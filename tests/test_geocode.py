"""Tests for travel_video.geocode — written FIRST (TDD Red phase)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from travel_video.geocode import Location, reverse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GEOCODE_CACHE_FILENAME = "geocode.json"


def _make_nominatim_result(
    city: str | None = "Berlin",
    town: str | None = None,
    village: str | None = None,
    hamlet: str | None = None,
    county: str | None = None,
    country: str = "Germany",
    country_code: str = "de",
) -> MagicMock:
    """Return a mock geopy Location object with the specified address fields."""
    address: dict = {"country": country, "country_code": country_code}
    if city is not None:
        address["city"] = city
    if town is not None:
        address["town"] = town
    if village is not None:
        address["village"] = village
    if hamlet is not None:
        address["hamlet"] = hamlet
    if county is not None:
        address["county"] = county

    mock_loc = MagicMock()
    mock_loc.raw = {"address": address}
    return mock_loc


# ---------------------------------------------------------------------------
# 1. Successful lookup — returns correct Location
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_successful_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """reverse() returns a populated Location on a successful geocode."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(city="Berlin", country="Germany", country_code="de")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_geocoder_instance = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder_instance

        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl = MagicMock(return_value=mock_result)
            mock_rl_cls.return_value = mock_rl

            result = reverse(52.5200, 13.4050)

    assert result is not None
    assert isinstance(result, Location)
    assert result.town == "Berlin"
    assert result.country == "Germany"
    assert result.iso == "DE"


@pytest.mark.unit
def test_reverse_iso_uppercased(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """reverse() upcases the ISO country code regardless of Nominatim's casing."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(city="Paris", country="France", country_code="fr")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            result = reverse(48.8566, 2.3522)

    assert result is not None
    assert result.iso == "FR"


# ---------------------------------------------------------------------------
# 2. Coordinates rounded to 4 decimal places for cache key
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_cache_key_rounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache entries are keyed by coordinates rounded to 4 decimal places."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_dir))

    mock_result = _make_nominatim_result(city="Berlin", country="Germany", country_code="de")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            reverse(52.52001234, 13.40501234)  # extra decimals should be rounded

    geocode_file = cache_dir / "metadata" / GEOCODE_CACHE_FILENAME
    assert geocode_file.exists(), "geocode.json cache file must be created"

    cache_data = json.loads(geocode_file.read_text())
    expected_key = f"{round(52.52001234, 4)},{round(13.40501234, 4)}"
    assert expected_key in cache_data, f"Expected key '{expected_key}' not found in {cache_data}"


# ---------------------------------------------------------------------------
# 3. Cache hit — Nominatim NOT called second time for same coords
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_cache_hit_skips_nominatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second call with the same (rounded) coordinates must not call Nominatim."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_dir))

    mock_result = _make_nominatim_result(city="Berlin", country="Germany", country_code="de")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl = MagicMock(return_value=mock_result)
            mock_rl_cls.return_value = mock_rl

            first = reverse(52.5200, 13.4050)
            second = reverse(52.5200, 13.4050)

    # RateLimiter callable was constructed once; verify it was only invoked once
    assert mock_rl.call_count == 1, (
        "Nominatim geocoder must only be called once (cache hit on second)"
    )
    assert first == second


@pytest.mark.unit
def test_reverse_cache_hit_across_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache persists on disk so a fresh call also skips Nominatim."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_dir))

    mock_result = _make_nominatim_result(city="Rome", country="Italy", country_code="it")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            reverse(41.9028, 12.4964)

    # Second independent call — Nominatim should not be called at all
    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls2:
        mock_nominatim_cls2.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls2:
            mock_rl2 = MagicMock()
            mock_rl_cls2.return_value = mock_rl2
            result = reverse(41.9028, 12.4964)

    assert mock_rl2.call_count == 0, "Second independent call must use on-disk cache"
    assert result is not None
    assert result.town == "Rome"
    assert result.iso == "IT"


# ---------------------------------------------------------------------------
# 4. None coordinates return None immediately
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_none_lat_returns_none() -> None:
    """reverse(None, 13.0) must return None without calling Nominatim."""
    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl = MagicMock()
            mock_rl_cls.return_value = mock_rl
            result = reverse(None, 13.0)

    assert result is None
    assert mock_rl.call_count == 0


@pytest.mark.unit
def test_reverse_none_lon_returns_none() -> None:
    """reverse(52.0, None) must return None without calling Nominatim."""
    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl = MagicMock()
            mock_rl_cls.return_value = mock_rl
            result = reverse(52.0, None)

    assert result is None
    assert mock_rl.call_count == 0


@pytest.mark.unit
def test_reverse_both_none_returns_none() -> None:
    """reverse(None, None) must return None without calling Nominatim."""
    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl = MagicMock()
            mock_rl_cls.return_value = mock_rl
            result = reverse(None, None)

    assert result is None
    assert mock_rl.call_count == 0


# ---------------------------------------------------------------------------
# 5. Nominatim raises exception — returns None
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_nominatim_raises_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reverse() must return None when the geocoder raises any exception."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(side_effect=Exception("network error"))
            result = reverse(52.5200, 13.4050)

    assert result is None


@pytest.mark.unit
def test_reverse_geocoder_returns_none_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reverse() must return None when the geocoder returns None (location not found)."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=None)
            result = reverse(0.0, 0.0)

    assert result is None


# ---------------------------------------------------------------------------
# 6. Town fallback priority: city → town → village → hamlet → county
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_town_fallback_to_town(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When 'city' is absent, 'town' is used."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(
        city=None, town="Smallville", country="Germany", country_code="de"
    )

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            result = reverse(51.0, 9.0)

    assert result is not None
    assert result.town == "Smallville"


@pytest.mark.unit
def test_reverse_town_fallback_to_village(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When 'city' and 'town' are absent, 'village' is used."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(
        city=None, town=None, village="Hamletburg", country="Germany", country_code="de"
    )

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            result = reverse(51.0, 9.0)

    assert result is not None
    assert result.town == "Hamletburg"


@pytest.mark.unit
def test_reverse_town_fallback_to_hamlet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When city/town/village are absent, 'hamlet' is used."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(
        city=None, town=None, village=None, hamlet="Tiny Hamlet",
        country="Germany", country_code="de"
    )

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            result = reverse(51.0, 9.0)

    assert result is not None
    assert result.town == "Tiny Hamlet"


@pytest.mark.unit
def test_reverse_town_fallback_to_county(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When city/town/village/hamlet are absent, 'county' is used."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(
        city=None,
        town=None,
        village=None,
        hamlet=None,
        county="Big County",
        country="USA",
        country_code="us",
    )

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            result = reverse(36.0, -115.0)

    assert result is not None
    assert result.town == "Big County"


@pytest.mark.unit
def test_reverse_all_town_keys_missing_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When none of the town-fallback keys are present, return None."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_loc = MagicMock()
    mock_loc.raw = {"address": {"country": "Oceania", "country_code": "oc"}}

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_loc)
            result = reverse(-10.0, 160.0)

    assert result is None


# ---------------------------------------------------------------------------
# 7. TRAVEL_VIDEO_CACHE_DIR env var controls cache location
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_env_var_controls_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """geocode.json is written inside the directory set by TRAVEL_VIDEO_CACHE_DIR."""
    custom_cache = tmp_path / "custom_geocache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(custom_cache))

    mock_result = _make_nominatim_result(city="Tokyo", country="Japan", country_code="jp")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            reverse(35.6762, 139.6503)

    expected_file = custom_cache / "metadata" / GEOCODE_CACHE_FILENAME
    assert expected_file.exists(), f"Expected cache file at {expected_file}"

    data = json.loads(expected_file.read_text())
    assert len(data) == 1


@pytest.mark.unit
def test_reverse_different_cache_dirs_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Data stored under one cache dir is invisible when a different dir is active."""
    dir_a = tmp_path / "cache_a"
    dir_b = tmp_path / "cache_b"

    mock_result = _make_nominatim_result(city="Sydney", country="Australia", country_code="au")

    # Populate cache dir_a
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(dir_a))
    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            reverse(-33.8688, 151.2093)

    # Switch to dir_b — should NOT see dir_a's cache
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(dir_b))
    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls2:
        mock_nominatim_cls2.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls2:
            mock_rl2 = MagicMock(return_value=mock_result)
            mock_rl_cls2.return_value = mock_rl2
            reverse(-33.8688, 151.2093)

    # Nominatim was called because dir_b has no cached entry
    assert mock_rl2.call_count == 1, "Should have hit Nominatim because dir_b cache is empty"


# ---------------------------------------------------------------------------
# 8. user_agent is forwarded to Nominatim
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reverse_custom_user_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The user_agent kwarg is passed through to Nominatim."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    mock_result = _make_nominatim_result(city="Vienna", country="Austria", country_code="at")

    with patch("travel_video.geocode.Nominatim") as mock_nominatim_cls:
        mock_nominatim_cls.return_value = MagicMock()
        with patch("travel_video.geocode.RateLimiter") as mock_rl_cls:
            mock_rl_cls.return_value = MagicMock(return_value=mock_result)
            reverse(48.2082, 16.3738, user_agent="my-custom-agent")

    mock_nominatim_cls.assert_called_once_with(user_agent="my-custom-agent")


# ---------------------------------------------------------------------------
# 9. Location is a frozen dataclass (immutable)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_location_is_immutable() -> None:
    """Location must be a frozen dataclass — attribute assignment must raise."""
    loc = Location(town="Berlin", country="Germany", iso="DE")
    with pytest.raises((AttributeError, TypeError)):
        loc.town = "Munich"  # type: ignore[misc]


@pytest.mark.unit
def test_location_fields() -> None:
    """Location exposes town, country, and iso fields."""
    loc = Location(town="Oslo", country="Norway", iso="NO")
    assert loc.town == "Oslo"
    assert loc.country == "Norway"
    assert loc.iso == "NO"
