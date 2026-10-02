"""SQLite persistence round trip, independent of the generator."""

import sqlite3

from cue_sheet_gate import db
from cue_sheet_gate.models import Episode, LicenseRecord, MusicEvent


def test_license_insert_and_fetch_round_trip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)

    lic = LicenseRecord(
        id=None, library="APM Music", usage_type="Theme", term_start="2024-01-01",
        term_end="2024-12-31", territory="World", media_type="All Media", pro="ASCAP",
    )
    lic_id = db.insert_license(conn, lic)
    fetched = db.fetch_all_licenses(conn)
    assert len(fetched) == 1
    assert fetched[0].id == lic_id
    assert fetched[0].library == "APM Music"
    assert fetched[0].territory == "World"
    conn.close()


def test_episode_and_event_insert_and_fetch_round_trip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)

    ep = Episode(id=None, program="Harborline", episode_number=1,
                 episode_title="Episode 1", air_date="2024-06-15")
    ep_id = db.insert_episode(conn, ep)

    ev = MusicEvent(
        id=None, episode_id=ep_id, air_date="2024-06-15", cue_title="Test Cue",
        composer="X", publisher="Y", pro="ASCAP", usage_type="Theme", library="APM Music",
        territory="United States", media_type="Broadcast Television",
        in_timecode="00:00:00:00", out_timecode="00:00:10:00", duration_seconds=10.0,
        composer_share_pct=50.0, publisher_share_pct=50.0,
        intended_license_id=None, is_seeded_defect=False, seeded_reason=None,
    )
    db.insert_music_event(conn, ev)

    fetched_ep = db.fetch_episode(conn, ep_id)
    assert fetched_ep.program == "Harborline"

    fetched_events = db.fetch_events_for_episode(conn, ep_id)
    assert len(fetched_events) == 1
    assert fetched_events[0].cue_title == "Test Cue"
    assert fetched_events[0].composer_share_pct == 50.0
    conn.close()


def test_reset_db_clears_all_tables():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    ep = Episode(id=None, program="Harborline", episode_number=1,
                 episode_title="Episode 1", air_date="2024-06-15")
    db.insert_episode(conn, ep)
    assert len(db.fetch_all_episodes(conn)) == 1

    db.reset_db(conn)
    assert len(db.fetch_all_episodes(conn)) == 0
    conn.close()
