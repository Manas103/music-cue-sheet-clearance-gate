"""Unit tests on the reconciliation engine's matching logic, independent of
the synthetic dataset: hand-built license/event pairs, one dimension
varied at a time, boundary dates included.
"""

from dataclasses import replace

from cue_sheet_gate.models import (
    LICENSE_EXPIRED,
    LICENSE_NOT_YET_EFFECTIVE,
    LicenseRecord,
    MusicEvent,
    NO_LICENSE_RECORD,
    PRO_MISMATCH,
    WRONG_MEDIA_TYPE,
    WRONG_TERRITORY,
)
from cue_sheet_gate.reconcile import build_license_index, find_covering_license


def _license(**kwargs):
    base = dict(
        id=1, library="APM Music", usage_type="Theme", term_start="2024-01-01",
        term_end="2024-12-31", territory="United States", media_type="Broadcast Television",
        pro="ASCAP",
    )
    base.update(kwargs)
    return LicenseRecord(**base)


def _event(**kwargs):
    base = dict(
        id=1, episode_id=1, air_date="2024-06-15", cue_title="Test Cue",
        composer="X", publisher="Y", pro="ASCAP", usage_type="Theme", library="APM Music",
        territory="United States", media_type="Broadcast Television", in_timecode="00:00:00:00",
        out_timecode="00:00:10:00", duration_seconds=10.0, composer_share_pct=50.0,
        publisher_share_pct=50.0,
    )
    base.update(kwargs)
    return MusicEvent(**base)


def test_exact_match_is_covered():
    lic = _license()
    ev = _event()
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is not None
    assert reason is None


def test_air_date_on_term_start_boundary_is_covered():
    lic = _license(term_start="2024-06-15")
    ev = _event(air_date="2024-06-15")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is not None and reason is None


def test_air_date_on_term_end_boundary_is_covered():
    lic = _license(term_end="2024-06-15")
    ev = _event(air_date="2024-06-15")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is not None and reason is None


def test_air_date_one_day_after_term_end_is_expired():
    lic = _license(term_end="2024-06-14")
    ev = _event(air_date="2024-06-15")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == LICENSE_EXPIRED


def test_air_date_one_day_before_term_start_is_not_yet_effective():
    lic = _license(term_start="2024-06-16")
    ev = _event(air_date="2024-06-15")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == LICENSE_NOT_YET_EFFECTIVE


def test_no_license_for_library_usage_key_at_all():
    lic = _license(library="Extreme Music")
    ev = _event(library="APM Music")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == NO_LICENSE_RECORD


def test_world_license_covers_any_event_territory():
    lic = _license(territory="World")
    for territory in ("United States", "United States and Canada", "World"):
        ev = _event(territory=territory)
        index = build_license_index([lic])
        found, reason = find_covering_license(ev, index)
        assert found is not None and reason is None, territory


def test_us_only_license_does_not_cover_world_event():
    lic = _license(territory="United States")
    ev = _event(territory="World")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == WRONG_TERRITORY


def test_us_canada_license_covers_us_but_not_world():
    lic = _license(territory="United States and Canada")
    index = build_license_index([lic])

    found, reason = find_covering_license(_event(territory="United States"), index)
    assert found is not None and reason is None

    found, reason = find_covering_license(_event(territory="World"), index)
    assert found is None and reason == WRONG_TERRITORY


def test_broadcast_only_license_does_not_cover_all_media_event():
    lic = _license(media_type="Broadcast Television")
    ev = _event(media_type="All Media")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == WRONG_MEDIA_TYPE


def test_all_media_license_covers_broadcast_only_event():
    lic = _license(media_type="All Media")
    ev = _event(media_type="Broadcast Television")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is not None and reason is None


def test_pro_mismatch():
    lic = _license(pro="ASCAP")
    ev = _event(pro="BMI")
    index = build_license_index([lic])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == PRO_MISMATCH


def test_multiple_candidates_same_key_one_covers():
    bad = _license(id=1, territory="United States", media_type="Broadcast Television")
    good = _license(id=2, territory="World", media_type="All Media")
    ev = _event(territory="World", media_type="All Media")
    index = build_license_index([bad, good])
    found, reason = find_covering_license(ev, index)
    assert found is not None and found.id == 2 and reason is None


def test_multiple_candidates_same_key_none_covers_reports_closest():
    # One candidate fails at territory (stage 1), the other fails further
    # along, at PRO (stage 3); the PRO failure is reported because it is
    # the "closer to covering" candidate.
    territory_fail = _license(id=1, territory="United States", pro="ASCAP")
    pro_fail = _license(id=2, territory="World", pro="BMI")
    ev = _event(territory="World", pro="ASCAP")
    index = build_license_index([territory_fail, pro_fail])
    found, reason = find_covering_license(ev, index)
    assert found is None
    assert reason == PRO_MISMATCH
