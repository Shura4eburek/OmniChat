"""Gradio front end over the omnivoice core, in the OmniChat HUD style.

build() only wires components; nothing slow runs there. The environment probe (docker / GPU, up to
~2 minutes) and the dependency checklist start on the first page load in daemon threads, «Установить
зависимости» and training run in daemon threads (SetupRunner / TrainRunner, polled by gr.Timer), and slicing / transcription use the queue with gr.Progress so other sections stay usable.

Writes are serialised per project by helpers.ProjectLocks (non-blocking): slice, transcribe, save
edits, drop/restore, «Готово», check, pack and the Colab zip hold the project's lock for their whole
run; a second one is refused with «Проект занят: идёт <операция> — подожди». Training holds it from
Start until the dataset csv is written and releases it before the long docker run.
"""
from contextlib import contextmanager
import functools
import html
import logging
import traceback
import warnings
from pathlib import Path

import gradio as gr

from omnivoice import checker, colab, dataset, install, languages, pack, previews, slicer, train, transcriber, verify
from omnivoice.fsutil import TargetBusy
from omnivoice.pack import PackError
from omnivoice.project import Project, ProjectError
from omnivoice.ui import strings as S
from omnivoice.ui import theme
from omnivoice.ui.helpers import (COLUMNS, NAV_SECTIONS, SECTION_STEP, SECTIONS, EnvProbe, ProjectLocks,
                                  SetupRunner, TrainRunner, apply_edits, check_install_target, checklist_html,
                                  copy_uploads, counter_label, env_badge, error_text, list_projects, needs_setup,
                                  list_raw_files, portrait_preview, report_html, segments_rows, stats_line,
                                  steps_bar_html, toggle_dropped)

log = logging.getLogger("omnivoice.ui")
# Gradio warns on every update that a Styler can't be shown in an interactive table, yet the row
# colours do render (checked in the browser); keep the console readable.
warnings.filterwarnings("ignore", message="Cannot display Styler object in interactive mode")

USER_ERRORS = (ProjectError, train.TrainError, PackError, TargetBusy, RuntimeError, ValueError, OSError)
PACK_FIELDS = (("name", S.F_NAME), ("description", S.F_DESCRIPTION), ("gender", S.F_GENDER),
               ("sample", S.F_SAMPLE))
PREVIEW_SLOTS = 4

# Clicking a chip in the steps bar selects that section (event delegation survives re-renders).
STEPS_JS = """
element.addEventListener('click', (e) => {
  const chip = e.target.closest('.st');
  if (chip) trigger('click', {section: chip.dataset.section});
});
"""


def msg_html(text: str = "", error: bool = False) -> str:
    if not text:
        return ""
    cls = "section-msg err" if error else "section-msg"
    return f'<div class="{cls}">{html.escape(text).replace(chr(10), "<br>")}</div>'


def header_html(env) -> str:
    return (f'<div class="hud-top"><span class="hud-title">{S.TITLE}</span>'
            f'<span class="hud-badge">{html.escape(env_badge(env))}</span></div>')


def guarded(n_out: int, msg_idx: int = 0):
    """Core errors become a gr.Warning toast plus red text in the section's message slot;
    every other output is left untouched. Never a traceback in the browser."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except USER_ERRORS as e:
                text = error_text(e)
            except Exception:  # unexpected: full detail goes to the console only
                log.error("UI handler %s failed:\n%s", fn.__name__, traceback.format_exc())
                text = S.ERR_UNKNOWN
            gr.Warning(text, title=S.ERR_TITLE)
            out = [gr.skip()] * n_out
            out[msg_idx] = msg_html(text, error=True)
            return out[0] if n_out == 1 else tuple(out)
        return wrapper
    return deco


def table_value(rows):
    """Phrase rows as a styled frame: flagged rows yellow, dropped rows struck through (mockup look)."""
    import pandas as pd
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df

    def style(row):
        if row[S.COL_DROPPED]:
            css = f"color:{theme.BAD};text-decoration:line-through"
        elif row[S.COL_FLAGS]:
            css = f"color:{theme.FLAG}"
        else:
            css = ""
        return [css] * len(row)
    return df.style.apply(style, axis=1).format({S.COL_DURATION: "{:.1f}"})


def first_open_section(steps: dict) -> str:
    for section in SECTIONS:
        if section != S.SEC_SLICE and not steps.get(SECTION_STEP[section]):
            return section
    return S.SEC_PACK


def build(projects_root: Path, detect=None, check_fn=None, install_fn=None) -> gr.Blocks:
    """detect / check_fn / install_fn replace train.detect_env / deps.check_all / deps.install_all (tests)."""
    root = Path(projects_root)
    probe = EnvProbe(detect or (lambda: train.detect_env()))
    setup = SetupRunner(install_fn=install_fn, check_fn=check_fn, on_finish=probe.restart)
    runners: dict[str, TrainRunner] = {}
    locks = ProjectLocks()

    @contextmanager
    def locked(name, op: str):
        """Hold the project's write lock for the whole block; yields the freshly loaded project."""
        if not name:
            raise ProjectError(S.NO_PROJECT_SELECTED)
        with locks.hold(root / name, op):
            yield load(name)

    def runner(name: str) -> TrainRunner:
        return runners.setdefault(name, TrainRunner())

    def load(name) -> Project:
        if not name:
            raise ProjectError(S.NO_PROJECT_SELECTED)
        return Project.load(root / name)

    def try_load(name):
        try:
            return load(name)
        except ProjectError:
            return None

    def table_update(p, only_flagged, tolerant=False):
        """tolerant: a corrupt metadata.csv / review.json shows an empty table instead of raising
        (used where no error slot exists: startup, project switch, filter); actions still report it."""
        try:
            segs = dataset.load(p) if p else []
        except ProjectError:
            if not tolerant:
                raise
            segs = []
        return stats_line(segs), table_value(segments_rows(segs, only_flagged))

    def steps_html(p, section):
        return steps_bar_html(p.steps if p else {}, SECTION_STEP.get(section), need_setup=needs_setup(probe.env))

    projects = list_projects(root)
    first = projects[0] if projects else None
    p0 = try_load(first)
    sec0 = first_open_section(p0.steps) if p0 else S.SEC_SETUP  # a fresh install starts at «Установка»
    stats0, rows0 = table_update(p0, False, tolerant=True)
    display0 = p0.display if p0 else {}
    targets = [str(t) for t in install.default_targets()]

    with gr.Blocks(title=S.PAGE_TITLE) as demo:
        with gr.Column(elem_classes="hud-panel"):
            header = gr.HTML(header_html(None))
            with gr.Row(equal_height=False):
                # ---------------- sidebar ----------------
                with gr.Column(scale=1, min_width=210, elem_classes="hud-nav"):
                    project_dd = gr.Dropdown(projects, value=first, label=S.PROJECT,
                                             info=None if projects else S.NO_PROJECTS)
                    section = gr.Radio(list(NAV_SECTIONS), value=sec0, show_label=False, container=False)
                    with gr.Accordion(S.NEW_PROJECT, open=not projects, elem_classes="hud-new"):
                        new_name = gr.Textbox(label=S.NEW_NAME, max_lines=1)
                        new_lang = gr.Dropdown(list(languages.PRESETS), value="ru", label=S.NEW_LANGUAGE)
                        create_btn = gr.Button(S.CREATE, variant="primary", size="sm")
                        create_msg = gr.HTML()

                # ---------------- main ----------------
                with gr.Column(scale=4, elem_classes="hud-main"):
                    steps = gr.HTML(steps_html(p0, sec0), js_on_load=STEPS_JS)

                    with gr.Column(visible=sec0 == S.SEC_SETUP, elem_classes="hud-section") as g_setup:
                        gr.HTML(msg_html(S.SETUP_INTRO))
                        checklist = gr.HTML(checklist_html(None))
                        setup_btn = gr.Button(S.SETUP_INSTALL, variant="primary")
                        setup_progress = gr.HTML(setup.progress.html())
                        setup_status = gr.HTML(setup.status_html())
                        setup_log = gr.Textbox(label=S.SETUP_LOG, lines=12, max_lines=12, interactive=False,
                                               autoscroll=True)
                        setup_seen = gr.State(-1)

                    with gr.Column(visible=sec0 == S.SEC_AUDIO, elem_classes="hud-section") as g_audio:
                        upload = gr.File(label=S.UPLOAD, file_count="multiple", type="filepath")
                        raw_df = gr.Dataframe(list_raw_files(p0.raw_dir) if p0 else [],
                                              headers=[S.RAW_NAME, S.RAW_SIZE], label=S.RAW_FILES,
                                              interactive=False, type="array", max_height=260)
                        with gr.Row():
                            isolate = gr.Checkbox(label=S.ISOLATE, value=False)
                            slice_btn = gr.Button(S.SLICE, variant="primary")
                        audio_msg = gr.HTML()

                    with gr.Column(visible=sec0 in (S.SEC_SLICE, S.SEC_PHRASES),
                                   elem_classes="hud-section") as g_phrases:
                        with gr.Row(equal_height=True):
                            stats = gr.HTML(stats0)
                            only_flagged = gr.Checkbox(label=S.ONLY_FLAGGED, value=False, scale=0, min_width=130)
                        table = gr.Dataframe(rows0, headers=COLUMNS, type="array",
                                             datatype=["str", "str", "number", "str", "bool"],
                                             interactive=True, static_columns=[0, 2, 3, 4], wrap=True,
                                             column_widths=["14%", "54%", "10%", "14%", "8%"], max_height=420)
                        selected = gr.State(None)
                        player = gr.Audio(label=S.PLAYER, type="filepath", interactive=False)
                        with gr.Row():
                            transcribe_btn = gr.Button(S.TRANSCRIBE)
                            save_btn = gr.Button(S.SAVE_EDITS, variant="primary")
                            drop_btn = gr.Button(S.TOGGLE_DROP)
                            done_btn = gr.Button(S.PHRASES_DONE)
                        phrases_msg = gr.HTML()

                    with gr.Column(visible=sec0 == S.SEC_CHECK, elem_classes="hud-section") as g_check:
                        check_btn = gr.Button(S.CHECK, variant="primary")
                        check_out = gr.HTML(msg_html(S.CHECK_EMPTY))

                    with gr.Column(visible=sec0 == S.SEC_TRAIN, elem_classes="hud-section") as g_train:
                        with gr.Column(visible=False, elem_classes="setup-needed") as setup_needed:
                            gr.HTML(msg_html(S.SETUP_FIRST_HINT, error=True))
                            goto_setup = gr.Button(S.SETUP_GOTO, variant="primary")
                        with gr.Column(visible=False) as colab_group:
                            gr.Markdown(S.COLAB_HINT.format(url=colab.NOTEBOOK_URL))
                            colab_btn = gr.Button(S.COLAB_ZIP)
                            colab_file = gr.File(label=S.COLAB_FILE, interactive=False, visible=False)
                        with gr.Row():
                            epochs = gr.Number(1000, label=S.EPOCHS, precision=0, minimum=1)
                            batch = gr.Number(16, label=S.BATCH, precision=0, minimum=1)
                        with gr.Row():
                            start_btn = gr.Button(S.TRAIN_START, variant="primary")
                            stop_btn = gr.Button(S.TRAIN_STOP, variant="stop")
                            resume_btn = gr.Button(S.TRAIN_RESUME)
                        train_status = gr.HTML(f'<div class="train-status">{S.TRAIN_IDLE}</div>')
                        loss_plot = gr.LinePlot(x="step", y="loss", label=S.LOSS, height=220,
                                                x_title=S.LOSS_STEP, y_title=S.LOSS_VALUE)
                        train_log = gr.Textbox(label=S.TRAIN_LOG, lines=10, max_lines=10, interactive=False,
                                               autoscroll=True)
                        with gr.Row(equal_height=True):
                            ckpt_dd = gr.Dropdown([], label=S.CHECKPOINTS, scale=3)
                            refresh_btn = gr.Button(S.REFRESH, scale=1)
                        export_btn = gr.Button(S.EXPORT, variant="primary")
                        preview_dd = gr.Dropdown([], label=S.PREVIEW_STEP)
                        with gr.Row():
                            preview_players = [gr.Audio(label=S.PREVIEW.format(n=i + 1), type="filepath",
                                                        interactive=False, visible=False)
                                               for i in range(PREVIEW_SLOTS)]
                        train_msg = gr.HTML()

                    with gr.Column(visible=sec0 == S.SEC_PACK, elem_classes="hud-section") as g_pack:
                        with gr.Row():
                            with gr.Column(scale=3):
                                fields = {}
                                for key, label in PACK_FIELDS:
                                    fields[key] = gr.Textbox(display0.get(key, ""), max_lines=3 if key == "description" else 1,
                                                             label=counter_label(label, display0.get(key, ""), key))
                                license_tb = gr.Textbox(display0.get("license", ""), label=S.F_LICENSE, max_lines=1)
                            with gr.Column(scale=2):
                                portrait_in = gr.Image(label=S.PORTRAIT, type="filepath", sources=["upload"],
                                                       height=200)
                                portrait_out = gr.Image(label=S.PORTRAIT_PREVIEW, interactive=False, height=200,
                                                        elem_classes="portrait")
                        pack_btn = gr.Button(S.PACK, variant="primary")
                        pack_msg = gr.HTML()
                        sample_audio = gr.Audio(label=S.SAMPLE_AUDIO, type="filepath", interactive=False)
                        packed = gr.State(None)
                        with gr.Row(equal_height=True):
                            target_dd = gr.Dropdown(targets, value=targets[0] if targets else None,
                                                    allow_custom_value=True, label=S.INSTALL_TARGET, scale=3)
                            overwrite = gr.Checkbox(label=S.INSTALL_OVERWRITE, value=False, scale=1)
                        install_btn = gr.Button(S.INSTALL, variant="primary")
                        install_msg = gr.HTML()

        groups = [g_setup, g_audio, g_phrases, g_check, g_train, g_pack]
        group_of = {S.SEC_SETUP: g_setup, S.SEC_AUDIO: g_audio, S.SEC_SLICE: g_phrases, S.SEC_PHRASES: g_phrases,
                    S.SEC_CHECK: g_check, S.SEC_TRAIN: g_train, S.SEC_PACK: g_pack}
        env_timer = gr.Timer(1.0)
        train_timer = gr.Timer(2.0)
        setup_timer = gr.Timer(1.0)
        loss_timer = gr.Timer(15.0)

        # ---------------- environment probe ----------------
        def start_probe():
            probe.start()
            if setup.items is None:
                setup.check()
            return header_html(probe.env)

        def poll_env(name, sec):
            env = probe.env
            if env is None:
                return (gr.skip(),) * 6
            return (header_html(env), train.batch_size_for(env.vram_mib), gr.update(visible=not env.gpu),
                    gr.update(visible=needs_setup(env)), steps_html(try_load(name), sec), gr.Timer(active=False))

        demo.load(start_probe, outputs=header)
        env_timer.tick(poll_env, [project_dd, section], [header, batch, colab_group, setup_needed, steps, env_timer],
                       show_progress="hidden")

        # ---------------- setup ----------------
        @guarded(2)
        def on_setup():
            setup.start()  # RuntimeError(S.SETUP_BUSY) on a double click → toast
            return setup.status_html(), setup.progress.html()

        setup_btn.click(on_setup, None, [setup_status, setup_progress])

        def on_setup_tick(seen):
            v = setup.version
            if v == seen:
                return (gr.skip(),) * 6
            # a finished run re-probes the environment (SetupRunner.on_finish): poll the badge again
            env_poll = gr.Timer(active=True) if setup.status != "running" and setup.status != "idle" else gr.skip()
            return (checklist_html(setup.items), setup.progress.html(), setup.status_html(), setup.log_text(), v,
                    env_poll)

        setup_timer.tick(on_setup_tick, setup_seen,
                         [checklist, setup_progress, setup_status, setup_log, setup_seen, env_timer],
                         show_progress="hidden")  # 1 s polling must not flash a loader
        goto_setup.click(lambda: S.SEC_SETUP, None, section)

        # ---------------- navigation ----------------
        def on_section(name, sec):
            target = group_of.get(sec)
            if sec == S.SEC_SETUP and not setup.running:
                setup.check()  # the user may have installed something by hand meanwhile
            return [steps_html(try_load(name), sec)] + [gr.update(visible=g is target) for g in groups]

        section.change(on_section, [project_dd, section], [steps] + groups)

        def on_chip(evt: gr.EventData):
            sec = getattr(evt, "section", None)
            return sec if sec in NAV_SECTIONS else gr.skip()

        steps.click(on_chip, None, section)

        section_msgs = [audio_msg, phrases_msg, train_msg, pack_msg, install_msg]
        refresh_outputs = [steps, raw_df, stats, table, selected, player, check_out, train_status, train_log,
                           ckpt_dd, preview_dd, packed, sample_audio, license_tb, *fields.values(),
                           portrait_in, portrait_out, colab_file, *section_msgs, *preview_players]

        def refresh_all(name, sec, flagged):
            p = try_load(name)
            st, rows = table_update(p, flagged, tolerant=True)
            d = p.display if p else {}
            r = runners.get(name)
            cps = previews.list_checkpoints(p) if p else []
            return [steps_html(p, sec), list_raw_files(p.raw_dir) if p else [], st, rows, None, None,
                    msg_html(S.CHECK_EMPTY),
                    f'<div class="train-status">{html.escape(r.status_text() if r else S.TRAIN_IDLE)}</div>',
                    r.log_text() if r else "", gr.update(choices=ckpt_choices(cps), value=None),
                    gr.update(choices=[], value=None), None, None, d.get("license", "")] + [
                gr.update(value=d.get(k, ""), label=counter_label(lbl, d.get(k, ""), k)) for k, lbl in PACK_FIELDS] + [
                None, None, gr.update(value=None, visible=False)] + [""] * len(section_msgs) + [
                gr.update(value=None, visible=False)] * PREVIEW_SLOTS

        project_dd.change(refresh_all, [project_dd, section, only_flagged], refresh_outputs)

        @guarded(2)
        def create(name, lang):
            name = (name or "").strip()
            if not name:
                raise ValueError(S.NAME_REQUIRED)
            folder = dataset.sanitize_id(name).strip("_") or "voice"
            if (root / folder).exists():
                raise ValueError(S.PROJECT_EXISTS.format(name=folder))
            root.mkdir(parents=True, exist_ok=True)
            Project.create(root / folder, name=name, language=lang)
            return msg_html(S.CREATED.format(name=name)), gr.update(choices=list_projects(root), value=folder)

        create_btn.click(create, [new_name, new_lang], [create_msg, project_dd])

        # ---------------- audio ----------------
        @guarded(3)
        def on_upload(name, files):
            with locked(name, S.OP_UPLOAD) as p:
                out = copy_uploads(files or [], p.raw_dir)
            return msg_html(S.UPLOADED.format(n=len(out))), list_raw_files(p.raw_dir), None

        upload.upload(on_upload, [project_dd, upload], [audio_msg, raw_df, upload])

        @guarded(4)
        def on_slice(name, iso, sec, flagged, progress=gr.Progress()):
            with locked(name, S.OP_SLICE) as p:
                n = slicer.slice_project(p, isolate=iso,
                                         progress=lambda f, frac: progress(frac, desc=S.SLICING.format(name=f)))
                st, rows = table_update(p, flagged)
            return msg_html(S.SLICED.format(n=n)), steps_html(p, sec), st, rows

        slice_btn.click(on_slice, [project_dd, isolate, section, only_flagged],
                        [audio_msg, steps, stats, table])

        # ---------------- phrases ----------------
        def on_filter(name, flagged):
            st, rows = table_update(try_load(name), flagged, tolerant=True)
            return st, rows

        only_flagged.change(on_filter, [project_dd, only_flagged], [stats, table])

        def on_select(name, rows, evt: gr.SelectData):
            p = try_load(name)
            row = getattr(evt, "row_value", None)
            if not row:
                idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
                row = rows[idx] if rows is not None and 0 <= idx < len(rows) else None
            if not p or not row:
                return None, None
            wav = p.segments_dir / f"{row[0]}.wav"
            return row[0], (str(wav) if wav.is_file() else None)

        table.select(on_select, [project_dd, table], [selected, player])

        @guarded(3)
        def on_transcribe(name, flagged, progress=gr.Progress()):
            with locked(name, S.OP_TRANSCRIBE) as p:
                n = transcriber.transcribe_project(
                    p, progress=lambda sid, frac: progress(frac, desc=S.TRANSCRIBING.format(name=sid)))
                st, rows = table_update(p, flagged)
            return msg_html(S.TRANSCRIBED.format(n=n)), st, rows

        transcribe_btn.click(on_transcribe, [project_dd, only_flagged], [phrases_msg, stats, table])

        @guarded(3)
        def on_save(name, rows, flagged):
            with locked(name, S.OP_SAVE) as p:
                segs = dataset.load(p)
                n = apply_edits(segs, rows)
                if n:
                    dataset.save(p, segs)
                st, new_rows = table_update(p, flagged)
            return msg_html(S.SAVED_EDITS.format(n=n)), st, new_rows

        save_btn.click(on_save, [project_dd, table, only_flagged], [phrases_msg, stats, table])

        @guarded(3)
        def on_drop(name, sid, flagged):
            if not sid:
                raise ValueError(S.SELECT_ROW)
            with locked(name, S.OP_DROP) as p:
                segs = dataset.load(p)
                now = toggle_dropped(segs, sid)
                dataset.save(p, segs)
                st, rows = table_update(p, flagged)
            return msg_html((S.DROPPED if now else S.RESTORED).format(id=sid)), st, rows

        drop_btn.click(on_drop, [project_dd, selected, only_flagged], [phrases_msg, stats, table])

        @guarded(2)
        def on_done(name, sec):
            with locked(name, S.OP_DONE) as p:
                p.mark("phrases"); p.save()
            return msg_html(S.PHRASES_MARKED), steps_html(p, sec)

        done_btn.click(on_done, [project_dd, section], [phrases_msg, steps])

        # ---------------- check ----------------
        @guarded(2)
        def on_check(name, sec):
            with locked(name, S.OP_CHECK) as p:
                r = checker.check_project(p)
            return report_html(r), steps_html(p, sec)

        check_btn.click(on_check, [project_dd, section], [check_out, steps])

        # ---------------- train ----------------
        def ckpt_choices(cps):
            return [((S.CHECKPOINT_LAST if c.metric is None else S.CHECKPOINT_ITEM).format(epoch=c.epoch)
                     + (f" · {c.metric}={c.value:.3f}" if c.metric else ""), str(c.path)) for c in cps]

        def start_training(name, n_epochs, n_batch, resume):
            if not name:
                raise ProjectError(S.NO_PROJECT_SELECTED)
            key = root / name
            # Held until the dataset csv is written (first should_stop poll), then released for the docker run.
            locks.acquire(key, S.OP_TRAIN)
            try:
                p = load(name)
                n_epochs = int(n_epochs or 1000)
                runner(name).start(p, epochs=n_epochs, resume=resume, batch=int(n_batch) if n_batch else None,
                                   env=probe.env, target=train.base_epoch(p) + n_epochs,
                                   on_prepared=lambda: locks.release(key))
            except BaseException:
                locks.release(key)
                raise
            return msg_html(""), f'<div class="train-status">{html.escape(runner(name).status_text())}</div>'

        start_btn.click(guarded(2)(lambda n, e, b: start_training(n, e, b, False)),
                        [project_dd, epochs, batch], [train_msg, train_status])
        resume_btn.click(guarded(2)(lambda n, e, b: start_training(n, e, b, True)),
                         [project_dd, epochs, batch], [train_msg, train_status])

        @guarded(2)
        def on_stop(name):
            r = runners.get(name)
            if r:
                r.stop()
            return msg_html(""), f'<div class="train-status">{html.escape(r.status_text() if r else S.TRAIN_IDLE)}</div>'

        stop_btn.click(on_stop, project_dd, [train_msg, train_status])

        def on_train_tick(name):
            r = runners.get(name)
            if r is None:
                return gr.skip(), gr.skip()
            return f'<div class="train-status">{html.escape(r.status_text())}</div>', r.log_text()

        train_timer.tick(on_train_tick, project_dd, [train_status, train_log])

        def loss_frame(name, sec):
            import pandas as pd
            r = runners.get(name)
            if sec != S.SEC_TRAIN and not (r and r.running):
                return gr.skip()  # nobody is looking and nothing changes: don't re-read tensorboard logs
            try:
                p = try_load(name)
                series = previews.loss_series(p) if p else []
            except Exception:  # tensorboard missing / log being written: just keep the old chart
                return gr.skip()
            return pd.DataFrame(series, columns=["step", "loss"])

        loss_timer.tick(loss_frame, [project_dd, section], loss_plot)
        demo.load(loss_frame, [project_dd, section], loss_plot)
        project_dd.change(loss_frame, [project_dd, section], loss_plot)
        section.change(loss_frame, [project_dd, section], loss_plot)

        @guarded(3)
        def on_refresh(name, progress=gr.Progress()):
            p = load(name)
            progress(0, desc=S.REFRESHING)
            cps = previews.list_checkpoints(p)
            found = previews.extract_previews(p)
            steps_list = [str(s) for s in sorted(found, reverse=True)]
            return (msg_html("" if cps else S.NO_CHECKPOINTS),
                    gr.update(choices=ckpt_choices(cps), value=str(cps[0].path) if cps else None),
                    gr.update(choices=steps_list, value=steps_list[0] if steps_list else None))

        refresh_btn.click(on_refresh, project_dd, [train_msg, ckpt_dd, preview_dd])

        def on_preview(name, step):
            p = try_load(name)
            files = sorted((p.train_dir / "previews" / str(step)).glob("*.wav")) if p and step else []
            return [gr.update(value=str(files[i]), visible=True) if i < len(files) else gr.update(value=None, visible=False)
                    for i in range(PREVIEW_SLOTS)]

        preview_dd.change(on_preview, [project_dd, preview_dd], preview_players)

        @guarded(1)
        def on_export(name, ckpt, progress=gr.Progress()):
            if not ckpt:
                raise ValueError(S.CHOOSE_CHECKPOINT)
            with locked(name, S.OP_EXPORT) as p:
                progress(0, desc=S.EXPORTING)
                out = train.export_project(p, Path(ckpt))
            return msg_html(S.EXPORTED.format(path=out))

        export_btn.click(on_export, [project_dd, ckpt_dd], train_msg)

        @guarded(2)
        def on_colab(name, progress=gr.Progress()):
            with locked(name, S.OP_COLAB) as p:
                progress(0, desc=S.ZIPPING)
                z = colab.make_dataset_zip(p)
            return msg_html(S.COLAB_READY.format(path=z)), gr.update(value=str(z), visible=True)

        colab_btn.click(on_colab, project_dd, [train_msg, colab_file])

        # ---------------- pack ----------------
        for key, label in PACK_FIELDS:
            fields[key].input(functools.partial(lambda lbl, k, v: gr.update(label=counter_label(lbl, v, k)), label, key),
                              fields[key], fields[key])

        @guarded(2)
        def on_portrait(path):
            if not path:
                return msg_html(""), None
            try:
                return msg_html(""), portrait_preview(Path(path))
            except Exception:
                raise ValueError(S.PORTRAIT_BAD)

        portrait_in.change(on_portrait, portrait_in, [pack_msg, portrait_out])

        @guarded(4)
        def on_pack(name, portrait, lic, sec, v_name, v_description, v_gender, v_sample, progress=gr.Progress()):
            values = (v_name, v_description, v_gender, v_sample)
            with locked(name, S.OP_PACK) as p:
                progress(0, desc=S.PACKING)
                p.display.update({k: (v or "").strip() for (k, _), v in zip(PACK_FIELDS, values)})
                p.display["license"] = (lic or "").strip()
                p.save()
                folder = pack.pack_project(p, portrait=Path(portrait) if portrait else None)
            progress(0.7, desc=S.VERIFYING)
            v = verify.verify_voice(folder)
            text = S.PACKED.format(path=folder) + "\n" + v.message
            if not v.ok:
                gr.Warning(v.message, title=S.ERR_TITLE)
            return (msg_html(text, error=not v.ok), str(v.sample) if v.sample else None, str(folder),
                    steps_html(p, sec))

        pack_btn.click(on_pack, [project_dd, portrait_in, license_tb, section, *fields.values()],
                       [pack_msg, sample_audio, packed, steps])

        @guarded(1)
        def on_install(name, folder, target, over):
            if not folder:
                p = load(name)
                guess = p.export_dir / pack.folder_name(p.display.get("name") or p.name)
                if not guess.is_dir():
                    raise ValueError(S.INSTALL_NO_VOICE)
                folder = guess
            t = check_install_target(target)
            dest = install.install_voice(Path(folder), t, overwrite=bool(over))
            return msg_html(S.INSTALLED.format(path=dest))

        install_btn.click(on_install, [project_dd, packed, target_dd, overwrite], install_msg)

    demo.omnivoice_probe = probe  # for launch() / debugging
    return demo


def launch(projects_root: Path, port: int = 7860, inbrowser: bool = True) -> None:
    projects_root = Path(projects_root).resolve()
    projects_root.mkdir(parents=True, exist_ok=True)
    demo = build(projects_root)
    demo.queue(default_concurrency_limit=1).launch(
        server_name="127.0.0.1", server_port=port, inbrowser=inbrowser, theme=theme.THEME, css=theme.CSS, head=theme.HEAD,
        allowed_paths=[str(projects_root)], footer_links=[])
