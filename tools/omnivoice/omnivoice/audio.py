from pathlib import Path
import numpy as np, soundfile as sf, soxr

SR = 22050

def load_mono(path) -> tuple[np.ndarray, int]:
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1), sr

def resample(x: np.ndarray, sr_in: int, sr_out: int = SR) -> np.ndarray:
    return x if sr_in == sr_out else soxr.resample(x, sr_in, sr_out).astype(np.float32)

def pad(x: np.ndarray, sr: int, ms: int = 150) -> np.ndarray:
    z = np.zeros(int(sr * ms / 1000), np.float32)
    return np.concatenate([z, x.astype(np.float32), z])

def write_wav(path, x: np.ndarray, sr: int = SR) -> None:
    sf.write(str(path), np.clip(x, -1, 1), sr, subtype="PCM_16")

def clipping_ratio(x: np.ndarray) -> float:
    return float(np.mean(np.abs(x) >= 0.999)) if len(x) else 0.0

def duration(path) -> float:
    i = sf.info(str(path)); return i.frames / i.samplerate
