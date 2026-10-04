"""omnivoice's entry for `piper.train fit`: piper's own CLI with lighter, stop-safe checkpointing.

piper keeps the 5 best checkpoints by val_mel and the 5 best by val_mos (each ~850 MB). Lightning stages
every file in /tmp and then copies it into the project, which under WSL means a copy to the Windows
disk: 12-25 s per file, so a one-second epoch took ~40 s while the top-5 lists were filling. Here:
  * one best checkpoint per metric;
  * val_mos skips the warm-up epochs: they still sound like the base voice and score a high MOS, so the
    single slot would otherwise stay on the first epoch for good (same warm-up as omnivoice.previews);
  * last.ckpt every --omnivoice-last-every epochs, on the final epoch and on a graceful stop, written
    beside its final name and renamed into place, so a stop never leaves a half-written last.ckpt;
  * graceful stop: <default_root_dir>/STOP makes the run stop after the current batch and save.

python fit.py [--omnivoice-base-epoch N] [--omnivoice-last-every N] fit <piper.train fit arguments>
Runs inside the training environment (WSL distro / Docker image) where piper and Lightning live.
"""
import os
import sys
from pathlib import Path

STOP_FILE = "STOP"
LAST = "last.ckpt"
LAST_EPOCH = "last.epoch"  # the epoch last.ckpt holds: its training events may run further
WARMUP_MIN, WARMUP_SHARE = 20, 0.05


def pop_int(argv: list, name: str, default: int) -> int:
    """Remove `name value` from argv (LightningCLI must not see it) and return the value."""
    if name not in argv:
        return default
    i = argv.index(name)
    value = int(argv[i + 1])
    del argv[i:i + 2]
    return value


def warmup_end(base: int, max_epochs: int) -> int:
    """First epoch that may be «best by MOS»: base + 1 + max(WARMUP_MIN, WARMUP_SHARE of the planned epochs)."""
    planned = max(0, max_epochs - base - 1)
    return base + 1 + max(WARMUP_MIN, round(planned * WARMUP_SHARE))


def last_due(epoch: int, max_epochs: int, every: int, stopping: bool) -> bool:
    return stopping or (epoch + 1) % every == 0 or epoch + 1 >= max_epochs


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    base = pop_int(argv, "--omnivoice-base-epoch", 0)
    every = max(1, pop_int(argv, "--omnivoice-last-every", 10))

    from lightning.pytorch.callbacks import Callback, ModelCheckpoint
    import piper.train.__main__ as piper_main

    class WarmupCheckpoint(ModelCheckpoint):
        """A best-by-metric checkpoint that ignores the warm-up epochs."""

        def setup(self, trainer, pl_module, stage):
            super().setup(trainer, pl_module, stage)
            self.first_epoch = warmup_end(base, trainer.max_epochs or 0)

        def _save_topk_checkpoint(self, trainer, monitor_candidates):
            if trainer.current_epoch >= getattr(self, "first_epoch", 0):
                super()._save_topk_checkpoint(trainer, monitor_candidates)

    class SparseLast(Callback):
        """last.ckpt every `every` epochs / at the end / on a graceful stop, written atomically."""

        def __init__(self):
            self.saved_step = None
            self.val_epoch = None

        @staticmethod
        def _stop_file(trainer) -> Path:
            return Path(trainer.default_root_dir) / STOP_FILE

        def on_train_start(self, trainer, pl_module):
            folder = Path(trainer.checkpoint_callback.dirpath)
            (folder / (LAST + ".part")).unlink(missing_ok=True)  # left by a run killed mid-save

        def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx):
            if self._stop_file(trainer).exists():
                trainer.should_stop = True

        def on_validation_end(self, trainer, pl_module):
            if trainer.sanity_checking:
                return
            self.val_epoch = trainer.current_epoch
            if last_due(trainer.current_epoch, trainer.max_epochs or 0, every, trainer.should_stop):
                self._save(trainer)

        def on_train_end(self, trainer, pl_module):
            self._save(trainer)  # the final or stopped state, unless this step is saved already

        def _save(self, trainer):
            if trainer.global_step == self.saved_step or not trainer.is_global_zero:
                return
            folder = Path(trainer.checkpoint_callback.dirpath)
            folder.mkdir(parents=True, exist_ok=True)
            part = folder / (LAST + ".part")
            trainer.save_checkpoint(str(part))
            os.replace(part, folder / LAST)
            epoch = self.val_epoch if self.val_epoch is not None else trainer.current_epoch
            (folder / LAST_EPOCH).write_text(str(epoch), encoding="utf-8")
            self.saved_step = trainer.global_step

    piper_main._DEFAULT_CALLBACKS[:] = [
        ModelCheckpoint(monitor="val_mel", mode="min", save_top_k=1, save_last=False,
                        filename="epoch={epoch}-val_mel={val_mel:.4f}", auto_insert_metric_name=False),
        WarmupCheckpoint(monitor="val_mos", mode="max", save_top_k=1, save_last=False,
                         filename="epoch={epoch}-val_mos={val_mos:.4f}", auto_insert_metric_name=False),
        SparseLast(),
    ]
    sys.argv = [sys.argv[0], *argv]
    piper_main.main()


if __name__ == "__main__":
    main()
