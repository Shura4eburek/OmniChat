import io
from pathlib import Path
import onnx
from onnx import helper, TensorProto
from PIL import Image

def make_onnx(path: Path, meta: dict[str, str]) -> Path:
    node = helper.make_node("Identity", ["x"], ["y"])
    graph = helper.make_graph([node], "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])])
    model = helper.make_model(graph)
    for k, v in meta.items():
        p = model.metadata_props.add(); p.key = k; p.value = v
    onnx.save(model, path)
    return path

def png(w: int, h: int) -> bytes:
    buf = io.BytesIO(); Image.new("RGBA", (w, h), (53, 224, 200, 255)).save(buf, "PNG")
    return buf.getvalue()
