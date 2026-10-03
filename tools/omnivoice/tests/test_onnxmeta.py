from omnivoice import onnxmeta
from tests.helpers import make_onnx
from omnivoice.modrules import read_onnx_metadata

CFG = {"audio": {"sample_rate": 22050}, "espeak": {"voice": "ru"}, "num_speakers": 1,
       "phoneme_id_map": {"_": [0], "^": [1], " ": [3], "\n": [9], "a": 5}}

def test_piper_metadata_exact_keys():
    m = onnxmeta.piper_metadata(CFG, "Russian", "0.1.0")
    assert m == {"model_type": "vits", "comment": "piper", "language": "Russian", "voice": "ru", "version": "1",
                 "has_espeak": "1", "n_speakers": "1", "sample_rate": "22050", "omnivoice_version": "0.1.0"}

def test_tokens_from_config_edge_cases():
    assert onnxmeta.tokens_from_config(CFG) == "_ 0\n^ 1\n  3\na 5\n"
    pt = dict(CFG, espeak={"voice": "pt-PT"}, audio={"sample_rate": 22500})
    m = onnxmeta.piper_metadata(pt, "Portuguese", "0.1.0")
    assert m["voice"] == "pt" and m["sample_rate"] == "22050"

def test_write_metadata_replaces_existing(tmp_path):
    src = make_onnx(tmp_path / "a.onnx", {"comment": "old", "junk": "1"})
    onnxmeta.write_metadata(src, tmp_path / "b.onnx", {"n_speakers": "1", "comment": "piper", "voice": "ru"})
    assert read_onnx_metadata(tmp_path / "b.onnx") == {"n_speakers": "1", "comment": "piper", "voice": "ru"}
    assert read_onnx_metadata(src) == {"comment": "old", "junk": "1"}

def test_tokens_skip_vowel_cluster_entries():
    cfg = {"phoneme_id_map": {"a": [5], "ɪ": [6], "aɪ": [161]}}
    assert onnxmeta.tokens_from_config(cfg) == "a 5\nɪ 6\n"

def test_tokens_refuse_models_trained_with_vowel_clusters():
    import pytest
    with pytest.raises(ValueError, match="vowel_clusters"):
        onnxmeta.tokens_from_config({"phoneme_id_map": {"a": [5]}, "vowel_clusters": [["a", "ɪ"]]})
