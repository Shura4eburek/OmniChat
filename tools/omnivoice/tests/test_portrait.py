import io
from PIL import Image
from omnivoice.portrait import make_portrait
from omnivoice.modrules import portrait_problem

def test_any_image_becomes_valid_portrait():
    buf = io.BytesIO(); Image.effect_noise((300, 200), 80).convert("RGB").save(buf, "PNG")
    out = make_portrait(buf.getvalue())
    assert portrait_problem(out) is None

def test_many_colour_large_image_hits_quantize_path():
    import os
    img = Image.frombytes("RGB", (512, 512), os.urandom(512 * 512 * 3))
    buf = io.BytesIO(); img.save(buf, "PNG")
    assert portrait_problem(make_portrait(buf.getvalue())) is None
