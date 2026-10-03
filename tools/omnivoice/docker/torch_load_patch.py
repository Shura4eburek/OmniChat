# Compatibility shims for piper1-gpl v1.8.0 on PyTorch >= 2.6, loaded at interpreter start via torch_load_patch.pth.
try:
    import functools
    import torch

    # Piper checkpoints pickle pathlib objects, but Lightning loads them with
    # weights_only=True, which rejects them. The checkpoints come from
    # rhasspy/piper-checkpoints or the user's own training, so allow a full load.
    _orig_load = torch.load

    @functools.wraps(_orig_load)
    def _load(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_load(*args, **kwargs)

    torch.load = _load

    # torch.onnx.export defaults to the dynamo exporter now; piper's VITS export
    # only traces with the TorchScript exporter.
    import torch.onnx

    _orig_export = torch.onnx.export

    @functools.wraps(_orig_export)
    def _export(*args, **kwargs):
        kwargs.setdefault("dynamo", False)
        return _orig_export(*args, **kwargs)

    torch.onnx.export = _export
except ImportError:
    pass
