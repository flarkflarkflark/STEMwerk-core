from stemwerk_core import StemSeparator


def test_separator_instantiation_defaults() -> None:
    separator = StemSeparator()
    assert separator.model == "htdemucs"
    assert separator.device == "auto"
    assert separator.on_progress is None
