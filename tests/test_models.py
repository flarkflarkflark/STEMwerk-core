from stemwerk_core.models import AVAILABLE_MODELS, resolve_model_name


def test_model_mapping_contains_expected_keys() -> None:
    expected = {
        "htdemucs": "htdemucs.yaml",
        "htdemucs_ft": "htdemucs_ft.yaml",
        "htdemucs_6s": "htdemucs_6s.yaml",
        "hdemucs_mmi": "hdemucs_mmi.yaml",
    }
    assert AVAILABLE_MODELS == expected


def test_resolve_model_name_passthrough() -> None:
    assert resolve_model_name("htdemucs") == "htdemucs.yaml"
    assert resolve_model_name("custom_model.yaml") == "custom_model.yaml"
