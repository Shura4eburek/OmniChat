from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from omnivoice import audio, dataset, deps
from omnivoice.dataset import Segment
from omnivoice.hints import NEED_PREP
from omnivoice.segments import plan_segments

SR = audio.SR

def _need_ffmpeg() -> str:
    ff = deps.ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg не найден — нажми «Установить зависимости» (omnivoice setup)")
    return ff

def _tail(b) -> str:
    return (b or b"").decode("utf-8", errors="replace").strip()[-300:] if isinstance(b, (bytes, bytearray)) else str(b or "").strip()[-300:]

def _decode(path: Path, label: str | None = None) -> np.ndarray:
    ff = _need_ffmpeg()
    try:
        raw = subprocess.run([ff, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg не смог прочитать {label or Path(path).name}: {_tail(e.stderr)}") from e
    return np.frombuffer(raw, np.float32).copy()

def _isolate(path: Path, out: Path) -> Path:
    try:
        subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", str(out), str(path)],
                       capture_output=True, check=True, env=deps.ffmpeg_env())
    except subprocess.CalledProcessError as e:
        err = _tail(e.stderr)
        if "No module named" in err:
            raise RuntimeError(NEED_PREP) from e
        raise RuntimeError(f"demucs не смог обработать {Path(path).name}: {err}") from e
    vocals = next(out.rglob("vocals.wav"), None)
    if vocals is None:
        raise RuntimeError("demucs не создал vocals.wav")
    return vocals

_VAD = None

def _speech(x: np.ndarray) -> list[tuple[float, float]]:
    global _VAD
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps
        import torch
    except ImportError as e:
        raise RuntimeError(NEED_PREP) from e
    if _VAD is None:
        _VAD = load_silero_vad()
    x16 = audio.resample(x, SR, 16000)
    ts = get_speech_timestamps(torch.from_numpy(x16), _VAD, sampling_rate=16000, return_seconds=True)
    return [(t["start"], t["end"]) for t in ts]

def _normalize(y: np.ndarray) -> np.ndarray:
    try:
        import pyloudnorm as pyln
    except ImportError as e:
        raise RuntimeError(NEED_PREP) from e
    if len(y) < 0.4 * SR:
        return y
    loud = pyln.Meter(SR).integrated_loudness(y)
    return pyln.normalize.loudness(y, loud, -20.0) if np.isfinite(loud) else y

PEAK_LIMIT = 0.99

def _limit_peak(y: np.ndarray, limit: float = PEAK_LIMIT) -> np.ndarray:
    """Loudness normalisation can push quiet-but-peaky clips past full scale; scale them back."""
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    return (y * (limit / peak)).astype(y.dtype, copy=False) if peak > limit else y

def _energy(x: np.ndarray):
    def f(a: float, b: float) -> float:
        seg = x[max(0, int(a * SR)): int(b * SR)]
        return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    return f

def slice_project(p, isolate: bool = False, progress=None) -> int:
    done_file = p.raw_dir / ".sliced.json"
    _need_ffmpeg()
    try:
        done = json.loads(done_file.read_text(encoding="utf-8")) if done_file.is_file() else {}
        if not isinstance(done, dict):
            done = {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        done = {}
    segments = dataset.load(p); added = 0
    known = {s.id.casefold() for s in segments}  # case-insensitive: ids differing by case collide on Windows
    p.segments_dir.mkdir(parents=True, exist_ok=True)
    files = [f for f in sorted(p.raw_dir.iterdir()) if f.is_file() and not f.name.startswith(".")]
    for i, f in enumerate(files):
        st = f.stat()
        key = f"{st.st_size}:{int(st.st_mtime)}"
        if done.get(f.name) == key:
            continue
        if progress: progress(f.name, i / max(1, len(files)))
        if isolate:
            with tempfile.TemporaryDirectory(prefix="omnivoice-demucs-") as tmp:
                x = _decode(_isolate(f, Path(tmp)), label=f.name)
        else:
            x = _decode(f)
        stem = dataset.sanitize_id(f.stem) or "raw"
        for s, e in plan_segments(_speech(x), _energy(x)):
            y = audio.pad(_limit_peak(_normalize(x[int(s * SR): int(e * SR)])), SR)
            n = 0
            while f"{stem}_{n:04d}".casefold() in known:
                n += 1
            sid = f"{stem}_{n:04d}"
            audio.write_wav(p.segments_dir / f"{sid}.wav", y)
            segments.append(Segment(sid, "", round(len(y) / SR, 3), source=f.name))
            known.add(sid.casefold())
            added += 1
        done[f.name] = key
        dataset.save(p, segments)
        tmp_marker = done_file.with_name(done_file.name + ".tmp")
        tmp_marker.write_text(json.dumps(done), encoding="utf-8")
        os.replace(tmp_marker, done_file)
    if added:
        p.mark_fresh(("audio", "slice"))
    return added
