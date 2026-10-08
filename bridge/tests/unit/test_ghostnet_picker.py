from datetime import UTC, datetime, timedelta

from ghostjs8.contract.messages import ReceiverListing
from ghostjs8.ghostnet.picker import ReceiverPicker, distance_km
from ghostjs8.util.maidenhead import grid_center

NOW = datetime(2026, 10, 9, tzinfo=UTC)


def rx(id: str, lat: float | None, lon: float | None, **kw: object) -> ReceiverListing:
    base: dict[str, object] = dict(
        id=id,
        name=id,
        host=f"{id}.example",
        port=8073,
        tls=False,
        location="",
        grid=None,
        lat=lat,
        lon=lon,
        users=0,
        users_max=4,
        min_hz=0,
        max_hz=30_000_000,
        antenna="",
        snr_db=30,
    )
    base.update(kw)
    return ReceiverListing(**base)  # type: ignore[arg-type]


HOME = grid_center("EM73")  # Atlanta area


def test_distance() -> None:
    assert round(distance_km(0, 0, 0, 1)) == 111
    assert distance_km(10, 10, 10, 10) == 0


def test_ranks_by_distance_and_filters() -> None:
    picker = ReceiverPicker(HOME)
    listings = [
        rx("far", 47.6, -122.3),  # Seattle
        rx("near", 34.0, -84.0),  # Atlanta
        rx("mid", 39.0, -77.0),  # DC
        rx("full", 33.9, -84.1, users=4),
        rx("noisy", 33.8, -84.2, snr_db=8),
        rx("vlf", 33.7, -84.3, max_hz=1_000_000),
        rx("nogps", None, None),
    ]
    ranked = picker.rank(listings, 7_107_000, NOW)
    assert [c.listing.id for c in ranked] == ["near", "mid", "far"]
    assert ranked[0].reason.startswith("nearest free receiver:")


def test_bench_cooldown() -> None:
    picker = ReceiverPicker(HOME, cooldown=timedelta(minutes=30))
    listings = [rx("near", 34.0, -84.0), rx("mid", 39.0, -77.0)]
    picker.bench("near", NOW)
    assert [c.listing.id for c in picker.rank(listings, 7_107_000, NOW)] == ["mid"]
    later = NOW + timedelta(minutes=31)
    assert [c.listing.id for c in picker.rank(listings, 7_107_000, later)] == ["near", "mid"]
