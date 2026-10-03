# omnivoice: one-click dependency setup and WSL training backend

**Goal:** A non-technical Windows user installs everything omnivoice needs with one button («Установить зависимости»), and training runs in a WSL2 distro that omnivoice builds itself. No Docker Desktop is required, and nothing is hosted by us.

**Decisions approved by the user (2026-10-03):**
- Build the training environment on the user's machine from official sources. Do not ship prebuilt archives.
- Pin every version to what really trained a model today (see *Pinned environment*), so that a build on the user's machine reproduces the tested one.
- Docker stays as a fallback backend for users who already have it.

## Global constraints
- The package is `tools/omnivoice`. User-facing text is in Russian, and an expected failure must never produce a traceback. The commit trailer is `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Stage explicit paths only; never `.wolf/` or `.superpowers/`.
- Never touch, unregister or modify the user's existing WSL distros (`Ubuntu-24.04`, `docker-desktop`). omnivoice owns only the distro named `omnivoice`.
- Every network download has a pinned URL plus a sha256 check, a timeout, resume or retry once, and a Russian error that names the URL.
- Every step is idempotent. A version marker records what is installed, so re-running does only the missing work.
- Tests never touch the network, WSL or Docker. Inject the runner (`run=`) as `train.py` already does.
- Windows paths map to WSL paths through `wsl -d omnivoice -- wslpath -a`, or through a pure function for `C:\…` → `/mnt/c/…`, with a test.

## Pinned environment (from the image that trained a model on 2026-10-03)
- Base OS: Ubuntu 24.04, Python 3.12.
- Packages: `torch==2.14.1+cu126`, `torchaudio==2.11.0+cu126`, `lightning==2.6.6`, `pytorch-lightning==2.6.6`, `lightning-utilities==0.15.3`, `torchmetrics==1.9.0`, `jsonargparse==4.52.0`, `numpy==2.5.3`, `librosa==0.11.0`, `onnx==1.23.1`, `onnxscript==0.7.2`, `onnxruntime==1.30.0`, `tensorboard==2.21.0`, `Cython==3.3.0`, `scikit-build==0.19.1`. The full freeze is in `image-freeze.txt` in the scratchpad; the implementer of Task 1 copies the relevant subset.
- piper1-gpl: git tag `v1.8.0`, built with `./build_monotonic_align.sh` and `python3 setup.py build_ext --inplace`.
- Compatibility: `omnivoice/piper_compat` (`torch_shim.py`, `clean_ckpt.py`) is already used by Docker and Colab.

---

### Task 1: WSL environment builder (`omnivoice/wslenv.py` + `omnivoice/piper_compat/wsl_setup.sh` + `constraints.txt`)
- `constraints.txt` (pinned versions above) lives in `piper_compat/` and is shipped in the wheel. The Dockerfile must also use it (`pip install -c`), so Docker and WSL stay identical.
- `wsl_setup.sh` runs inside the distro as root and is idempotent:
  - apt installs `python3 python3-venv python3-dev build-essential git ca-certificates`;
  - creates a venv at `/opt/omnivoice/venv`;
  - installs torch, torchaudio and the rest with `-c constraints.txt` from the cu126 index;
  - clones piper1-gpl `v1.8.0` into `/opt/omnivoice/piper1-gpl`, then runs `pip install -e '.[train]' -c constraints.txt`, `build_monotonic_align.sh` and `build_ext --inplace`;
  - installs `torch_shim.py` plus its `.pth` into the venv site-packages, and copies `clean_ckpt.py` to `/opt/omnivoice/`;
  - writes `/opt/omnivoice/READY` containing the environment version string.
  It prints one line per step: `STEP <n>/<total> <russian title>`, so Python can show progress.
- `wslenv.py` API, with `run=` injectable:
  - `status() -> EnvStatus(wsl: bool, wsl_version_ok: bool, distro: bool, ready: bool, gpu: bool | None, message: str)`. It parses `wsl --status` and `wsl -l -q`, which are UTF-16LE (decode them correctly), plus `wsl -d omnivoice -- cat /opt/omnivoice/READY`.
  - `ensure_wsl()`: if WSL is missing, run `wsl --install --no-distribution` elevated. That triggers one UAC prompt, so use `powershell Start-Process -Verb RunAs -Wait`. Return «нужна перезагрузка» when Windows asks for one.
  - `download_rootfs(progress)`: the official Ubuntu 24.04 WSL rootfs from Canonical, with a pinned URL and sha256. Verify the URL and checksum live and record them in the report. Store it in `cache_dir()/wsl/`.
  - `import_distro()`: `wsl --import omnivoice <cache_dir()/wsl/omnivoice> <tar> --version 2`.
  - `provision(on_line)`: copies `wsl_setup.sh`, `constraints.txt`, `torch_shim.py` and `clean_ckpt.py` into the distro, then runs the script and streams its output.
  - `ensure_ready(on_line, progress)`: runs all of the above in order, skipping what is already done.
  - `wsl_path(win_path)`.
  - `gpu_ok()`: `wsl -d omnivoice -- nvidia-smi`.
  - `ENV_VERSION` constant. When it changes, provisioning re-runs.
- Tests cover status parsing (with UTF-16 samples), idempotent skipping, the STEP line parser, the path mapping, the sha256 mismatch error, and a missing-WSL message.

### Task 2: WSL training backend in `train.py`
- Backend selection: `backend(env) -> "wsl" | "docker"`. Prefer `"wsl"` when `wslenv.status().ready`; fall back to Docker when Docker works; otherwise raise the Russian TrainError «Нет среды обучения — нажми «Установить зависимости» (omnivoice setup)».
- `detect_env` reports the backend and the GPU for it.
- WSL commands use `wsl -d omnivoice -- /opt/omnivoice/venv/bin/python -m piper.train fit …`, with `fit_args` paths mapped through `wsl_path` and the cache/checkpoints referenced by their `/mnt/...` paths. Export and clean work the same way.
- Stop and Ctrl-C run `wsl -d omnivoice -- pkill -f piper.train`, following the same contract as Docker (`should_stop`, exit code 130, the Russian message).
- The OOM retry, relative epochs, the target-reached check and `mark_fresh` behave identically for both backends. Reuse the existing logic and make it backend-agnostic, not duplicated.
- The UTMOS torch.hub cache sits on a persistent path inside the distro (`/root/.cache/torch`); it persists by default.
- Tests check that the WSL command lines are correct, the fallback order, and that stop on WSL calls `pkill`.

### Task 3: Windows-side dependencies (`omnivoice/deps.py`)
- `ffmpeg_path()`: use ffmpeg from PATH if present. Otherwise use `cache_dir()/ffmpeg/bin/ffmpeg.exe` if installed. `install_ffmpeg(progress)` downloads a pinned Windows build (gyan.dev or BtbN release zip, with a verified URL and sha256) and extracts only `ffmpeg.exe` and `ffprobe.exe`. `slicer` must call `ffmpeg_path()` instead of the bare `"ffmpeg"`.
- `prep_ok()` checks that the prep extra imports. `install_prep(on_line)` installs the `prep` and `ui` extras into the current interpreter:
  - in the repo checkout (there is a `pyproject.toml` next to the package): `uv sync --all-extras --project <tools/omnivoice>`;
  - otherwise: `uv pip install --python <sys.executable> "omnivoice[prep,ui]"`.
  In both cases, use the `uv` on PATH, or the one next to `sys.executable`.
- `check_all() -> list[Item(name, ok, detail)]` covers prep, ffmpeg, WSL, the distro, GPU and Docker (optional). `install_all(on_line, progress)` installs every missing piece in order. It stops at «нужна перезагрузка» with a clear Russian message.
- Tests use injected runners and fake downloads.

### Task 4: CLI `omnivoice setup` + UI button + Windows installer
- CLI:
  - `omnivoice setup` prints the checklist with ✓/✗ and runs `install_all`, streaming the log.
  - `omnivoice setup --check` prints the checklist only and exits 1 if anything is missing.
- UI:
  - An «Установка» section appears first in the sidebar. It shows the checklist, a «Установить зависимости» button, a progress bar (`STEP n/total` plus download percent) and a live log.
  - It runs in a background thread, with the same pattern as `TrainRunner` and protected against double clicks.
  - The steps bar and the Обучение section show «Сначала установи зависимости» when the environment is missing.
  - All strings live in `strings.py`.
- `tools/omnivoice/Установить omnivoice.bat` (with a UTF-8/ASCII-safe name fallback `install-omnivoice.bat`, also usable from cmd). It:
  - installs uv via the official `irm https://astral.sh/uv/install.ps1 | iex` if `uv` is missing;
  - runs `uv sync --all-extras`;
  - creates a desktop shortcut «OmniVoice» that runs `uv run omnivoice ui --projects %USERPROFILE%\omnivoice-projects`;
  - launches the UI.
  `.bat` files must be CRLF and must not depend on the console codepage. Use `chcp 65001` or keep the file ASCII.
- Tests: CLI `setup --check` output and exit code, the UI helper that renders the checklist, and the double-click guard.

### Task 5: README and live end-to-end
- README:
  - The «Установка» section becomes: download the repo or zip → double-click the installer → in the UI press «Установить зависимости».
  - Docker becomes an «если уже стоит Docker» fallback.
  - Troubleshooting covers no WSL, the reboot, an old NVIDIA driver, and disk space (~6 ГБ).
- Live e2e on this machine. This is allowed: it creates only the `omnivoice` distro and the cache.
  1. Run `omnivoice setup`.
  2. Then train the scratchpad smoke project for 2 epochs through the WSL backend.
  3. Then run `export` (pack + verify).
  4. Record the timings and disk usage.
