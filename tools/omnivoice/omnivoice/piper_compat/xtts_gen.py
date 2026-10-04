"""Generate synthetic phrases with XTTS v2 (runs inside the WSL venv /opt/omnivoice/xtts).

python xtts_gen.py <job.json>   — see omnivoice.teacher for the job format. Prints `ITEM n/N id` after
every written wav and `FAIL id message` for a phrase that failed; stops between phrases when the job's
stop_file appears. Each wav goes through <id>.wav.part and os.replace, so a stop never leaves half a file.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np


def _write(path: Path, x: np.ndarray, sr: int, target_sr: int) -> None:
    import soundfile as sf
    import soxr
    if sr != target_sr:
        x = soxr.resample(x.astype(np.float32), sr, target_sr)
    part = path.with_name(path.name + ".part")
    sf.write(str(part), np.clip(x, -1, 1), target_sr, subtype="PCM_16", format="WAV")
    os.replace(part, path)


def run_job(job: dict, synthesize, out=print) -> int:
    out_dir, stop = Path(job["out_dir"]), Path(job["stop_file"])
    out_dir.mkdir(parents=True, exist_ok=True)
    items = job["items"]
    for n, it in enumerate(items, 1):
        if stop.exists():
            break
        target = out_dir / f"{it['id']}.wav"
        if target.exists():
            continue
        try:
            x, sr = synthesize(it["text"], job["refs"])
            _write(target, np.asarray(x, np.float32).reshape(-1), int(sr), int(job["sample_rate"]))
        except Exception as e:  # one phrase failing must not stop the rest
            out(f"FAIL {it['id']} {str(e).splitlines()[0] if str(e) else type(e).__name__}")
            continue
        out(f"ITEM {n}/{len(items)} {it['id']}")
    return 0


def xtts_synthesizer(language: str, refs: list[str]):
    """XTTS v2 with the conditioning computed once for all phrases."""
    import torch
    from TTS.api import TTS
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda" if torch.cuda.is_available() else "cpu")
    model = tts.synthesizer.tts_model
    latent, speaker = model.get_conditioning_latents(audio_path=refs)
    sr = tts.synthesizer.output_sample_rate

    def synthesize(text, _refs):
        out = model.inference(text, language, latent, speaker, temperature=0.65, enable_text_splitting=True)
        return np.asarray(out["wav"], np.float32), sr
    return synthesize


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    job = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    return run_job(job, xtts_synthesizer(job["language"], job["refs"]), out=lambda s: print(s, flush=True))


if __name__ == "__main__":
    sys.exit(main())
