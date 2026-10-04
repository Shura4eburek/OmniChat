import json
from omnivoice import synth, teacher, wslenv
from omnivoice.project import Project


def test_job_and_command(tmp_path):
    p = Project.create(tmp_path / "a", name="a", language="ru")
    (p.segments_dir / "s1.wav").write_bytes(b"x")
    st = synth.SynthState(["s1"], [synth.SynthItem("synth_0001", "раз", "corpus"),
                                    synth.SynthItem("synth_0002", "два", "corpus", status="done")])
    t = teacher.XttsTeacher()
    job = json.loads(t.write_job(p, st).read_text(encoding="utf-8"))
    assert job["refs"] == [wslenv.wsl_path((p.segments_dir / "s1.wav").resolve())]
    assert [i["id"] for i in job["items"]] == ["synth_0001"]                 # only what is pending
    assert job["stop_file"].endswith("/synth/STOP") and job["sample_rate"] == 22050
    cmd = t.command(p.synth_dir / "job.json")
    assert cmd[:7] == wslenv.wsl_cmd(teacher.XTTS_PY)[:7] and cmd[-1].endswith("/synth/job.json")
    assert cmd[-2] == wslenv.wsl_path(teacher.GEN_SCRIPT)


def test_generate_streams_lines_and_stop_request(tmp_path):
    p = Project.create(tmp_path / "a", name="a", language="ru")
    st = synth.SynthState([], [synth.SynthItem("synth_0001", "раз", "corpus")])

    class Proc:
        stdout = iter([b"ITEM 1/1 synth_0001\n"])
        def wait(self): return 0

    seen = []
    assert teacher.XttsTeacher().generate(p, st, seen.append, popen=lambda *a, **k: Proc()) == 0
    assert seen == ["ITEM 1/1 synth_0001"]
    teacher.XttsTeacher().request_stop(p)
    assert (p.synth_dir / teacher.STOP_FILE).exists()
