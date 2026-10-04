import numpy as np
import pytest
from omnivoice import audio, dataset, synth
from omnivoice.dataset import Segment
from omnivoice.project import Project, STEPS


def project(tmp_path, durations=(4.0, 6.0, 2.0, 8.0, 13.0)):
    p = Project.create(tmp_path / "a", name="a", language="ru")
    segs = []
    for i, d in enumerate(durations):
        audio.write_wav(p.segments_dir / f"s{i}.wav", np.zeros(int(audio.SR * d), np.float32))
        segs.append(Segment(f"s{i}", "раз два три четыре пять шесть"[: 10 + i], d))
    dataset.save(p, segs)
    return p


def test_steps_and_dir(tmp_path):
    assert STEPS.index("synth") == STEPS.index("check") + 1 < STEPS.index("train")
    assert Project.create(tmp_path / "b", name="b", language="ru").synth_dir.name == "synth"


def test_choose_refs_and_rate(tmp_path):
    segs = dataset.load(project(tmp_path))
    refs = synth.choose_refs(segs)
    assert refs == ["s3", "s1", "s0"]                   # 3–12 s, longest first, ≤ 30 s, flagged/dropped skipped
    assert synth.choose_refs([]) == [] and synth.speech_rate([]) == 14.0
    segs[3].flags = ["check"]
    assert "s3" not in synth.choose_refs(segs)


def test_plan_lines_and_roundtrip(tmp_path):
    p = project(tmp_path)
    synth.save_lines(p, "Ты не надейся на быструю смерть!\n   \n")
    st = synth.make_plan(p, minutes=0.2, refs=["s1"])
    assert st.items[0].text == "Ты не надейся на быструю смерть!" and st.items[0].source == "user"
    assert all(i.status == "pending" and i.id.startswith("synth_") for i in st.items)
    synth.save(p, st)
    again = synth.load(p)
    assert again.items == st.items and again.refs == ["s1"] and again.weight == 3


def test_sync_check_manual_and_training(tmp_path):
    p = project(tmp_path)
    st = synth.make_plan(p, minutes=6, refs=["s1"])   # ~1.8 chars/s, corpus lines ~100 chars: 6 min ≈ 6 phrases
    a, b, c = st.items[:3]
    for it, sec in ((a, 2.0), (b, 2.0), (c, 0.3)):
        synth.wav(p, it.id).parent.mkdir(parents=True, exist_ok=True)
        audio.write_wav(synth.wav(p, it.id), (0.2 * np.sin(np.arange(int(audio.SR * sec)) / 9)).astype(np.float32))
    st = synth.sync_generated(p, st)
    assert [i.status for i in st.items[:3]] == ["done"] * 3 and st.items[3].status == "pending"
    heard = {a.id: a.text, b.id: "что-то совсем другое и не то", c.id: c.text}
    st = synth.apply_check(p, st, lambda wav: heard[wav.stem])
    v = {i.id: (i.verdict, i.dropped) for i in st.items[:3]}
    assert v[a.id][1] is (v[a.id][0] != "accepted") and v[b.id] == ("rejected", True) and v[c.id] == ("rejected", True)
    synth.save(p, st)
    st = synth.set_manual(p, b.id, "accept")
    st = synth.apply_check(p, st, lambda wav: heard[wav.stem])      # a re-check keeps the manual decision
    assert next(i for i in st.items if i.id == b.id).dropped is False
    synth.save(p, st)
    ids = {i.id for i in synth.training_items(p)}
    assert b.id in ids and c.id not in ids and (a.id in ids) == (not next(i for i in st.items if i.id == a.id).dropped)
    s = synth.summary(st)
    assert s["rejected"] == 1 and s["pending"] == len(st.items) - 3


def test_plan_keeps_done_and_manual(tmp_path):
    p = project(tmp_path)
    st = synth.make_plan(p, minutes=0.1, refs=["s1"])
    first = st.items[0]
    synth.wav(p, first.id).parent.mkdir(parents=True, exist_ok=True)
    audio.write_wav(synth.wav(p, first.id), np.zeros(audio.SR * 2, np.float32))
    st = synth.sync_generated(p, st); first = st.items[0]; first.manual = "drop"; synth.save(p, st)
    st2 = synth.make_plan(p, minutes=0.1, refs=["s1"])                # same refs: kept
    kept = next(i for i in st2.items if i.text == first.text)
    assert kept.status == "done" and kept.manual == "drop"
    st3 = synth.make_plan(p, minutes=0.1, refs=["s0"])                # other refs: regenerate, manual kept
    redo = next(i for i in st3.items if i.text == first.text)
    assert redo.status == "pending" and redo.manual == "drop" and not synth.wav(p, redo.id).exists()


def test_no_synth_means_no_training_items(tmp_path):
    assert synth.training_items(project(tmp_path)) == []
    assert synth.load(project(tmp_path / "x")).items == []
