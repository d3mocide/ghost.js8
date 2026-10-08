import ghostjs8


def test_protocol_version_is_positive_int() -> None:
    assert isinstance(ghostjs8.PROTOCOL_VERSION, int)
    assert ghostjs8.PROTOCOL_VERSION >= 1


def test_version_is_resolvable() -> None:
    assert ghostjs8.__version__
