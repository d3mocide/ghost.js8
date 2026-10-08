import pytest

from ghostjs8.util.maidenhead import grid_center, normalize_grid


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("EN34", "EN34"),
        ("en34", "EN34"),
        ("FN31pr", "FN31pr"),
        ("fn31PR", "FN31pr"),
        ("JO65ab12", "JO65ab12"),
        (" EM73 ", "EM73"),
        ("RR99xx", "RR99xx"),
    ],
)
def test_valid(raw: str, norm: str) -> None:
    assert normalize_grid(raw) == norm


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "EN",
        "SN34",
        "EN3",
        "EN345",
        "EN34y",
        "EN34yz",
        "EN34ab1",
        "1234",
        "EN34ab1x",
        "N0CALL",
        "@ALLCALL",
        "EN34-",
    ],
)
def test_invalid(raw: str | None) -> None:
    assert normalize_grid(raw) is None


def test_centres() -> None:
    lat, lon = grid_center("FN31pr")
    assert (round(lat, 3), round(lon, 3)) == (41.729, -72.708)
    lat, lon = grid_center("EN34")
    assert (lat, lon) == (44.5, -93.0)
    with pytest.raises(ValueError, match="invalid"):
        grid_center("ZZ99")
