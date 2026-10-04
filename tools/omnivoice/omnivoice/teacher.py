"""The teacher model behind synthetic phrases (spec «Модули»). XttsTeacher writes a job, runs
piper_compat/xtts_gen.py in the WSL venv /opt/omnivoice/xtts and streams its lines."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

from omnivoice import wslenv

XTTS_PY = "/opt/omnivoice/xtts/bin/python"
GEN_SCRIPT = Path(__file__).resolve().parent / "piper_compat" / "xtts_gen.py"
STOP_FILE = "STOP"
STOP_GRACE = 60  # s before a stop turns into a kill


class XttsTeacher:
    name = "xtts"

    def write_job(self, p, state) -> Path:
        p.synth_dir.mkdir(parents=True, exist_ok=True)
        job = {"language": p.language, "sample_rate": p.sample_rate,
               "refs": [wslenv.wsl_path((p.segments_dir / f"{r}.wav").resolve()) for r in state.refs],
               "out_dir": wslenv.wsl_path((p.synth_dir / "wavs").resolve()),
               "stop_file": wslenv.wsl_path((p.synth_dir / STOP_FILE).resolve()),
               "items": [{"id": i.id, "text": i.text} for i in state.items if i.status == "pending"]}
        path = p.synth_dir / "job.json"
        path.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def command(self, job_path: Path) -> list[str]:
        return wslenv.wsl_cmd(XTTS_PY, "-W", "ignore", wslenv.wsl_path(GEN_SCRIPT),
                              wslenv.wsl_path(Path(job_path).resolve()))

    def generate(self, p, state, on_line, popen=subprocess.Popen) -> int:
        (p.synth_dir / STOP_FILE).unlink(missing_ok=True)
        proc = popen(self.command(self.write_job(p, state)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     env={**os.environ, "WSL_UTF8": "1"})
        for raw in proc.stdout:
            on_line(wslenv.decode(raw).rstrip("\r\n"))
        return proc.wait()

    def request_stop(self, p) -> None:
        p.synth_dir.mkdir(parents=True, exist_ok=True)
        (p.synth_dir / STOP_FILE).touch()

    def kill(self, run=subprocess.run) -> None:
        run(wslenv.wsl_cmd("pkill", "-f", "piper_compat/xtts_gen.py"), capture_output=True)
