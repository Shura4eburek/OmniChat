"""Pure helpers behind the web UI. No gradio import here, so they are testable without the ui extra.

Concurrency model: ProjectLocks gives each project one non-blocking write lock. Every UI action that
loads, modifies and saves project files holds it for its whole duration; a second action on the same
project is refused with S.PROJECT_BUSY instead of interleaving writes. Training holds it only while
the dataset csv is written (released at TrainRunner's first should_stop poll), not during the docker run.
"""
from __future__ import annotations

import html
import io
import logging
import re
import shutil
import subprocess
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from collections import deque
from pathlib import Path

from PIL import Image

from omnivoice import modrules, trainlog
from omnivoice.dataset import clean_text
from omnivoice.project import FILE as PROJECT_FILE
from omnivoice.ui import strings as S

SECTIONS = (S.SEC_AUDIO, S.SEC_SLICE, S.SEC_PHRASES, S.SEC_CHECK, S.SEC_TRAIN, S.SEC_PACK)
NAV_SECTIONS = (S.SEC_SETUP, *SECTIONS)  # sidebar order: setup first, then the project steps
SECTION_STEP = dict(zip(SECTIONS, ("audio", "slice", "phrases", "check", "train", "pack")))
COLUMNS = [S.COL_ID, S.COL_TEXT, S.COL_DURATION, S.COL_FLAGS, S.COL_DROPPED]
FLAG = "⚑"
log = logging.getLogger("omnivoice.ui")


# ---------- projects ----------

def list_projects(root: Path) -> list[str]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir() and (d / PROJECT_FILE).is_file())


# ---------- steps bar ----------

def steps_bar_html(steps: dict, current: str | None, need_setup: bool = False) -> str:
    """`current` is a step key (project.STEPS), e.g. "phrases".
    Six chips: the selected section is `on` (teal), finished steps `done` (green ✓), others grey.
    need_setup adds a yellow chip that leads to «Установка» (no training environment yet)."""
    chips = []
    for i, section in enumerate(SECTIONS, 1):
        step = SECTION_STEP[section]
        done = bool(steps.get(step))
        cls = "st on" if step == current else ("st done" if done else "st")
        label = f"{i} {section.upper()}{' ✓' if done else ''}"
        chips.append(f'<span class="{cls}" data-section="{html.escape(section)}">{html.escape(label)}</span>')
    if need_setup:
        chips.append(f'<span class="st warn" data-section="{html.escape(S.SEC_SETUP)}">'
                     f'{html.escape(S.SETUP_FIRST.upper())} →</span>')
    return '<div class="steps">' + "".join(chips) + "</div>"


# ---------- uploads ----------

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_upload_name(name: str) -> str:
    """Last path component only, no leading dots, no characters Windows forbids."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = _BAD_CHARS.sub("_", base).strip().lstrip(".").strip()
    return base or "audio"


def copy_uploads(paths, raw_dir: Path, names=None) -> list[Path]:
    """Copy uploaded files into raw_dir under sanitized, non-clashing names."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    root = raw_dir.resolve()
    out = []
    for i, src in enumerate(paths):
        src = Path(src)
        name = safe_upload_name(names[i] if names else src.name)
        stem, suffix = Path(name).stem or "audio", Path(name).suffix
        dest, n = raw_dir / name, 1
        while dest.exists():
            n += 1
            dest = raw_dir / f"{stem}_{n}{suffix}"
        if dest.resolve().parent != root:  # belt and braces: never escape raw/
            raise ValueError(S.BAD_FILE_NAME.format(name=name))
        shutil.copyfile(src, dest)
        out.append(dest)
    return out


def list_raw_files(raw_dir: Path) -> list[list]:
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return []
    return [[f.name, f"{f.stat().st_size / 1024:.1f} {S.KB}"]
            for f in sorted(raw_dir.iterdir()) if f.is_file() and not f.name.startswith(".")]


# ---------- phrases ----------

def stats_line(segments) -> str:
    live = [s for s in segments if not s.dropped]
    minutes = sum(s.duration for s in live) / 60
    check = sum(1 for s in live if "check" in s.flags)
    dropped = len(segments) - len(live)
    return (f'<div class="stat"><span>{S.STAT_PHRASES} <b>{len(live)}</b></span>'
            f'<span>{S.STAT_SPEECH} <b>{minutes:.1f} {S.STAT_MINUTES}</b></span>'
            f'<span class="flag">{S.STAT_CHECK}: {check}</span>'
            f'<span class="muted">{S.STAT_DROPPED}: {dropped}</span></div>')


def code_label(code: str) -> str:
    """Human Russian label for an internal flag / issue code; unknown codes are shown as is."""
    return S.code_labels.get(code, code)


def flags_text(flags) -> str:
    return " ".join(f"{FLAG} {code_label(f)}" for f in flags)


def segments_rows(segments, only_flagged: bool = False) -> list[list]:
    return [[s.id, s.text, round(float(s.duration), 2), flags_text(s.flags), bool(s.dropped)]
            for s in segments if not only_flagged or (s.flags and not s.dropped)]


def apply_edits(segments, rows) -> int:
    """Write edited texts back. A changed text marks the segment edited and clears its `check` flag."""
    by_id = {s.id: s for s in segments}
    changed = 0
    for row in rows or []:
        if not row:
            continue
        s = by_id.get(str(row[0]))
        if s is None:
            continue
        text = clean_text(str(row[1] if len(row) > 1 and row[1] is not None else ""))
        if text != s.text:
            s.text, s.edited = text, True
            s.flags = [f for f in s.flags if f != "check"]
            changed += 1
    return changed


def toggle_dropped(segments, seg_id: str) -> bool:
    for s in segments:
        if s.id == seg_id:
            s.dropped = not s.dropped
            return s.dropped
    raise ValueError(S.NO_SEGMENT.format(id=seg_id))


# ---------- check ----------

def report_html(r) -> str:
    e = html.escape
    parts = [f'<div class="report"><p>{e(S.CHECK_SUMMARY.format(minutes=r.total_minutes, phrases=r.phrases))}</p>']
    parts += [f'<p class="err">✗ {e(x)}</p>' for x in r.errors]
    parts += [f'<p class="warn">! {e(x)}</p>' for x in r.warnings]
    if not r.errors:
        parts.append(f'<p class="ok">✓ {e(S.CHECK_OK)}</p>')
    if r.per_segment:
        parts.append(f'<p>{e(S.CHECK_ISSUES)}</p><table class="issues">')
        for sid, issues in sorted(r.per_segment.items()):
            parts.append(f"<tr><td>{e(sid)}</td><td>{e(', '.join(code_label(i) for i in issues))}</td></tr>")
        parts.append("</table>")
    parts.append("</div>")
    return "".join(parts)


# ---------- train ----------

def env_badge(env) -> str:
    if env is None:
        return S.ENV_CHECKING
    wsl_no_gpu = env.backend is None and env.wsl_ready and env.wsl_gpu is False
    if env.gpu_name:
        gpu = S.GPU_PREFIX + env.gpu_name + ("" if env.gpu or wsl_no_gpu else S.GPU_DOCKER_NO)
    else:
        gpu = S.NO_GPU
    if env.backend == "wsl":
        return f"{gpu} · {S.WSL_OK}"
    if wsl_no_gpu:
        return f"{gpu} · {S.WSL_NO_GPU}"
    return f"{gpu} · {S.DOCKER_OK if env.docker else S.DOCKER_NO}"


class EnvProbe:
    """Runs detect_env() once in a daemon thread (it can take ~2 minutes)."""

    def __init__(self, detect):
        self._detect = detect
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._gen = 0
        self.env = None

    @property
    def done(self) -> bool:
        return self.env is not None

    def start(self) -> None:
        with self._lock:
            if self._thread is None:
                self._spawn()

    def restart(self) -> None:
        """Probe again (after «Установить зависимости»); a result from an older probe is dropped."""
        with self._lock:
            self._gen += 1
            self.env = None
            self._spawn()

    def _spawn(self) -> None:
        self._thread = threading.Thread(target=self._run, args=(self._gen,), daemon=True, name="omnivoice-env")
        self._thread.start()

    def _run(self, gen: int = 0) -> None:
        try:
            env = self._detect()
        except Exception:
            from omnivoice.train import Env
            env = Env(False, False, None, None)
        with self._lock:
            if gen == self._gen:
                self.env = env

    def join(self, timeout=None) -> None:
        if self._thread:
            self._thread.join(timeout)


class TrainRunner:
    """One background training run per project; Stop = train.stop_training (docker stop / pkill in WSL).

    The raw stdout goes to <project>/train/train.log untouched; the UI shows trainlog.LogCleaner's
    short lines (one per epoch) rendered with self.metrics, which the UI refreshes from the events."""

    def __init__(self, train_fn=None, run=subprocess.run, max_lines: int = 400, clock=None):
        self._train = train_fn or self._default_train
        self._run = run
        self._max_lines = max_lines
        self._clock = clock or time.monotonic
        self.clean = trainlog.LogCleaner(max_lines=max_lines, clock=self._clock)
        self.metrics: dict = {}  # {absolute epoch: {"val_mos": .., "val_mel": ..}}
        self.log_path: Path | None = None
        self._raw = None
        self._seen_ckpts: set[str] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.status = "idle"  # idle | running | done | stopped | failed | error
        self.code: int | None = None
        self.epoch: int | None = None
        self.target: int | None = None
        self.offset = 0
        self._p = None
        self._stop = threading.Event()
        self._prepared = None
        self._last_pct = -1

    def _download_progress(self, done, total) -> None:
        """Like the CLI: log the base checkpoint download at most every 5 %."""
        if total:
            pct = done * 100 // total // 5 * 5
            if pct > self._last_pct:
                self._last_pct = pct
                self._note(S.TRAIN_DOWNLOAD.format(pct=pct))

    def _default_train(self, p, **kw):
        from omnivoice import train
        return train.train_project(p, progress=self._download_progress, **kw)

    def _release_prepared(self) -> None:
        cb, self._prepared = self._prepared, None
        if cb:
            cb()

    def _should_stop(self) -> bool:
        # train_project polls first right after the dataset csv is written: the project lock can go.
        self._release_prepared()
        return self._stop.is_set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---- log ----
    def _write_raw(self, text: str) -> None:
        if self._raw is not None:
            try:
                self._raw.write(text + "\n")
            except (OSError, ValueError):
                self._raw = None

    def _line(self, line: str) -> None:
        """A raw stdout line of the training process."""
        with self._lock:
            self._write_raw(line)
            self.clean.feed(line)
            if self.clean.epoch is not None:
                self.epoch = self.clean.epoch

    def _note(self, text: str) -> None:
        """A message of our own: shown as is."""
        with self._lock:
            self._write_raw(text)
            self.clean.add(text)

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self.clean.render(self.metrics))

    def _open_raw(self, p) -> None:
        train_dir = getattr(p, "train_dir", None)
        self.log_path = self._raw = None
        if train_dir is None:
            return
        try:
            Path(train_dir).mkdir(parents=True, exist_ok=True)
            self.log_path = Path(train_dir) / "train.log"
            self._raw = open(self.log_path, "a", encoding="utf-8", errors="replace", buffering=1)
            self._raw.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        except OSError:
            self._raw = None

    def _close_raw(self) -> None:
        with self._lock:
            f, self._raw = self._raw, None
        if f is not None:
            try:
                f.close()
            except OSError:
                pass

    def _ckpt_files(self) -> list[Path]:
        train_dir = getattr(self._p, "train_dir", None)
        return list(Path(train_dir).glob("lightning_logs/*/checkpoints/epoch=*.ckpt")) if train_dir else []

    def poll_checkpoints(self) -> None:
        """Log «Сохранён чекпойнт …» for files written since start (Lightning prints nothing about them).
        The val_mel and val_mos files of one epoch make one line."""
        from omnivoice.previews import _CKPT_RE
        new: dict[int, dict[str, float]] = {}
        for f in sorted(self._ckpt_files()):
            if str(f) in self._seen_ckpts:
                continue
            self._seen_ckpts.add(str(f))
            m = _CKPT_RE.match(f.name)
            if m:
                new.setdefault(int(m.group(1)), {})[m.group(2)] = float(m.group(3))
        for epoch, vals in sorted(new.items()):
            self._note(S.CKPT_SAVED.format(what=_ckpt_text(epoch - self.offset, vals.get("val_mos"),
                                                           vals.get("val_mel"))))

    # ---- run ----
    def start(self, p, epochs: int, resume: bool, batch, env, target: int | None = None,
              on_prepared=None, offset: int = 0) -> None:
        """on_prepared() runs once: after the dataset csv is written, or when the run ends earlier."""
        with self._lock:
            if self.running:
                raise RuntimeError(S.TRAIN_BUSY)
            self._p = p
            self.status, self.code, self.epoch, self.target = "running", None, None, target
            self.offset = offset  # base checkpoint's epoch: the log's absolute epochs minus this = new epochs
            self.clean = trainlog.LogCleaner(offset=offset, target=target, max_lines=self._max_lines,
                                             clock=self._clock)
            self._stop.clear()
            self._prepared, self._last_pct = on_prepared, -1
            self._seen_ckpts = {str(f) for f in self._ckpt_files()}
            self._open_raw(p)
            self._write_raw(S.TRAIN_STARTED.format(epochs=epochs, batch=batch or S.TRAIN_BATCH_AUTO))
            self.clean.add(S.TRAIN_STARTED.format(epochs=epochs, batch=batch or S.TRAIN_BATCH_AUTO))
            self._thread = threading.Thread(target=self._work, args=(p, epochs, resume, batch, env),
                                            daemon=True, name=f"omnivoice-train-{p.name}")
            self._thread.start()

    def _work(self, p, epochs, resume, batch, env) -> None:
        try:
            code = self._train(p, epochs=epochs, resume=resume, on_line=self._line, batch=batch, env=env,
                               should_stop=self._should_stop)
        except Exception as e:  # TrainError / RuntimeError / OSError: shown in the log, never a traceback
            self._note(str(e) or type(e).__name__)
            if self.status != "stopped":
                self.status = "error"
            self._close_raw()
            return
        finally:
            self._release_prepared()
        self.code = code
        if self.status != "stopped":
            self.status = "done" if code == 0 else "failed"
        if self.status == "done":
            with self._lock:
                self.clean.finish()
        self.poll_checkpoints()
        self._note({"done": S.TRAIN_DONE, "stopped": S.TRAIN_STOPPED,
                    "failed": S.TRAIN_FAILED.format(code=code)}[self.status])
        self._close_raw()

    def stop(self, timeout: int = 60) -> None:
        if not self.running or self._p is None:
            return
        self.status = "stopped"
        self._stop.set()  # covers the download / image-build phase, before any container exists
        self._note(S.TRAIN_STOPPING)
        try:
            from omnivoice import train
            train.stop_training(self._p, run=self._run, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as e:
            self._note(str(e))

    def join(self, timeout=None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def status_text(self) -> str:
        if self.status == "running":
            if self.epoch is None:
                return S.TRAIN_RUNNING_NO_EPOCH
            target = self.target - self.offset if self.target is not None else "?"
            text = S.TRAIN_RUNNING.format(epoch=self.epoch - self.offset, target=target)
            per, eta = self.clean.seconds_per_epoch(), self.clean.eta()
            if per is not None and eta is not None:
                text += S.TRAIN_TIMING.format(per=trainlog.duration_text(per), eta=trainlog.duration_text(eta))
            return text
        return {"idle": S.TRAIN_IDLE, "done": S.TRAIN_DONE, "stopped": S.TRAIN_STOPPED,
                "failed": S.TRAIN_FAILED.format(code=self.code), "error": S.TRAIN_ERROR}[self.status]


def _ckpt_text(epoch: int, mos: float | None, mel: float | None) -> str:
    parts = [S.CKPT_EPOCH.format(epoch=epoch)]
    if mos is not None:
        parts.append(S.CKPT_MOS.format(v=mos))
    if mel is not None:
        parts.append(S.CKPT_MEL.format(v=mel))
    return " · ".join(parts)


def ckpt_choices(rows, offset: int) -> tuple[list[tuple[str, str]], str | None]:
    """previews.rank_checkpoints rows → dropdown (label, path) pairs and the one to preselect
    (the best by MOS, else the first)."""
    choices = []
    for r in rows:
        tags = [S.CKPT_BEST_MOS] if r.best_mos else []
        tags += [S.CKPT_BEST_MEL] if r.best_mel else []
        tags += [S.CKPT_LAST] if r.last else []
        tags += [S.CKPT_OLD_LAST] if r.old_last else []
        choices.append((" · ".join([_ckpt_text(r.epoch - offset, r.mos, r.mel), *tags]), str(r.path)))
    best = next((str(r.path) for r in rows if r.best_mos), choices[0][1] if choices else None)
    return choices, best


def disk_html(train_bytes: int, n_ckpt: int, extra_bytes: int, n_extra: int) -> str:
    from omnivoice.datadir import human_size
    line = S.DISK_LINE.format(size=human_size(train_bytes), n=n_ckpt)
    extra = S.DISK_EXTRA.format(n=n_extra, size=human_size(extra_bytes)) if n_extra else S.DISK_NOTHING_EXTRA
    return (f'<div class="disk-line">{html.escape(line)}</div>'
            f'<div class="section-msg muted">{html.escape(extra)} · {html.escape(S.PRUNE_INFO)}</div>')


# ---------- setup (dependencies) ----------

def needs_setup(env) -> bool:
    """No usable training environment and the omnivoice WSL distro isn't built (None = still probing).
    Without an NVIDIA GPU on the host setup skips WSL (deps.check_all), so the Colab hint is shown instead."""
    return env is not None and env.backend is None and not env.wsl_ready and env.gpu_name is not None


def last_epoch_target(p, n_epochs: int) -> int:
    """The epoch number the training log reaches when `n_epochs` more epochs are done."""
    from omnivoice import train
    return train.target_epochs(p, n_epochs) - 1  # Lightning prints 0-based last epoch


def checklist_html(items) -> str:
    """deps.check_all() items as HUD rows: ✓ green, ✗ red, optional misses grey with a chip."""
    if items is None:
        return f'<div class="checklist"><div class="ck-row muted">{html.escape(S.SETUP_CHECKING)}</div></div>'
    rows = []
    for it in items:
        cls = "ok" if it.ok else ("opt" if it.optional else "miss")  # not "bad": that one strikes through
        chip = f'<span class="ck-chip">{html.escape(S.SETUP_OPTIONAL)}</span>' if it.optional else ""
        rows.append(f'<div class="ck-row {cls}"><span class="ck-mark">{"✓" if it.ok else "✗"}</span>'
                    f'<span class="ck-name">{html.escape(it.name)}{chip}</span>'
                    f'<span class="ck-detail">{html.escape(it.detail)}</span></div>')
    return '<div class="checklist">' + "".join(rows) + "</div>"


class SetupProgress:
    """Progress of install_all: `STEP n/total title` lines from wsl_setup.sh, download percent, and the
    stage lines of install_all (they end with «…»)."""

    def __init__(self):
        self.pct, self.step, self.total, self.title = 0, None, None, ""

    def line(self, line: str) -> None:
        from omnivoice.wslenv import parse_step
        if st := parse_step(line):
            self.step, self.total, self.title = st
            self.pct = (self.step - 1) * 100 // max(self.total, 1)
        elif line.rstrip().endswith("…") and len(line) < 120:
            self.title = line.strip()

    def download(self, done, total) -> None:
        if total:
            self.pct = max(0, min(100, done * 100 // total))
            self.title = S.SETUP_DOWNLOADING.format(pct=self.pct)

    def finish(self) -> None:
        self.pct = 100

    def html(self) -> str:
        label = self.title
        if self.step is not None:
            label = S.SETUP_STEP.format(n=self.step, total=self.total) + (f" · {self.title}" if self.title else "")
        return (f'<div class="setup-progress"><div class="setup-bar"><i style="width:{self.pct}%"></i></div>'
                f'<div class="setup-step">{html.escape(label)}</div></div>')


class SetupRunner:
    """«Установить зависимости» in a daemon thread (same pattern as TrainRunner): one run at a time,
    a live log, progress, then a fresh check_all() and on_finish() (re-probes the environment).
    `version` changes on every update, so the UI timer can skip idle ticks."""

    def __init__(self, install_fn=None, check_fn=None, on_finish=None, max_lines: int = 600):
        from omnivoice import deps, train, wslenv
        self._install = install_fn or deps.install_all
        self._check = check_fn or deps.check_all
        self._on_finish = on_finish
        self._errors = (deps.DepsError, wslenv.WslError, train.TrainError, RuntimeError, OSError)
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._check_thread: threading.Thread | None = None
        self.status = "idle"  # idle | running | done | reboot | error
        self.items = None
        self.reboot: str | None = None
        self.error: str | None = None
        self.check_error: str | None = None
        self.progress = SetupProgress()
        self.version = 0
        self._job = self._install
        self.done_text: str | None = None
        self.error_title: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def busy(self) -> bool:
        """An install or a background check is running: the UI keeps polling until both are done."""
        return self.running or (self._check_thread is not None and self._check_thread.is_alive())

    def _bump(self) -> None:
        self.version += 1

    def _line(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)
        self.progress.line(line)
        self._bump()

    def _download(self, done, total) -> None:
        self.progress.download(done, total)
        self._bump()

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self._lines)

    def check(self) -> None:
        """Re-run check_all() in the background (it calls wsl.exe, which can take seconds)."""
        with self._lock:
            if self.busy:
                return
            self._check_thread = threading.Thread(target=self._recheck, daemon=True, name="omnivoice-deps-check")
            self._check_thread.start()

    def _recheck(self) -> None:
        try:
            self.items, self.check_error = self._check(), None
        except Exception as e:  # wsl.exe hanging / missing: show it, never a traceback
            log.warning("check_all failed: %s", e)
            self.items, self.check_error = [], S.SETUP_CHECK_FAILED.format(error=str(e) or type(e).__name__)
        self._bump()

    def start(self, job=None, done_text: str | None = None, error_title: str | None = None) -> None:
        """Run install_fn, or `job` (same signature: on_line, progress → reboot message | None) with the same
        busy guard, log and progress; `done_text` / `error_title` replace the install wording of the status."""
        with self._lock:
            if self.running:
                raise RuntimeError(S.SETUP_BUSY)
            self.status, self.reboot, self.error = "running", None, None
            self._job, self.done_text, self.error_title = job or self._install, done_text, error_title
            self.progress = SetupProgress()
            self._lines.clear()
            self._thread = threading.Thread(target=self._work, daemon=True, name="omnivoice-setup")
            self._thread.start()
        self._bump()

    def _work(self) -> None:
        try:
            self.reboot = self._job(self._line, self._download)
            self.status = "reboot" if self.reboot else "done"
            if not self.reboot:
                self.progress.finish()
        except self._errors as e:
            self.error = str(e) or type(e).__name__
            self._line(self.error)
            self.status = "error"
        except Exception:
            log.error("setup failed:\n%s", traceback.format_exc())
            self.error = S.ERR_UNKNOWN
            self._line(self.error)
            self.status = "error"
        self._recheck()
        if self._on_finish:
            try:
                self._on_finish()
            except Exception:
                log.error("setup on_finish failed:\n%s", traceback.format_exc())
        self._bump()

    def join(self, timeout=None) -> None:
        for t in (self._thread, self._check_thread):
            if t:
                t.join(timeout)

    def status_html(self) -> str:
        e = html.escape
        if self.status == "reboot":
            out = (f'<div class="setup-reboot"><b>{e(S.SETUP_REBOOT_TITLE)}</b>'
                   f'<p>{e(self.reboot or "")}</p></div>')
        elif self.status == "error":
            text = e(self.error or "").replace("\n", "<br>")
            out = f'<div class="section-msg err">{e(self.error_title or S.SETUP_ERROR)}: {text}</div>'
        elif self.status == "done" and self.done_text:
            out = f'<div class="train-status ok">{e(self.done_text)}</div>'
        elif self.status == "done":
            missing = any(not i.ok and not i.optional for i in self.items or [])
            out = (f'<div class="section-msg err">{e(S.SETUP_DONE_MISSING)}</div>' if missing
                   else f'<div class="train-status ok">{e(S.SETUP_DONE)}</div>')
        elif self.status == "running":
            out = f'<div class="train-status">{e(S.SETUP_RUNNING)}</div>'
        else:
            out = f'<div class="section-msg muted">{e(S.SETUP_IDLE)}</div>'
        if self.check_error:
            out += f'<div class="section-msg err">{e(self.check_error)}</div>'
        return out


def data_dir_html(path: Path, source: str, disk_usage=shutil.disk_usage) -> str:
    """Hint under the dependency-folder box: free space on that drive (or why it can't be changed here)."""
    from omnivoice.datadir import human_size
    drive = Path(path).drive or Path(path).anchor or str(path)
    try:
        text = S.DATA_DIR_FREE.format(drive=drive, free=human_size(disk_usage(Path(path).anchor or str(path)).free))
        cls = "section-msg muted"
    except (OSError, ValueError):
        text, cls = S.DATA_DIR_NO_DRIVE.format(drive=drive), "section-msg err"
    out = f'<div class="{cls}">{html.escape(text)}</div>'
    if source == "env":
        out += f'<div class="section-msg err">{html.escape(S.DATA_DIR_ENV)}</div>'
    return out


# ---------- per-project write lock ----------

class ProjectBusy(RuntimeError):
    pass


class ProjectLocks:
    """One non-blocking lock per project (keyed by resolved root) plus the running operation's name."""

    def __init__(self):
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._ops: dict[str, str] = {}

    @staticmethod
    def _key(root) -> str:
        return str(Path(root).resolve())

    def acquire(self, root, op: str) -> None:
        """Take the project's lock or raise ProjectBusy naming the operation that holds it."""
        key = self._key(root)
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
            if not lock.acquire(blocking=False):
                raise ProjectBusy(S.PROJECT_BUSY.format(op=self._ops.get(key, "?")))
            self._ops[key] = op

    def release(self, root) -> None:
        key = self._key(root)
        with self._guard:
            self._ops.pop(key, None)
            lock = self._locks.get(key)
            if lock is not None and lock.locked():
                lock.release()

    def busy(self, root) -> str | None:
        with self._guard:
            return self._ops.get(self._key(root))

    @contextmanager
    def hold(self, root, op: str):
        self.acquire(root, op)
        try:
            yield
        finally:
            self.release(root)


# ---------- install ----------

def check_install_target(target) -> Path:
    """Install target must be an existing absolute folder; it is never created from the UI."""
    text = (target or "").strip()
    if not text:
        raise ValueError(S.INSTALL_NO_TARGET)
    path = Path(text)
    if not path.is_absolute():
        raise ValueError(S.TARGET_NOT_ABSOLUTE)
    if not path.is_dir():
        raise ValueError(S.TARGET_NOT_FOUND.format(path=path))
    return path


# ---------- pack ----------

def counter_label(label: str, text: str, key: str) -> str:
    n, limit = len(text or ""), modrules.LIMITS[key]
    return f"{label} · {n}/{limit}" + (" ⚠" if n > limit else "")


def portrait_preview(path: Path, scale: int = 6) -> Image.Image:
    """What the mod will show: make_portrait() result, upscaled nearest-neighbour."""
    from omnivoice.portrait import make_portrait
    img = Image.open(io.BytesIO(make_portrait(Path(path).read_bytes()))).convert("RGBA")
    side = 32 * scale
    return img.resize((side, side), Image.NEAREST)


# ---------- errors ----------

def error_text(e: BaseException) -> str:
    problems = getattr(e, "problems", None)
    if problems:
        return "\n".join(str(p) for p in problems)
    return str(e).strip() or S.ERR_UNKNOWN
