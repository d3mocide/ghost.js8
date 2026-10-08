import pytest

from ghostjs8.receivers.directory import Directory, DirectoryError, parse_directory
from ghostjs8.util.clock import ManualClock

# Shape of rx.linkfanel.net/kiwisdr_com.js (trimmed, values synthetic).
SAMPLE = """// KiwiSDR.com receiver list for dyatlov map maker
var kiwisdr_com =
[
	{
		"id":"aaa", "status":"active", "offline":"no", "name":"Test RX | Somewhere",
		"bands":"10000-32000000", "users":"3", "users_max":"4", "gps":"(46.427049, 0.888543)",
		"grid":"JN06kj", "loc":"Somewhere FRANCE", "antenna":"Loop", "snr":"47,43",
		"url":"http://192.0.2.10:8073"
	},
	{
		"id":"bbb", "status":"active", "offline":"no", "name":"Proxied", "bands":"0-30000000",
		"users":"0", "users_max":"8", "gps":"", "grid":"N0CALL", "url":"http://22204.proxy.kiwisdr.com",
	},
	{"id":"ccc", "status":"active", "offline":"yes", "url":"http://198.51.100.1:8073"},
	{"id":"ddd", "status":"active", "offline":"no", "url":"javascript:alert(1)"},
]
;
"""


def test_parse_sample() -> None:
    rx = parse_directory(SAMPLE)
    assert [r.id for r in rx] == ["aaa", "bbb"]
    a, b = rx
    assert (a.host, a.port, a.tls) == ("192.0.2.10", 8073, False)
    assert (a.users, a.users_max, a.min_hz, a.max_hz) == (3, 4, 10_000, 32_000_000)
    assert (a.lat, a.lon, a.grid, a.snr_db) == (46.427049, 0.888543, "JN06kj", 47)
    assert (b.host, b.port) == ("22204.proxy.kiwisdr.com", 80)
    assert b.grid is None  # invalid grids are never passed on
    assert b.lat is None


def test_garbage_raises() -> None:
    with pytest.raises(DirectoryError):
        parse_directory("var x = 5;")


async def test_cache_ttl_and_stale_on_error() -> None:
    clock = ManualClock()
    calls: list[str] = []
    fail = False

    async def fetch(url: str) -> bytes:
        calls.append(url)
        if fail:
            raise OSError("network down")
        return SAMPLE.encode()

    d = Directory(clock=clock, fetch=fetch, ttl_s=900, retry_s=60)
    first = await d.get()
    assert not first.stale
    assert len(first.receivers) == 2
    await d.get()
    assert len(calls) == 1  # cached

    clock.advance(901)
    fail = True
    stale = await d.get()
    assert stale.stale
    assert len(stale.receivers) == 2  # last good list kept
    await d.get()
    assert len(calls) == 2  # no hammering within retry window

    clock.advance(61)
    fail = False
    again = await d.get()
    assert not again.stale
    assert len(calls) == 3


async def test_first_fetch_failure_is_empty_and_stale() -> None:
    async def fetch(url: str) -> bytes:
        raise OSError("offline")

    result = await Directory(clock=ManualClock(), fetch=fetch).get()
    assert result.stale
    assert result.receivers == []
