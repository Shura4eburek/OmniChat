import numpy as np
import soundfile as sf
from omnivoice.piper_compat import xtts_gen


def test_run_job_writes_resampled_wavs_skips_existing_and_reports(tmp_path):
    (tmp_path / "synth_0002.wav").write_bytes(b"done before")
    job = {"language": "ru", "sample_rate": 22050, "refs": ["/r.wav"], "out_dir": str(tmp_path),
           "stop_file": str(tmp_path / "STOP"),
           "items": [{"id": "synth_0001", "text": "раз"}, {"id": "synth_0002", "text": "два"},
                     {"id": "synth_0003", "text": "boom"}]}
    said, lines = [], []

    def synthesize(text, refs):
        said.append(text)
        if text == "boom":
            raise RuntimeError("cuda oom")
        return np.zeros(24000, np.float32), 24000

    assert xtts_gen.run_job(job, synthesize, out=lines.append) == 0
    assert said == ["раз", "boom"]                                   # synth_0002 already there
    info = sf.info(str(tmp_path / "synth_0001.wav"))
    assert info.samplerate == 22050 and info.channels == 1 and info.subtype == "PCM_16"
    assert lines[0] == "ITEM 1/3 synth_0001" and lines[1].startswith("FAIL synth_0003 cuda oom")
    assert not list(tmp_path.glob("*.part"))


def test_run_job_stops_on_the_stop_file(tmp_path):
    job = {"language": "ru", "sample_rate": 22050, "refs": [], "out_dir": str(tmp_path),
           "stop_file": str(tmp_path / "STOP"), "items": [{"id": f"synth_{i:04d}", "text": "а"} for i in range(1, 4)]}

    def synthesize(text, refs):
        (tmp_path / "STOP").write_text("")
        return np.zeros(100, np.float32), 22050

    assert xtts_gen.run_job(job, synthesize, out=lambda s: None) == 0
    assert [f.name for f in tmp_path.glob("synth_*.wav")] == ["synth_0001.wav"]
