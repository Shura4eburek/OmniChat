#!/usr/bin/env bash
# Builds /opt/omnivoice/xtts: a venv of its own for XTTS v2 (coqui-tts), apart from piper's venv.
# Idempotent; one "STEP n/4 title" line per step (parsed like wsl_setup.sh). Usage: bash xtts_setup.sh <version>
set -euo pipefail
VERSION="${1:?usage: xtts_setup.sh <version>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV=/opt/omnivoice/xtts
TORCH_INDEX=https://download.pytorch.org/whl/cu126
C="$HERE/xtts_constraints.txt"
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PIP_NO_CACHE_DIR=1 COQUI_TOS_AGREED=1
step() { echo "STEP $1/4 $2"; }
rm -f "$VENV/READY"

step 1 "Окружение Python для XTTS"
[ -x "$VENV/bin/python" ] || python3 -m venv --clear "$VENV"

step 2 "PyTorch 2.8 и coqui-tts"
"$VENV/bin/python" -m pip install --progress-bar off -c "$C" --extra-index-url "$TORCH_INDEX" \
  torch torchaudio coqui-tts transformers soundfile soxr

step 3 "Модель XTTS v2 (~1.8 ГБ)"
"$VENV/bin/python" -c 'from TTS.api import TTS; TTS("tts_models/multilingual/multi-dataset/xtts_v2")'

step 4 "Пробная генерация"
"$VENV/bin/python" - <<'EOF'
import numpy as np, soundfile as sf, tempfile, torch, os
from TTS.api import TTS
ref = os.path.join(tempfile.gettempdir(), "omnivoice_ref.wav")
sf.write(ref, (0.1 * np.sin(np.arange(22050 * 3) / 7)).astype("float32"), 22050)
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda" if torch.cuda.is_available() else "cpu")
wav = tts.tts("Проверка связи.", speaker_wav=ref, language="ru")
assert len(wav) > 1000, "XTTS returned no audio"
print("xtts ok, cuda:", torch.cuda.is_available())
EOF
echo "$VERSION" > "$VENV/READY"
echo "XTTS v2 готов ($VERSION)"
