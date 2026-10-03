import pytest
gr = pytest.importorskip("gradio")
from omnivoice.ui.app import build
from omnivoice.project import Project


def test_build_lists_projects(tmp_path):
    Project.create(tmp_path / "glados", name="glados", language="ru")
    demo = build(tmp_path)
    assert isinstance(demo, gr.Blocks)


def test_strings_have_no_empty_values():
    from omnivoice.ui import strings
    assert all(isinstance(v, str) and v for k, v in vars(strings).items() if k.isupper())


def test_build_does_not_probe_env(tmp_path, monkeypatch):
    from omnivoice import train
    def boom(*a, **k):
        raise AssertionError("detect_env must not run inside build()")
    monkeypatch.setattr(train, "detect_env", boom)
    assert isinstance(build(tmp_path), gr.Blocks)


def test_theme_and_css_present():
    from omnivoice.ui import theme
    assert isinstance(theme.THEME, gr.themes.Base)
    assert ".hud-panel" in theme.CSS and "::before" in theme.CSS and ".st.done" in theme.CSS


def test_upload_and_export_hold_project_lock():
    import inspect, re
    from omnivoice.ui import app as ui_app
    src = inspect.getsource(ui_app.build)
    for fn, op in (("on_upload", "OP_UPLOAD"), ("on_export", "OP_EXPORT")):
        body = re.search(rf"def {fn}\(.*?(?=\n        @|\n        def |\n        [a-z_]+\.(click|upload)\()", src, re.S).group(0)
        assert f"with locked(name, S.{op})" in body, fn


def test_build_survives_corrupt_review_json(tmp_path):
    from omnivoice import dataset
    from omnivoice.dataset import Segment
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    dataset.save(p, [Segment("a", "x", 1.0)])
    p.review_json.write_text("{broken", encoding="utf-8")
    assert isinstance(build(tmp_path), gr.Blocks)


def test_build_has_setup_section_first_and_does_not_check_deps(tmp_path):
    def boom(*a, **k):
        raise AssertionError("check_all / install_all must not run inside build()")
    demo = build(tmp_path, check_fn=boom, install_fn=boom)
    radios = [b for b in demo.blocks.values() if isinstance(b, gr.Radio)]
    from omnivoice.ui import strings as S
    assert any(r.choices and r.choices[0][0] == S.SEC_SETUP for r in radios)
    buttons = [b.value for b in demo.blocks.values() if isinstance(b, gr.Button)]
    assert S.SETUP_INSTALL in buttons and S.SETUP_GOTO in buttons


def test_setup_timer_starts_inactive(tmp_path):
    demo = build(tmp_path, check_fn=lambda: [], install_fn=lambda *a: None)
    idle = [t for t in demo.blocks.values() if isinstance(t, gr.Timer) and not t.active]
    assert [t.value for t in idle] == [1.0]  # only the setup timer, activated by a setup run or check


def test_setup_section_has_data_dir_box_above_install(tmp_path, monkeypatch):
    from omnivoice.ui import strings as S
    monkeypatch.delenv("OMNIVOICE_CACHE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    demo = build(tmp_path, check_fn=lambda: [], install_fn=lambda *a: None)
    blocks = list(demo.blocks.values())
    box = next(b for b in blocks if isinstance(b, gr.Textbox) and b.label == S.DATA_DIR)
    assert box.value == str(tmp_path / "local" / "omnivoice")
    move = next(b for b in blocks if isinstance(b, gr.Button) and b.value == S.DATA_DIR_MOVE)
    install = next(b for b in blocks if isinstance(b, gr.Button) and b.value == S.SETUP_INSTALL)
    assert box._id < move._id < install._id


def test_slice_and_transcribe_show_progress_on_their_message_only(tmp_path):
    from omnivoice.ui import strings as S
    demo = build(tmp_path)
    cfg = demo.get_config_file()
    btn = {b.value: b._id for b in demo.blocks.values() if isinstance(b, gr.Button)}
    for label in (S.SLICE, S.TRANSCRIBE):
        dep = next(d for d in cfg["dependencies"] if [btn[label], "click"] in [list(t) for t in d["targets"]])
        assert dep["show_progress_on"] and len(dep["show_progress_on"]) == 1
        assert dep["show_progress_on"][0] == dep["outputs"][0]


def test_slice_message_says_whether_text_was_recognised(monkeypatch, tmp_path):
    from omnivoice.ui import app as ui_app, strings as S
    assert ui_app.slice_message(3, True) == S.SLICED_TEXT.format(n=3)
    assert ui_app.slice_message(3, False) == S.SLICED_NO_TEXT.format(n=3)
    assert ui_app.slice_message(0, True) == S.SLICED_NONE


def _handler(demo, name):
    return next(f.fn for f in demo.fns.values() if getattr(f.fn, "__name__", "") == name)


def test_training_panel_fills_charts_checkpoints_players_and_prunes(tmp_path):
    pytest.importorskip("tensorboard")
    import os, time
    from omnivoice import previews
    from omnivoice.ui import strings as S
    from tests.test_previews import ckpts, piper_events
    p = Project.create(tmp_path / "Arthas", name="Arthas", language="ru")
    logs = p.train_dir / "lightning_logs"
    piper_events(logs / "version_0", [4140, 4141, 4142], mos={4140: 3.98, 4141: 3.5, 4142: 2.2},
                 mel={4140: 0.68, 4141: 0.6, 4142: 0.55})
    d = ckpts(p, "version_0", ["epoch=4140-val_mos=3.9800.ckpt", "epoch=4141-val_mos=3.5000.ckpt",
                               "epoch=4142-val_mel=0.5500.ckpt", "last.ckpt"])
    old = time.time() - 600
    for f in list(d.iterdir()) + list(logs.rglob("events*")):
        os.utime(f, (old, old))
    demo = build(tmp_path)
    out = _handler(demo, "on_refresh")("Arthas", S.SEC_TRAIN, None)
    msg, status, mos, mel, chart_note, log_note, dd, disk, head, *players = out
    assert list(mos["epoch"]) == [1, 2, 3] and list(mel["epoch"]) == [1, 2, 3]
    assert dd["value"] == str(d / "epoch=4140-val_mos=3.9800.ckpt")
    assert S.CKPT_BEST_MOS in dd["choices"][0][0] and dd["choices"][0][0].startswith("эпоха 1 · MOS 3.98")
    assert "Эпоха 1" in head and players[0]["visible"] and players[0]["label"].startswith("1. Твоя душа")
    assert S.TRAIN_IDLE_DONE.format(n=3) in status and "Лишних: 1" in disk
    # listening to another checkpoint
    _m, head2, *pl2 = _handler(demo, "on_listen")("Arthas", str(d / "epoch=4142-val_mel=0.5500.ckpt"))
    assert "Эпоха 3" in head2 and pl2[4]["visible"]
    # pruning: needs the checkbox, then keeps best MOS + best mel + last.ckpt
    refused = _handler(demo, "on_prune")("Arthas", S.SEC_TRAIN, None, False)
    assert S.PRUNE_NEED_CONFIRM in refused[0] and (d / "epoch=4141-val_mos=3.5000.ckpt").exists()
    done = _handler(demo, "on_prune")("Arthas", S.SEC_TRAIN, None, True)
    assert "Удалено чекпойнтов: 1" in done[0] and done[1] is False
    assert sorted(f.name for f in d.iterdir()) == ["epoch=4140-val_mos=3.9800.ckpt", "epoch=4142-val_mel=0.5500.ckpt",
                                                   "last.ckpt"]
    previews._INDEX.clear()


def test_prune_refused_while_files_are_fresh(tmp_path):
    from omnivoice.ui import strings as S
    from tests.test_previews import ckpts
    p = Project.create(tmp_path / "g", name="g", language="ru")
    d = ckpts(p, "version_0", ["epoch=1-val_mos=2.0000.ckpt", "epoch=2-val_mos=1.0000.ckpt", "last.ckpt"])
    out = _handler(build(tmp_path), "on_prune")("g", S.SEC_TRAIN, None, True)
    assert S.PRUNE_RECENT in out[0] and len(list(d.iterdir())) == 3
