#!/usr/bin/env bash
# Builds the omnivoice training environment inside the WSL distro "omnivoice" (Ubuntu 24.04).
# Runs as root and is idempotent: a re-run only does the missing work.
# Usage: bash wsl_setup.sh <env-version>
# constraints.txt, torch_shim.py and clean_ckpt.py must sit next to this script.
# Progress: one "STEP <n>/<total> <title>" line per step (parsed by omnivoice.wslenv).
set -euo pipefail

VERSION="${1:?usage: wsl_setup.sh <env-version>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT=/opt/omnivoice
VENV="$ROOT/venv"
PIPER="$ROOT/piper1-gpl"
PIPER_TAG=v1.8.0
PIPER_REPO=https://github.com/OHF-voice/piper1-gpl.git
TORCH_INDEX=https://download.pytorch.org/whl/cu126
C="$HERE/constraints.txt"
TOTAL=7
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PIP_NO_CACHE_DIR=1

step() { echo "STEP $1/$TOTAL $2"; }

mkdir -p "$ROOT"
rm -f "$ROOT/READY"  # the marker is written back only after every step succeeded

step 1 "Системные пакеты (apt)"
PKGS=(python3 python3-venv python3-dev build-essential cmake ninja-build git ca-certificates)
if ! dpkg -s "${PKGS[@]}" >/dev/null 2>&1; then
  apt-get update -q
  apt-get install -y -q --no-install-recommends "${PKGS[@]}"
fi

step 2 "Виртуальное окружение Python"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
export PATH="$VENV/bin:$PATH"
PIP=(python -m pip install --progress-bar off -c "$C" --extra-index-url "$TORCH_INDEX")

step 3 "PyTorch (CUDA 12.6) и библиотеки обучения"
"${PIP[@]}" setuptools wheel Cython scikit-build \
  torch torchaudio lightning pytorch-lightning lightning-utilities torchmetrics jsonargparse \
  numpy librosa onnx onnxscript onnxruntime tensorboard

step 4 "Исходники piper1-gpl $PIPER_TAG"
if [ "$(git -C "$PIPER" describe --tags --exact-match 2>/dev/null || true)" != "$PIPER_TAG" ]; then
  rm -rf "$PIPER"
  git clone --depth 1 --branch "$PIPER_TAG" "$PIPER_REPO" "$PIPER"
fi

step 5 "Сборка piper1-gpl"
cd "$PIPER"
"${PIP[@]}" -e '.[train]'
./build_monotonic_align.sh
python setup.py build_ext --inplace

step 6 "Совместимость piper с текущим PyTorch"
SITE="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
install -m 644 "$HERE/torch_shim.py" "$SITE/omnivoice_torch_shim.py"
echo "import omnivoice_torch_shim" > "$SITE/omnivoice_torch_shim.pth"
install -m 644 "$HERE/clean_ckpt.py" "$ROOT/clean_ckpt.py"

step 7 "Проверка среды"
python -c 'import torch, torchaudio, lightning, piper.train; print("torch", torch.__version__, "cuda", torch.version.cuda)'
echo "$VERSION" > "$ROOT/READY"
echo "Среда omnivoice готова ($VERSION)"
