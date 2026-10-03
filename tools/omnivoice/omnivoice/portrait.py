from __future__ import annotations
import io
from PIL import Image
from omnivoice.modrules import MAX_PORTRAIT_BYTES

def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO(); img.save(buf, "PNG", optimize=True); return buf.getvalue()

def make_portrait(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    for size in (32, 16):
        small = img.resize((size, size), Image.NEAREST)
        for candidate in (small, small.quantize(64).convert("RGBA")):
            data = _png(candidate)
            if len(data) <= MAX_PORTRAIT_BYTES:
                return data
    raise ValueError("Не удалось ужать портрет до 8 КБ")
