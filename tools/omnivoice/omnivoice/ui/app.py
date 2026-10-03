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

from omnivoice import (checker, colab, dataset, datadir, install, languages, pack, paths, previews, slicer, train,
                       transcriber, verify)
from omnivoice.datadir import human_size, size_of
from omnivoice.fsutil import TargetBusy
from omnivoice.pack import PackError
from omnivoice.project import Project, ProjectError
from omnivoice.ui import strings as S
from omnivoice.ui import theme
from omnivoice.ui.helpers import (COLUMNS, NAV_SECTIONS, SECTION_STEP, SECTIONS, EnvProbe, ProjectLocks,
                                  SetupRunner, TrainRunner, apply_edits, check_install_target, checklist_html,
                                  ckpt_choices, copy_uploads, counter_label, data_dir_html, disk_html, env_badge,
                                  error_text,
                                  last_epoch_target,
                                  list_projects, needs_setup, list_raw_files, portrait_preview, report_html,
                                  segments_rows, stats_line, steps_bar_html, toggle_dropped)

log = logging.getLogger("omnivoice.ui")
# Gradio warns on every update that a Styler can't be shown in an interactive table, yet the row
# colours do render (checked in the browser); keep the console readable.
warnings.filterwarnings("ignore", message="Cannot display Styler object in interactive mode")

USER_ERRORS = (ProjectError, train.TrainError, PackError, TargetBusy, RuntimeError, ValueError, OSError)
PACK_FIELDS = (("name", S.F_NAME), ("description", S.F_DESCRIPTION), ("gender", S.F_GENDER),
               ("sample", S.F_SAMPLE))
PREVIEW_SLOTS = 5  # piper synthesises 5 validation phrases per epoch

# Clicking a chip in the steps bar selects that section (event delegation survives re-renders).
STEPS_JS = """
element.addEventListener('click', (e) => {
  const chip = e.target.closest('.st');
  if (chip) trigger('click', {section: chip.dataset.section});
});
"""


def msg_html(text: str = "", error: bool = False, muted: bool = False) -> str:
    if not text:
        return ""
    cls = "section-msg err" if error else ("section-msg muted" if muted else "section-msg")
    return f'<div class="{cls}">{html.escape(text).replace(chr(10), "<br>")}</div>'


def header_html(env) -> str:
    return (f'<div class="hud-top"><span class="hud-title">{S.TITLE}</span>'
            f'<span class="hud-badge">{html.escape(env_badge(env))}</span></div>')


def slice_message(n: int, recognised: bool) -> str:
    if not n:
        return S.SLICED_NONE
    return (S.SLICED_TEXT if recognised else S.SLICED_NO_TEXT).format(n=n)


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
    dd0, dd_source = paths.cache_source()

    with gr.Blocks(title=S.PAGE_TITLE) as demo:
        with gr.Column(elem_classes="hud-panel"):
            header = gr.HTML(header_html(None))
            with gr.Row(equal_height=False):
                # ---------------- sidebar ----------------
                with gr.Column(scale=1, min_width=210, elem_classes="hud-nav"):
                    project_dd = gr.Dropdown(projects, value=first, label=S.PROJECT, filterable=False,
                                             info=None if projects else S.NO_PROJECTS)
                    section = gr.Radio(list(NAV_SECTIONS), value=sec0, show_label=False, container=False)
                    with gr.Accordion(S.NEW_PROJECT, open=not projects, elem_classes="hud-new"):
                        new_name = gr.Textbox(label=S.NEW_NAME, max_lines=1)
                        new_lang = gr.Dropdown(list(languages.PRESETS), value="ru", label=S.NEW_LANGUAGE, filterable=False)
                        create_btn = gr.Button(S.CREATE, variant="primary", size="sm")
                        create_msg = gr.HTML()

                # ---------------- main ----------------
                with gr.Column(scale=4, elem_classes="hud-main"):
                    steps = gr.HTML(steps_html(p0, sec0), js_on_load=STEPS_JS)

                    with gr.Column(visible=sec0 == S.SEC_SETUP, elem_classes="hud-section") as g_setup:
                        gr.HTML(msg_html(S.SETUP_INTRO))
                        checklist = gr.HTML(checklist_html(None))
                        with gr.Row(equal_height=True):
                            data_dir_box = gr.Textbox(str(dd0), label=S.DATA_DIR, info=S.DATA_DIR_INFO, scale=4,
                                                      interactive=dd_source != "env")
                            data_dir_btn = gr.Button(S.DATA_DIR_MOVE, scale=1, min_width=220, interactive=dd_source != "env")
                        data_dir_hint = gr.HTML(data_dir_html(dd0, dd_source))
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
                                             column_widths=["14%", "50%", "10%", "14%", "12%"], max_height=420)
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
                        with gr.Row(equal_height=True):
                            mos_plot = gr.LinePlot(x="epoch", y="mos", label=S.CHART_MOS, height=200,
                                                   x_title=S.CHART_EPOCH, y_title="MOS")
                            mel_plot = gr.LinePlot(x="epoch", y="mel", label=S.CHART_MEL, height=200,
                                                   x_title=S.CHART_EPOCH, y_title="mel")
                        chart_note = gr.HTML()
                        train_log = gr.Textbox(label=S.TRAIN_LOG, lines=10, max_lines=10, interactive=False,
                                               autoscroll=True)
                        log_note = gr.HTML()
                        gr.HTML(f'<div class="sub-head">{S.CHECKPOINTS}</div>')
                        with gr.Row(equal_height=True):
                            ckpt_dd = gr.Dropdown([], label=S.CHECKPOINTS, show_label=False, scale=3,
                                                  filterable=False)
                            refresh_btn = gr.Button(S.REFRESH, scale=1)
                        gr.HTML(msg_html(S.CKPT_HINT, muted=True))
                        export_btn = gr.Button(S.EXPORT, variant="primary")
                        gr.HTML(f'<div class="sub-head">{S.LISTEN}</div>' + msg_html(S.LISTEN_HINT, muted=True))
                        listen_head = gr.HTML()
                        with gr.Row(elem_classes="listen-row"):
                            preview_players = [gr.Audio(label=S.PREVIEW.format(n=i + 1), type="filepath",
                                                        interactive=False, visible=False, min_width=150)
                                               for i in range(PREVIEW_SLOTS)]
                        gr.HTML(f'<div class="sub-head">{S.DISK}</div>')
                        disk_info = gr.HTML()
                        with gr.Row(equal_height=True):
                            prune_ok = gr.Checkbox(label=S.PRUNE_CONFIRM, value=False, scale=1)
                            prune_btn = gr.Button(S.PRUNE, variant="stop", scale=2)
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
        setup_timer = gr.Timer(1.0, active=False)  # woken by a setup run or check, sleeps when idle
        loss_timer = gr.Timer(15.0)

        # ---------------- environment probe ----------------
        def start_probe():
            probe.start()
            if setup.items is None:
                setup.check()
            return header_html(probe.env), gr.Timer(active=True)

        def poll_env(name, sec):
            env = probe.env
            if env is None:
                return (gr.skip(),) * 6
            return (header_html(env), train.batch_size_for(env.vram_mib), gr.update(visible=not env.gpu),
                    gr.update(visible=needs_setup(env)), steps_html(try_load(name), sec), gr.Timer(active=False))

        demo.load(start_probe, outputs=[header, setup_timer])

        def reload_projects(current):
            names = list_projects(root)
            value = current if current in names else (names[0] if names else None)
            return gr.update(choices=names, value=value, info=None if names else S.NO_PROJECTS)

        demo.load(reload_projects, project_dd, project_dd)
        env_timer.tick(poll_env, [project_dd, section], [header, batch, colab_group, setup_needed, steps, env_timer],
                       show_progress="hidden")

        # ---------------- setup ----------------
        @guarded(3)
        def on_setup():
            setup.start()  # RuntimeError(S.SETUP_BUSY) on a double click → toast
            return setup.status_html(), setup.progress.html(), gr.Timer(active=True)

        setup_btn.click(on_setup, None, [setup_status, setup_progress, setup_timer])

        @guarded(3)
        def on_data_dir(target):
            new = (target or "").strip()

            def job(on_line, progress):
                datadir.move_data(new, on_line)  # DataDirError (a RuntimeError) → the status shows it
                return None
            setup.start(job=job, done_text=S.DATA_DIR_DONE, error_title=S.DATA_DIR_ERROR)  # busy guard as setup
            return setup.status_html(), setup.progress.html(), gr.Timer(active=True)

        data_dir_btn.click(on_data_dir, data_dir_box, [setup_status, setup_progress, setup_timer])

        def on_data_dir_typed(target):
            t = Path((target or "").strip())
            return data_dir_html(t, dd_source) if t.anchor else gr.skip()

        data_dir_box.blur(on_data_dir_typed, data_dir_box, data_dir_hint, show_progress="hidden")

        def on_setup_tick(seen):
            v = setup.version
            if v == seen:  # nothing new; once the run/check is over the timer goes back to sleep
                return (gr.skip(),) * 8 + (gr.skip() if setup.busy else gr.Timer(active=False),)
            # a finished run re-probes the environment (SetupRunner.on_finish): poll the badge again
            finished = setup.status != "running" and setup.status != "idle"
            env_poll = gr.Timer(active=True) if finished else gr.skip()
            cur, source = paths.cache_source()
            box = str(cur) if setup.status == "done" and setup.done_text == S.DATA_DIR_DONE else gr.skip()
            return (checklist_html(setup.items), setup.progress.html(), setup.status_html(), setup.log_text(), v,
                    env_poll, data_dir_html(cur, source), box, gr.skip())

        setup_timer.tick(on_setup_tick, setup_seen,
                         [checklist, setup_progress, setup_status, setup_log, setup_seen, env_timer, data_dir_hint,
                          data_dir_box, setup_timer],
                         show_progress="hidden")  # 1 s polling must not flash a loader
        goto_setup.click(lambda: S.SEC_SETUP, None, section)

        # ---------------- navigation ----------------
        def on_section(name, sec):
            target = group_of.get(sec)
            wake = gr.skip()
            if sec == S.SEC_SETUP and not setup.running:
                setup.check()  # the user may have installed something by hand meanwhile
                wake = gr.Timer(active=True)
            return [steps_html(try_load(name), sec)] + [gr.update(visible=g is target) for g in groups] + [wake]

        section.change(on_section, [project_dd, section], [steps] + groups + [setup_timer])

        def on_chip(evt: gr.EventData):
            sec = getattr(evt, "section", None)
            return sec if sec in NAV_SECTIONS else gr.skip()

        steps.click(on_chip, None, section)

        section_msgs = [audio_msg, phrases_msg, train_msg, pack_msg, install_msg]
        refresh_outputs = [steps, raw_df, stats, table, selected, player, check_out, train_log,
                           packed, sample_audio, license_tb, *fields.values(),
                           portrait_in, portrait_out, colab_file, *section_msgs]

        def refresh_all(name, sec, flagged):
            """The training panel (status, charts, checkpoints, players) is refreshed by train_open."""
            p = try_load(name)
            st, rows = table_update(p, flagged, tolerant=True)
            d = p.display if p else {}
            r = runners.get(name)
            return [steps_html(p, sec), list_raw_files(p.raw_dir) if p else [], st, rows, None, None,
                    msg_html(S.CHECK_EMPTY), r.log_text() if r else "", None, None, d.get("license", "")] + [
                gr.update(value=d.get(k, ""), label=counter_label(lbl, d.get(k, ""), k)) for k, lbl in PACK_FIELDS] + [
                None, None, gr.update(value=None, visible=False)] + [""] * len(section_msgs)

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
            return msg_html(slice_message(n, transcriber.has_whisper())), steps_html(p, sec), st, rows

        slice_btn.click(on_slice, [project_dd, isolate, section, only_flagged],
                        [audio_msg, steps, stats, table], show_progress_on=[audio_msg])

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

        transcribe_btn.click(on_transcribe, [project_dd, only_flagged], [phrases_msg, stats, table],
                             show_progress_on=[phrases_msg])

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
                                   env=probe.env, target=last_epoch_target(p, n_epochs),
                                   offset=train.base_epoch(p), on_prepared=lambda: locks.release(key))
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

        def status_html(name, p=None, metrics=None):
            r = runners.get(name)
            if r is not None and r.status != "idle":
                return f'<div class="train-status">{html.escape(r.status_text())}</div>'
            done = max(metrics) - train.base_epoch(p) if p and metrics else 0
            text = S.TRAIN_IDLE_DONE.format(n=done) if done > 0 else S.TRAIN_IDLE
            return f'<div class="train-status">{html.escape(text)}</div>'

        def on_train_tick(name):
            r = runners.get(name)
            if r is None:
                return gr.skip(), gr.skip()
            if r.running:
                r.poll_checkpoints()
            return f'<div class="train-status">{html.escape(r.status_text())}</div>', r.log_text()

        train_timer.tick(on_train_tick, project_dd, [train_status, train_log], show_progress="hidden")

        def read_metrics(p) -> dict:
            try:
                return previews.epoch_metrics(p)
            except Exception:  # tensorboard missing / a file being rewritten: show what we can
                log.debug("events unreadable:\n%s", traceback.format_exc())
                return {}

        def players(p, ckpt, rows):
            """listen_head + one update per player for the checkpoint `ckpt` (a path string)."""
            row = next((r for r in rows if str(r.path) == ckpt), None)
            items, epoch = [], None
            if p is not None and row is not None:
                try:
                    epoch, items = previews.listen(p, row.epoch)
                except Exception:
                    log.warning("listen failed:\n%s", traceback.format_exc())
            if not items:
                head = msg_html(S.LISTEN_NONE, muted=True) if row is not None else ""
            else:
                off = train.base_epoch(p)
                text = (S.LISTEN_EPOCH if epoch == row.epoch else S.LISTEN_NEAREST).format(epoch=epoch - off)
                head = f'<div class="listen-head">{html.escape(text)}</div>'
            ups = [gr.update(value=str(items[i][1]), label=f"{i + 1}. {items[i][0]}", visible=True)
                   if i < len(items) else gr.update(value=None, visible=False) for i in range(PREVIEW_SLOTS)]
            return [head] + ups

        train_panel_outputs = [train_status, mos_plot, mel_plot, chart_note, log_note, ckpt_dd, disk_info,
                               listen_head, *preview_players]

        def train_panel(name, sec, current, force=False):
            """Status, charts, checkpoints, disk and players of the training section. Skipped while the
            section is hidden and nothing trains; the players are only redrawn when the selection moves."""
            import pandas as pd
            n = len(train_panel_outputs)
            r = runners.get(name)
            if not force and sec != S.SEC_TRAIN and not (r and r.running):
                return [gr.skip()] * n
            p = try_load(name)
            if p is None:
                return [gr.skip()] * n
            metrics = read_metrics(p)
            if r is not None:
                r.metrics = metrics
            off = train.base_epoch(p)
            mos = pd.DataFrame([(e, v) for e, v in previews.loss_series(p, "val_mos", off, metrics)],
                               columns=["epoch", "mos"])
            mel = pd.DataFrame([(e, v) for e, v in previews.loss_series(p, "val_mel", off, metrics)],
                               columns=["epoch", "mel"])
            rows = previews.rank_checkpoints(p, metrics)
            choices, best = ckpt_choices(rows, off)
            paths = [c[1] for c in choices]
            value = current if current in paths else best
            keep, drop = previews.prune_plan(p) if rows else ([], [])
            disk = disk_html(size_of(p.train_dir), len(keep) + len(drop),
                             sum(f.stat().st_size for f in drop if f.exists()), len(drop))
            raw_log = p.train_dir / "train.log"
            note = msg_html(S.TRAIN_LOG_FILE.format(path=raw_log), muted=True) if raw_log.exists() else ""
            listen = players(p, value, rows) if (value != current or force) else [gr.skip()] * (PREVIEW_SLOTS + 1)
            return [status_html(name, p, metrics), mos, mel,
                    "" if len(mos) or len(mel) else msg_html(S.CHART_EMPTY, muted=True), note,
                    gr.update(choices=choices, value=value) if choices else gr.update(choices=[], value=None),
                    disk if choices or len(mos) else "", *listen]

        def quiet(fn):
            """Timers / section switches: an unexpected error is logged, never toasted every few seconds."""
            @functools.wraps(fn)
            def wrapper(*args):
                try:
                    return fn(*args)
                except Exception:
                    log.error("training panel refresh failed:\n%s", traceback.format_exc())
                    return [gr.skip()] * len(train_panel_outputs)
            return wrapper

        on_train_open = quiet(lambda name, sec, cur: train_panel(name, sec, cur, force=sec == S.SEC_TRAIN))
        loss_timer.tick(quiet(train_panel), [project_dd, section, ckpt_dd], train_panel_outputs,
                        show_progress="hidden")
        demo.load(on_train_open, [project_dd, section, ckpt_dd], train_panel_outputs)
        section.change(on_train_open, [project_dd, section, ckpt_dd], train_panel_outputs)
        # a new project: drop the old selection so the new project's best checkpoint is preselected
        project_dd.change(quiet(lambda name, sec: train_panel(name, sec, None, force=True)), [project_dd, section],
                          train_panel_outputs)

        @guarded(len(train_panel_outputs) + 1)
        def on_refresh(name, sec, current, progress=gr.Progress()):
            p = load(name)
            progress(0, desc=S.REFRESHING)
            out = train_panel(name, sec, current, force=True)
            return [msg_html("" if previews.list_checkpoints(p) else S.NO_CHECKPOINTS, muted=True)] + out

        refresh_btn.click(on_refresh, [project_dd, section, ckpt_dd], [train_msg] + train_panel_outputs)

        @guarded(PREVIEW_SLOTS + 2)
        def on_listen(name, ckpt, progress=gr.Progress()):
            p = load(name)
            progress(0, desc=S.LISTENING)
            return [""] + players(p, ckpt, previews.rank_checkpoints(p, read_metrics(p)))

        ckpt_dd.input(on_listen, [project_dd, ckpt_dd], [train_msg, listen_head, *preview_players])

        @guarded(len(train_panel_outputs) + 2)
        def on_prune(name, sec, current, confirmed):
            r = runners.get(name)
            if r is not None and r.running:
                raise ValueError(S.PRUNE_BUSY)
            if not confirmed:
                raise ValueError(S.PRUNE_NEED_CONFIRM)
            with locked(name, S.OP_PRUNE) as p:
                if previews.recently_written(p):
                    raise ValueError(S.PRUNE_RECENT)
                _keep, drop = previews.prune_plan(p)
                n, freed = previews.delete_checkpoints(drop)
            out = train_panel(name, sec, current, force=True)
            return [msg_html(S.PRUNED.format(n=n, size=human_size(freed))), False] + out

        prune_btn.click(on_prune, [project_dd, section, ckpt_dd, prune_ok],
                        [train_msg, prune_ok] + train_panel_outputs)

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
