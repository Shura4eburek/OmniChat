"""Pure UI helpers: no gradio needed, so these run in the plain test environment too."""
import io
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from omnivoice.dataset import Segment
from omnivoice.ui import helpers as h
from omnivoice.ui import strings as S


def test_list_projects_only_dirs_with_project_toml(tmp_path):
    from omnivoice.project import Project
    Project.create(tmp_path / "b", name="b", language="ru")
    Project.create(tmp_path / "a", name="a", language="en")
    (tmp_path / "junk").mkdir()
    (tmp_path / "file.txt").write_text("x")
    assert h.list_projects(tmp_path) == ["a", "b"]
    assert h.list_projects(tmp_path / "missing") == []


def test_steps_bar_html_states():
    steps = {"audio": True, "slice": True, "phrases": False, "check": False, "train": False, "pack": False}
    html = h.steps_bar_html(steps, "phrases")
    assert html.count('data-section=') == 6
    assert 'class="st done" data-section="Аудио"' in html
    assert "1 АУДИО ✓" in html
    assert 'class="st on" data-section="Фразы"' in html
    assert 'class="st" data-section="Упаковка"' in html


def test_steps_bar_current_overrides_done():
    steps = {s: True for s in ("audio", "slice", "phrases", "check", "train", "pack")}
    html = h.steps_bar_html(steps, "audio")
    assert 'class="st on" data-section="Аудио"' in html


def test_section_mapping_covers_all_sections():
    assert [h.SECTION_STEP[s] for s in h.SECTIONS] == ["audio", "slice", "phrases", "check", "train", "pack"]


@pytest.mark.parametrize("name,expected", [
    ("song.mp3", "song.mp3"),
    ("../../evil.wav", "evil.wav"),
    ("..\\..\\evil.wav", "evil.wav"),
    ("C:\\Users\\x\\a b.wav", "a b.wav"),
    ("..", "audio"),
    (".hidden.wav", "hidden.wav"),
    ("ну:что?.flac", "ну_что_.flac"),
    ("", "audio"),
])
def test_safe_upload_name(name, expected):
    assert h.safe_upload_name(name) == expected


def test_copy_uploads_stays_in_raw_and_dedups(tmp_path):
    raw = tmp_path / "proj" / "raw"
    src = tmp_path / "up"
    src.mkdir()
    a = src / "voice.wav"; a.write_bytes(b"1")
    out = h.copy_uploads([a, a], raw, names=["../../voice.wav", "voice.wav"])
    assert [p.name for p in out] == ["voice.wav", "voice_2.wav"]
    assert all(p.parent == raw for p in out)
    assert not (tmp_path / "voice.wav").exists()
    assert (raw / "voice_2.wav").read_bytes() == b"1"


def test_list_raw_files_hides_markers(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"12")
    (tmp_path / ".sliced.json").write_text("{}")
    assert h.list_raw_files(tmp_path) == [["a.wav", "0.0 КБ"]]


def _segs():
    return [
        Segment("a", "раз", 2.0),
        Segment("b", "два", 4.0, flags=["check"]),
        Segment("c", "три", 6.0, flags=["check"], dropped=True),
    ]


def test_stats_line():
    line = h.stats_line(_segs())
    assert "фраз <b>2</b>" in line
    assert "речь <b>0.1 мин</b>" in line
    assert "к проверке: 1" in line
    assert "выкинуто: 1" in line


def test_segments_rows_and_filter():
    rows = h.segments_rows(_segs(), only_flagged=False)
    assert rows[0] == ["a", "раз", 2.0, "", False]
    assert rows[1][3] == "⚑ проверить"
    flagged = h.segments_rows(_segs(), only_flagged=True)
    assert [r[0] for r in flagged] == ["b"]


def test_apply_edits_sets_edited_and_drops_check_flag():
    segs = _segs()
    n = h.apply_edits(segs, [["a", "раз", 2.0, "", False], ["b", "два, исправлено", 4.0, "⚑ check", False]])
    assert n == 1
    b = segs[1]
    assert b.text == "два, исправлено" and b.edited is True and "check" not in b.flags
    assert segs[0].edited is False


def test_apply_edits_ignores_unknown_ids_and_strips_pipes():
    segs = _segs()
    assert h.apply_edits(segs, [["zzz", "x", 0, "", False], ["a", "р|аз", 2.0, "", False]]) == 1
    assert segs[0].text == "р аз"


def test_toggle_dropped():
    segs = _segs()
    assert h.toggle_dropped(segs, "a") is True and segs[0].dropped
    assert h.toggle_dropped(segs, "c") is False and not segs[2].dropped
    with pytest.raises(ValueError):
        h.toggle_dropped(segs, "nope")


def test_counter_label():
    assert h.counter_label("Имя", "abc", "name") == "Имя · 3/32"
    assert h.counter_label("Имя", "x" * 40, "name").endswith("40/32 ⚠")


def test_error_text_joins_pack_problems():
    from omnivoice.pack import PackError
    assert h.error_text(PackError(["один", "два"])) == "один\nдва"
    assert h.error_text(RuntimeError("плохо")) == "плохо"
    assert h.error_text(OSError()) == S.ERR_UNKNOWN


def test_report_html_colours():
    from omnivoice.checker import Report
    r = Report(12.5, 3, errors=["ошибка"], warnings=["внимание"], per_segment={"a": ["too_short"]})
    html = h.report_html(r)
    assert 'class="err"' in html and 'class="warn"' in html
    assert "<td>a</td>" in html and "слишком короткая" in html


def test_report_html_escapes():
    from omnivoice.checker import Report
    assert "<b>" not in h.report_html(Report(0, 0, errors=["<b>"]))


def test_portrait_preview_is_nearest_upscaled(tmp_path):
    src = tmp_path / "p.png"
    Image.new("RGB", (100, 80), (255, 0, 0)).save(src)
    img = h.portrait_preview(src)
    assert img.size == (192, 192)


def test_env_badge():
    from omnivoice.train import Env
    assert h.env_badge(None) == S.ENV_CHECKING
    assert "RTX" in h.env_badge(Env(True, True, "RTX 4070", 12000)) and "Docker ✓" in h.env_badge(Env(True, True, "RTX 4070", 12000))
    assert S.NO_GPU in h.env_badge(Env(False, False, None, None)) and "Docker ✗" in h.env_badge(Env(False, False, None, None))


def test_env_probe_runs_once_in_background():
    from omnivoice.train import Env
    calls = []
    gate = threading.Event()
    def detect():
        calls.append(1); gate.wait(5); return Env(True, False, None, None)
    probe = h.EnvProbe(detect)
    assert probe.env is None and not probe.done
    probe.start(); probe.start()
    gate.set(); probe.join(5)
    assert probe.done and probe.env.docker and len(calls) == 1


def test_env_probe_survives_errors():
    def detect():
        raise RuntimeError("boom")
    probe = h.EnvProbe(detect)
    probe.start(); probe.join(5)
    assert probe.done and probe.env is not None and not probe.env.docker


class _P:
    name = "glados"


def test_train_runner_streams_lines_and_epoch():
    seen = {}
    def fake_train(p, epochs, resume, on_line, batch, env, should_stop):
        seen.update(epochs=epochs, resume=resume, batch=batch)
        on_line("Epoch 7: 50%| 3/6")
        on_line("Epoch 8: 10%| 1/6")
        return 0
    r = h.TrainRunner(train_fn=fake_train)
    r.start(_P(), epochs=5, resume=True, batch=8, env=None)
    r.join(5)
    assert seen == {"epochs": 5, "resume": True, "batch": 8}
    assert r.epoch == 8 and r.status == "done"
    assert "Эпоха 7/?" in r.log_text()


def test_train_runner_error_and_busy():
    from omnivoice.train import TrainError
    gate = threading.Event()
    def slow(p, epochs, resume, on_line, batch, env, should_stop):
        gate.wait(5); raise TrainError("нет докера")
    r = h.TrainRunner(train_fn=slow)
    r.start(_P(), 1, False, None, None)
    with pytest.raises(RuntimeError):
        r.start(_P(), 1, False, None, None)
    gate.set(); r.join(5)
    assert r.status == "error" and "нет докера" in r.log_text()


def test_train_runner_stop_calls_docker_stop():
    gate = threading.Event()
    calls = []
    def slow(p, epochs, resume, on_line, batch, env, should_stop):
        gate.wait(5); return 137
    def fake_run(cmd, **kw):
        calls.append(cmd); gate.set()
        class R: returncode = 0
        return R()
    r = h.TrainRunner(train_fn=slow, run=fake_run)
    r.start(_P(), 1, True, None, None)
    r.stop(grace=0.1)  # a run that ignores the request (e.g. started by an older omnivoice) is killed
    r.join(5)
    assert calls == [["docker", "stop", "omnivoice-train-glados"]]
    assert r.status == "stopped"


def test_train_runner_stop_when_idle_is_noop():
    r = h.TrainRunner(train_fn=lambda *a, **k: 0, run=lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    r.stop()
    assert r.status == "idle"


def test_code_label_falls_back_to_raw_code():
    assert h.code_label("too_long") == "слишком длинная"
    assert h.code_label("weird_code") == "weird_code"
    assert h.flags_text(["check", "weird_code"]) == "⚑ проверить ⚑ weird_code"


def test_project_locks_second_acquire_names_operation(tmp_path):
    locks = h.ProjectLocks()
    locks.acquire(tmp_path / "p", S.OP_SLICE)
    with pytest.raises(h.ProjectBusy) as e:
        locks.acquire(tmp_path / "p" / ".." / "p", S.OP_SAVE)  # same project, different spelling
    assert str(e.value) == S.PROJECT_BUSY.format(op=S.OP_SLICE)
    locks.acquire(tmp_path / "other", S.OP_SAVE)  # other projects are independent
    locks.release(tmp_path / "p")
    with locks.hold(tmp_path / "p", S.OP_CHECK):
        assert locks.busy(tmp_path / "p") == S.OP_CHECK
    assert locks.busy(tmp_path / "p") is None


def test_project_locks_hold_releases_on_error(tmp_path):
    locks = h.ProjectLocks()
    with pytest.raises(ValueError):
        with locks.hold(tmp_path, S.OP_PACK):
            raise ValueError("x")
    locks.acquire(tmp_path, S.OP_PACK)


def test_train_runner_stop_before_container_launch():
    """Stop during download/image build: the event makes train_project bail out before docker run."""
    from omnivoice.train import STOPPED
    gate, launched = threading.Event(), []
    def train_fn(p, epochs, resume, on_line, batch, env, should_stop):
        if should_stop():           # after the csv
            return STOPPED
        gate.wait(5)                # "downloading the checkpoint"
        if should_stop():
            return STOPPED
        launched.append(1)
        return 0
    def fake_run(cmd, **kw):        # docker stop fails: no container yet
        gate.set()
        raise OSError("no such container")
    r = h.TrainRunner(train_fn=train_fn, run=fake_run)
    r.start(_P(), 1, True, None, None)
    r.stop(grace=0.1)
    r.join(5)
    assert launched == [] and r.code == STOPPED and r.status == "stopped"


def test_train_runner_releases_prepared_once():
    calls = []
    def train_fn(p, epochs, resume, on_line, batch, env, should_stop):
        should_stop(); should_stop(); return 0
    r = h.TrainRunner(train_fn=train_fn)
    r.start(_P(), 1, True, None, None, on_prepared=lambda: calls.append(1))
    r.join(5)
    assert calls == [1]


def test_train_runner_releases_prepared_on_early_error():
    calls = []
    def train_fn(p, epochs, resume, on_line, batch, env, should_stop):
        raise RuntimeError("нет фраз")
    r = h.TrainRunner(train_fn=train_fn)
    r.start(_P(), 1, True, None, None, on_prepared=lambda: calls.append(1))
    r.join(5)
    assert calls == [1] and r.status == "error"


def test_train_runner_logs_download_progress_every_5_percent():
    r = h.TrainRunner(train_fn=lambda *a, **k: 0)
    for done in range(0, 101):
        r._download_progress(done, 100)
    lines = r.log_text().splitlines()
    assert lines[0] == S.TRAIN_DOWNLOAD.format(pct=0) and lines[-1] == S.TRAIN_DOWNLOAD.format(pct=100)
    assert len(lines) == 21


def test_default_train_passes_progress(monkeypatch):
    from omnivoice import train
    seen = {}
    monkeypatch.setattr(train, "train_project", lambda p, **kw: seen.update(kw) or 0)
    r = h.TrainRunner()
    r.start(_P(), 3, True, 8, None)
    r.join(5)
    assert seen["progress"] == r._download_progress and callable(seen["should_stop"]) and seen["epochs"] == 3


@pytest.mark.parametrize("value", ["", "   ", None])
def test_install_target_required(value):
    with pytest.raises(ValueError, match=S.INSTALL_NO_TARGET):
        h.check_install_target(value)


def test_install_target_must_be_absolute_and_exist(tmp_path):
    with pytest.raises(ValueError) as e:
        h.check_install_target("relative/models")
    assert str(e.value) == S.TARGET_NOT_ABSOLUTE
    missing = tmp_path / "nope"
    with pytest.raises(ValueError) as e:
        h.check_install_target(f"  {missing}  ")
    assert str(e.value) == S.TARGET_NOT_FOUND.format(path=missing)
    assert not missing.exists()
    assert h.check_install_target(f" {tmp_path} ") == tmp_path


def test_apply_edits_turns_line_breaks_into_spaces():
    segs = [Segment("a", "", 2.0)]
    assert h.apply_edits(segs, [["a", "раз\rдва\r\nтри", 2.0, "", False]]) == 1
    assert segs[0].text == "раз два три"


def test_train_runner_stop_asks_first_then_kills_a_stuck_run(monkeypatch, tmp_path):
    from omnivoice import train
    monkeypatch.setitem(train._ACTIVE, "omnivoice-train-glados", "wsl")
    gate, calls = threading.Event(), []
    p = _NS(name="glados", train_dir=tmp_path / "train")
    def graceful(p, epochs, resume, on_line, batch, env, should_stop):
        for _ in range(500):  # fit.py: stops after its batch once the request file appears
            if (p.train_dir / train.STOP_FILE).exists():
                time.sleep(0.5)  # finishing the batch and saving last.ckpt
                return 0
            time.sleep(0.01)
        return 1
    r = h.TrainRunner(train_fn=graceful, run=lambda cmd, **kw: calls.append(cmd))
    r.start(p, 1, True, None, None)
    r.stop(grace=5)
    assert r.status_text() == S.TRAIN_STOPPING  # still saving: not «stopped» yet
    r.join(5)
    assert calls == [] and r.status == "stopped"  # stopped by itself: no kill
    assert r.log_text().splitlines()[-1] == S.TRAIN_STOPPED


def test_train_runner_stop_on_wsl_runs_pkill(monkeypatch):
    from omnivoice import train, wslenv
    monkeypatch.setitem(train._ACTIVE, "omnivoice-train-glados", "wsl")  # train_project chose WSL
    gate, calls = threading.Event(), []
    def slow(p, epochs, resume, on_line, batch, env, should_stop):
        gate.wait(5); return 130
    def fake_run(cmd, **kw):
        calls.append(cmd); gate.set()
        class R: returncode = 0
        return R()
    r = h.TrainRunner(train_fn=slow, run=fake_run)
    r.start(_P(), 1, True, None, None)
    r.stop(grace=0.1)  # the request is ignored (no fit.py): killed after the grace period
    r.join(5)
    assert calls == [wslenv.wsl_cmd("pkill", "-f", "piper_compat/fit.py|piper.train")] and r.status == "stopped"


def test_env_badge_shows_wsl_backend():
    from omnivoice.train import Env
    badge = h.env_badge(Env(False, True, "RTX 4070", 12000, backend="wsl"))
    assert "RTX 4070" in badge and S.WSL_OK in badge and S.DOCKER_NO not in badge


def test_env_badge_wsl_without_gpu():
    from omnivoice.train import Env
    badge = h.env_badge(Env(False, False, "RTX 4070", 12000, backend=None, wsl_ready=True, wsl_gpu=False))
    assert S.WSL_NO_GPU in badge and S.WSL_NO_GPU == "WSL: нет GPU" and S.DOCKER_NO not in badge


# ---------- setup section ----------

def _item(name, ok, detail="d", optional=False):
    from omnivoice.deps import Item
    return Item(name, ok, detail, optional)


def test_checklist_html_rows():
    html = h.checklist_html([_item("ffmpeg", True, "C:/ff<b>"), _item("WSL", False, "не установлен"),
                             _item("Docker", False, "не найден", optional=True)])
    assert html.count('class="ck-row') == 3
    assert 'class="ck-row ok"' in html and "✓" in html and "C:/ff&lt;b&gt;" in html
    assert 'class="ck-row miss"' in html and "✗" in html
    assert 'class="ck-row opt"' in html and S.SETUP_OPTIONAL in html


def test_checklist_html_pending():
    assert S.SETUP_CHECKING in h.checklist_html(None)


def test_needs_setup():
    from omnivoice.train import Env
    assert not h.needs_setup(None)  # still probing: don't nag
    assert h.needs_setup(Env(False, False, "RTX 4070", 12000))
    assert not h.needs_setup(Env(False, False, None, None, backend=None, wsl_ready=True, wsl_gpu=False))
    assert not h.needs_setup(Env(True, True, "RTX", 8000, backend="docker"))


def test_steps_bar_need_setup_chip():
    html = h.steps_bar_html({}, None, need_setup=True)
    assert f'data-section="{S.SEC_SETUP}"' in html and S.SETUP_FIRST.upper() in html
    assert S.SETUP_FIRST.upper() not in h.steps_bar_html({}, None)


def test_nav_sections_start_with_setup():
    assert h.NAV_SECTIONS == (S.SEC_SETUP, *h.SECTIONS[:-1], S.SEC_CKPT, S.SEC_PACK)
    assert h.SECTION_STEP[S.SEC_CKPT] == "train"


def test_setup_progress_parses_steps_and_downloads():
    pr = h.SetupProgress()
    assert pr.pct == 0 and pr.title == ""
    pr.line("Скачиваю ffmpeg…")
    assert pr.title == "Скачиваю ffmpeg…"
    pr.download(25, 100)
    assert pr.pct == 25 and "25%" in pr.title
    pr.line("STEP 3/6 Ставлю torch")
    assert (pr.step, pr.total) == (3, 6) and pr.title == "Ставлю torch" and pr.pct == 33
    pr.line("Collecting numpy")  # an ordinary log line keeps the step title
    assert pr.title == "Ставлю torch"
    html = pr.html()
    assert 'style="width:33%"' in html and "3/6" in html and "Ставлю torch" in html


def test_setup_runner_success_rechecks_and_calls_back():
    seen = []
    def install(on_line, progress):
        on_line("STEP 1/2 Ставлю пакеты"); progress(5, 10); on_line("Готово.")
        return None
    r = h.SetupRunner(install_fn=install, check_fn=lambda: [_item("WSL", True)], on_finish=lambda: seen.append(1))
    r.start(); r.join(5)
    assert r.status == "done" and r.reboot is None and seen == [1]
    assert r.items[0].ok and "Готово." in r.log_text() and r.progress.pct == 100
    assert r.version > 0


def test_setup_runner_reboot_and_errors():
    from omnivoice.deps import DepsError
    r = h.SetupRunner(install_fn=lambda on_line, progress: "Перезагрузи Windows", check_fn=lambda: [])
    r.start(); r.join(5)
    assert r.status == "reboot" and r.reboot == "Перезагрузи Windows"
    assert "Перезагрузи Windows" in r.status_html() and "setup-reboot" in r.status_html()

    def boom(on_line, progress):
        raise DepsError("нет uv")
    r = h.SetupRunner(install_fn=boom, check_fn=lambda: [])
    r.start(); r.join(5)
    assert r.status == "error" and "нет uv" in r.status_html() and "нет uv" in r.log_text()


def test_setup_runner_busy_guard():
    gate = threading.Event()
    r = h.SetupRunner(install_fn=lambda on_line, progress: gate.wait(5) and None, check_fn=lambda: [])
    r.start()
    with pytest.raises(RuntimeError, match=S.SETUP_BUSY):
        r.start()
    gate.set(); r.join(5)
    assert r.status == "done"


def test_setup_runner_check_in_background_survives_errors():
    def bad():
        raise OSError("wsl сломан")
    r = h.SetupRunner(install_fn=lambda *a: None, check_fn=bad)
    assert r.items is None
    r.check(); r.join(5)
    assert r.items == [] and "wsl сломан" in r.status_html()


def test_setup_runner_busy_covers_install_and_check():
    gate = threading.Event()
    r = h.SetupRunner(install_fn=lambda *a: None, check_fn=lambda: gate.wait(5) and [])
    assert not r.busy
    r.check()
    assert r.busy  # the UI timer keeps polling while a background check runs
    gate.set(); r.join(5)
    assert not r.busy


def test_env_probe_restart():
    from omnivoice.train import Env
    n = []
    probe = h.EnvProbe(lambda: n.append(1) or Env(bool(len(n) > 1), False, None, None))
    probe.start(); probe.join(5)
    assert not probe.env.docker
    probe.restart(); probe.join(5)
    assert probe.env.docker and len(n) == 2


def test_needs_setup_without_host_gpu_points_to_colab_not_setup():
    from omnivoice.train import Env
    # no NVIDIA GPU: setup skips the WSL environment, so «Сначала установи зависимости» would never go away
    assert not h.needs_setup(Env(False, False, None, None))


def test_last_epoch_target_matches_lightning_0_based_epochs():
    from types import SimpleNamespace
    from omnivoice import train
    p = SimpleNamespace(base_checkpoint="ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt")
    # the base already did epochs 0..4139; 10 more end with Lightning printing «Epoch 4149»
    assert h.last_epoch_target(p, 10) == train.target_epochs(p, 10) - 1 == 4149
    assert h.last_epoch_target(SimpleNamespace(base_checkpoint="x.ckpt"), 5) == 5


def test_setup_intro_disk_size():
    assert "~15 ГБ" in S.SETUP_INTRO and "6 ГБ" not in S.SETUP_INTRO
    assert "диске C:" not in S.SETUP_INTRO  # the folder is configurable now


def test_app_uses_last_epoch_target():
    import inspect
    from omnivoice.ui import app as ui_app
    src = inspect.getsource(ui_app)
    assert "target=last_epoch_target(p, n_epochs)" in src and "base_epoch(p) + n_epochs" not in src


def test_setup_runner_done_without_gpu_is_not_missing():
    from omnivoice import deps
    items = [deps.Item(deps.PREP, True, "установлены"), deps.Item(deps.FFMPEG, True, "ffmpeg.exe"),
             deps.Item(deps.WSL, False, deps.NO_GPU_DETAIL, optional=True),
             deps.Item(deps.ENV, False, deps.NO_GPU_DETAIL, optional=True)]
    r = h.SetupRunner(install_fn=lambda on_line, progress: on_line(deps.NO_GPU_DETAIL), check_fn=lambda: items)
    r.start(); r.join(5)
    html = r.status_html()
    assert S.SETUP_DONE in html and S.SETUP_DONE_MISSING not in html
    assert deps.NO_GPU_DETAIL in r.log_text() and deps.NO_GPU_DETAIL in h.checklist_html(r.items)


# ---------- dependency folder ----------
from collections import namedtuple

_Usage = namedtuple("_Usage", "total used free")


def test_data_dir_html_shows_path_and_free_space():
    out = h.data_dir_html(Path("G:/omnivoice"), "config", disk_usage=lambda p: _Usage(10**12, 0, 150 * 2**30))
    assert "150,0 ГБ" in out and "G:" in out


def test_data_dir_html_env_and_unavailable_drive():
    out = h.data_dir_html(Path("C:/x"), "env", disk_usage=lambda p: _Usage(1, 0, 2**30))
    assert "OMNIVOICE_CACHE" in out
    def gone(p):
        raise OSError("нет диска")
    assert S.DATA_DIR_NO_DRIVE.split("{")[0] in h.data_dir_html(Path("Q:/x"), "config", disk_usage=gone)


def test_data_dir_html_escapes():
    out = h.data_dir_html(Path("C:/<b>"), "default", disk_usage=lambda p: _Usage(1, 0, 1))
    assert "<b>" not in out


def test_setup_runner_runs_a_custom_job_with_its_own_done_text():
    seen = []
    r = h.SetupRunner(install_fn=lambda *a: (_ for _ in ()).throw(AssertionError("no install")),
                      check_fn=lambda: [], on_finish=lambda: seen.append(1))
    def job(on_line, progress):
        on_line("Копирую checkpoints…")
        return None
    r.start(job=job, done_text="Перенесено")
    r.join(5)
    assert r.status == "done" and "Перенесено" in r.status_html() and seen == [1]
    assert "Копирую checkpoints…" in r.log_text()
    r.start(job=lambda on_line, progress: (_ for _ in ()).throw(RuntimeError("Мало места")),
            done_text="Перенесено", error_title="Перенос не удался")
    r.join(5)
    assert r.status == "error" and "Перенос не удался: Мало места" in r.status_html()
    r.start(); r.join(5)  # the next plain run uses install_fn and the usual wording again
    assert r.status == "error" and S.SETUP_ERROR in r.status_html()

def test_data_dir_hint_has_single_colon(tmp_path):
    from omnivoice.ui import helpers
    out = helpers.data_dir_html(tmp_path, "config")
    assert "::" not in out and tmp_path.drive in out


# ---------- training section: clean log, train.log, checkpoints, disk ----------
from types import SimpleNamespace as _NS

_BAR = "█" * 10


def _epoch(n, mos):
    return [f"Epoch {n}: 100%|{_BAR}| 3/3 [00:01<00:00, 1.70it/s, v_num=1]",
            "\x1b[A", "Validation: |          | 0/? [00:00<?, ?it/s]\x1b[A",
            f"Validation DataLoader 0: 100%|{_BAR}| 1/1 [00:00<00:00, 12.01it/s]",
            f"Epoch {n}: 100%|{_BAR}| 3/3 [00:03<00:00, 0.27it/s, v_num=1, val_mos={mos}]"]


def test_train_runner_clean_log_raw_file_and_status(tmp_path):
    p = _NS(name="glados", train_dir=tmp_path / "train")
    t = [0.0]
    def fake_train(p, epochs, resume, on_line, batch, env, should_stop):
        on_line("/x/torch/jit/_script.py:1491: FutureWarning: deprecated")
        for n, mos in ((4140, "2.360"), (4141, "2.410")):
            for line in _epoch(n, mos):
                on_line(line)
            t[0] += 30
        return 0
    r = h.TrainRunner(train_fn=fake_train, clock=lambda: t[0])
    r.start(p, epochs=10, resume=True, batch=8, env=None, target=4149, offset=4139)
    r.join(5)
    r.metrics = {4140: {"val_mel": 0.39}}
    log = r.log_text().splitlines()
    assert log[0] == S.TRAIN_STARTED.format(epochs=10, batch=8)
    assert "Эпоха 1/10 · качество (MOS) 2.36 · mel 0.39 · 1.7 ит/с" in log
    assert "Эпоха 2/10 · качество (MOS) 2.41 · 1.7 ит/с" in log
    assert log[-1] == S.TRAIN_DONE and "Warning" not in r.log_text()
    raw = (p.train_dir / "train.log").read_text(encoding="utf-8")
    assert "FutureWarning" in raw and "val_mos=2.410" in raw and "\x1b[A" in raw
    assert r.log_path == p.train_dir / "train.log"


def test_train_runner_status_has_time_per_epoch_and_eta():
    gate = threading.Event()
    t = [0.0]
    def slow(p, epochs, resume, on_line, batch, env, should_stop):
        for n in (4140, 4141, 4142):
            for line in _epoch(n, "2.0"):
                on_line(line)
            t[0] += 30
        gate.wait(5)
        return 0
    r = h.TrainRunner(train_fn=slow, clock=lambda: t[0])
    r.start(_P(), epochs=10, resume=True, batch=None, env=None, target=4149, offset=4139)
    for _ in range(100):
        if "осталось" in r.status_text():
            break
        threading.Event().wait(0.02)
    s = r.status_text()
    gate.set(); r.join(5)
    assert s == S.TRAIN_RUNNING.format(epoch=3, target=10) + S.TRAIN_TIMING.format(per="30 с", eta="3 мин 30 с")


def test_train_runner_reports_new_checkpoints(tmp_path):
    p = _NS(name="glados", train_dir=tmp_path / "train")
    d = p.train_dir / "lightning_logs" / "version_0" / "checkpoints"
    d.mkdir(parents=True)
    (d / "epoch=4140-val_mel=0.6000.ckpt").write_bytes(b"x")  # from an earlier run: not reported
    gate = threading.Event()
    r = h.TrainRunner(train_fn=lambda *a, **k: gate.wait(5) and 0)
    r.start(p, epochs=10, resume=True, batch=None, env=None, target=4149, offset=4139)
    (d / "epoch=4204-val_mel=0.3482.ckpt").write_bytes(b"x")
    (d / "epoch=4204-val_mos=2.3630.ckpt").write_bytes(b"x")
    (d / "last.ckpt").write_bytes(b"x")
    r.poll_checkpoints(); r.poll_checkpoints()
    gate.set(); r.join(5)
    saved = [l for l in r.log_text().splitlines() if l.startswith("Сохранён")]
    assert saved == [S.CKPT_SAVED.format(what="эпоха 65 · MOS 2.36 · mel 0.348")]


def test_train_runner_stopped_does_not_count_the_broken_epoch():
    gate = threading.Event()
    def slow(p, epochs, resume, on_line, batch, env, should_stop):
        on_line(f"Epoch 5: 40%|{_BAR[:4]}      | 2/5 [00:01<00:01, 1.70it/s, v_num=1]")
        gate.wait(5)
        return 137
    r = h.TrainRunner(train_fn=slow, run=lambda *a, **k: gate.set())
    r.start(_P(), 10, True, None, None, target=9, offset=0)
    r.stop(grace=0.1); r.join(5)
    assert "Эпоха" not in r.log_text() and r.log_text().splitlines()[-1] == S.TRAIN_STOPPED


def test_nav_without_project_keeps_only_setup_and_new():
    assert h.nav_choices(False) == [S.SEC_SETUP, S.SEC_NEW]
    assert h.nav_choices(True) == [*h.NAV_SECTIONS, S.SEC_NEW, S.SEC_DELETE]


def test_delete_page_parts_and_confirmation(tmp_path):
    from omnivoice.project import Project
    p = Project.create(tmp_path / "Arthas_2", name="Arthas 2", language="ru")
    (p.train_dir / "a.ckpt").write_bytes(b"x" * 2048)
    out = h.delete_parts_html(p)
    assert "Arthas 2" in out and S.DELETE_PART_TRAIN in out and "2,0 КБ" in out
    assert h.delete_confirmed(p, " arthas 2 ") and h.delete_confirmed(p, "Arthas_2")
    assert not h.delete_confirmed(p, "") and not h.delete_confirmed(p, None) and not h.delete_confirmed(p, "Arthas")


def test_delete_raw_file_stays_inside_raw(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.wav").write_bytes(b"x")
    (tmp_path / "keep.wav").write_bytes(b"x")
    with pytest.raises(ValueError):
        h.delete_raw_file(tmp_path / "raw", "../keep.wav")
    with pytest.raises(ValueError):
        h.delete_raw_file(tmp_path / "raw", "missing.wav")
    h.delete_raw_file(tmp_path / "raw", "a.wav")
    assert h.raw_files(tmp_path / "raw") == [] and (tmp_path / "keep.wav").exists()
    assert h.language_choices() == [(S.LANG_RU, "ru"), (S.LANG_EN, "en")]


def test_steps_bar_disabled_leads_nowhere():
    out = h.steps_bar_html({}, None, disabled=True)
    assert out.count('class="st off"') == 6 and "data-section" not in out


def test_base_choices_per_language():
    choices, value = h.base_choices("ru")
    assert [n for _l, n in choices] == ["denis", "dmitri", "ruslan", "irina"] and value == "irina"
    assert ("ruslan · " + S.BASE_MALE, "ruslan") in choices and ("irina · " + S.BASE_FEMALE, "irina") in choices
    en, en_default = h.base_choices("en")
    assert en_default == "lessac" and [n for _l, n in en] == ["hfc_male", "joe", "ryan", "amy", "hfc_female", "lessac"]
    assert sum(label.endswith(S.BASE_MALE) for label, _n in en) == 3


def test_every_base_has_gender_and_epoch():
    import re
    from omnivoice import languages
    for name, ck in languages.BASE_CHECKPOINTS.items():
        assert name in languages.BASE_GENDER and re.search(r"epoch=\d+", ck), name


def test_base_sample_url_and_cache(tmp_path, monkeypatch):
    from omnivoice import checkpoints, languages
    ck = languages.BASE_CHECKPOINTS["ruslan"]
    assert checkpoints.sample_url(ck) == ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                                          "ru/ru_RU/ruslan/medium/samples/speaker_0.mp3")
    got = {}
    monkeypatch.setattr(checkpoints, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(checkpoints.download, "fetch", lambda url, target, **kw: got.update(url=url, target=target) or target)
    assert checkpoints.sample(ck) == tmp_path / "samples" / "ru/ru_RU/ruslan/medium.mp3"
    assert got["url"] == checkpoints.sample_url(ck)


def test_ckpt_table_sorts_marks_and_keys(tmp_path):
    rows = [_NS(path=tmp_path / "a.ckpt", epoch=4140, mos=3.98, mel=0.68, best_mos=True, best_mel=False,
                last=False, old_last=False),
            _NS(path=tmp_path / "last.ckpt", epoch=4211, mos=2.24, mel=None, best_mos=False, best_mel=False,
                last=True, old_last=False),
            _NS(path=tmp_path / "b.ckpt", epoch=4204, mos=None, mel=0.3482, best_mos=False, best_mel=True,
                last=False, old_last=False),
            _NS(path=tmp_path / "c.ckpt", epoch=4211, mos=2.5, mel=0.5, best_mos=False, best_mel=False,
                last=False, old_last=False)]
    table, keys, best = h.ckpt_table(rows, offset=4139)
    assert best == str(tmp_path / "a.ckpt")
    assert table == [[1, "3.98", "0.680", S.CKPT_BEST_MOS], [72, "2.50", "0.500", ""], [72, "2.24", "", S.CKPT_LAST],
                     [65, "", "0.348", S.CKPT_BEST_MEL]]
    assert [r[0] for r in h.ckpt_table(rows, 4139, S.CKPT_SORT_MEL)[0]] == [65, 72, 1, 72]
    assert [r[0] for r in h.ckpt_table(rows, 4139, S.CKPT_SORT_EPOCH)[0]] == [72, 72, 65, 1]
    # a last.ckpt sharing its epoch with a named file stays a separate, clickable row
    assert keys[h.ckpt_key_of_row(table[2])] == str(tmp_path / "last.ckpt")
    assert keys[h.ckpt_key_of_row(table[1])] == str(tmp_path / "c.ckpt")
    marked = h.ckpt_table(rows, 4139, None, str(tmp_path / "last.ckpt"))[0]
    assert marked[2][3] == S.CKPT_SELECTED + " · " + S.CKPT_LAST
    assert keys[h.ckpt_key_of_row(marked[2])] == str(tmp_path / "last.ckpt")
    assert h.ckpt_key_of_row(["x"]) is None and h.ckpt_table([], 0) == ([], {}, None)


def test_disk_html():
    out = h.disk_html(train_bytes=19 << 30, n_ckpt=24, extra_bytes=15 << 30, n_extra=21)
    assert "19,0 ГБ" in out and "24" in out and "15,0 ГБ" in out
    assert S.DISK_NOTHING_EXTRA in h.disk_html(1 << 30, 3, 0, 0)


def test_phrase_cards_meta_and_filter():
    a = _NS(id="arthas_0001", text="Во славу плети!", duration=2.25, flags=["check"], dropped=False)
    b = _NS(id="arthas_0002", text="Полегче!", duration=1.3, flags=[], dropped=True)
    meta = h.phrase_meta_html(a)
    assert "arthas_0001" in meta and S.PHRASE_SECONDS.format(v=2.25) in meta and h.code_label("check") in meta
    assert S.PHRASE_DROPPED_CHIP in h.phrase_meta_html(b) and S.PHRASE_DROPPED_CHIP not in meta
    assert h.shown_phrases([a, b]) == [a, b] and h.shown_phrases([a, b], only_flagged=True) == [a]
