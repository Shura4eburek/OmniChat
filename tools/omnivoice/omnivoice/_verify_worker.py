"""Runs sherpa-onnx synthesis in a separate process: a bad model can crash the interpreter natively."""
import sys
from pathlib import Path

def main(folder: str, text: str, out: str) -> None:
    try:
        import sherpa_onnx, soundfile as sf
    except ImportError as e:
        sys.stderr.write(f"missing dependency: {e}\n"); sys.exit(4)
    f = Path(folder)
    model = next(f.glob("*.onnx"))
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(model), lexicon="",
                 data_dir=str(f / "espeak-ng-data"), tokens=str(f / "tokens.txt")),
            provider="cpu", debug=False, num_threads=2),
        rule_fsts="", max_num_sentences=1)
    if not cfg.validate():
        sys.stderr.write("sherpa-onnx config validation failed\n"); sys.exit(2)
    tts = sherpa_onnx.OfflineTts(cfg)
    audio = tts.generate(text, 0, 1.0)
    if len(audio.samples) == 0:
        sys.stderr.write("sherpa-onnx produced no audio\n"); sys.exit(3)
    sf.write(out, audio.samples, samplerate=audio.sample_rate, subtype="PCM_16")

if __name__ == "__main__":
    main(*sys.argv[1:4])
