"""Make an old rhasspy piper checkpoint loadable by piper1-gpl's LightningCLI.

Newer Lightning parses a checkpoint's hyper_parameters as CLI config and rejects
keys VitsModel doesn't accept (sample_bytes, gpus, ...). Keep only known keys.
Usage: python3 clean_ckpt.py <in.ckpt> <out.ckpt>
"""
import inspect
import sys

import torch
from piper.train.vits.lightning import VitsModel

src, dst = sys.argv[1], sys.argv[2]
ckpt = torch.load(src, map_location="cpu", weights_only=False)
known = set(inspect.signature(VitsModel.__init__).parameters) - {"self"}
hp = ckpt.get("hyper_parameters", {})
ckpt["hyper_parameters"] = {k: v for k, v in hp.items() if k in known}
torch.save(ckpt, dst)
print(f"cleaned {len(hp) - len(ckpt['hyper_parameters'])} unknown hparams -> {dst}")
