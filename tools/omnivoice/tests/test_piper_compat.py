from omnivoice import piper_compat, train

def test_install_shim_writes_pth_and_module(tmp_path):
    pth = piper_compat.install_shim(tmp_path)
    assert pth.read_text(encoding="utf-8").strip() == "import omnivoice_torch_shim"
    assert "weights_only" in (tmp_path / "omnivoice_torch_shim.py").read_text(encoding="utf-8")

def test_docker_context_is_shipped_in_package():
    assert (train.DOCKER_DIR / "Dockerfile").is_file()
    assert (train.DOCKER_DIR / "torch_shim.py").is_file() and (train.DOCKER_DIR / "clean_ckpt.py").is_file()

def test_clean_command_points_at_script():
    cmd = piper_compat.clean_command("a.ckpt", "b.ckpt")
    assert cmd[1].endswith("clean_ckpt.py") and cmd[2:] == ["a.ckpt", "b.ckpt"]
