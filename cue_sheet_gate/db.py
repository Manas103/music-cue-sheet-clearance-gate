"""SQLite persistence: schema, connection helper, insert and fetch functions.

All dates are stored as ISO-8601 text ("YYYY-MM-DD"). SQLite has no native
date type; ISO-8601 text compares correctly under plain string comparison,
which the reconciliation and oracle modules both rely on for term-range
checks. See README Findings for the one place this almost went wrong.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, List, Optional

from cue_sheet_gate.models import Episode, LicenseRecord, MusicEvent

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS license_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library TEXT NOT NULL,
    usage_type TEXT NOT NULL,
    term_start TEXT NOT NULL,
    term_end TEXT NOT NULL,
    territory TEXT NOT NULL,
    media_type TEXT NOT NULL,
    pro TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program TEXT NOT NULL,
    episode_number INTEGER NOT NULL,
    episode_title TEXT NOT NULL,
    air_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS music_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    air_date TEXT NOT NULL,
    cue_title TEXT NOT NULL,
    composer TEXT NOT NULL,
    publisher TEXT NOT NULL,
    pro TEXT NOT NULL,
    usage_type TEXT NOT NULL,
    library TEXT NOT NULL,
    territory TEXT NOT NULL,
    media_type TEXT NOT NULL,
    in_timecode TEXT NOT NULL,
    out_timecode TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    composer_share_pct REAL NOT NULL,
    publisher_share_pct REAL NOT NULL,
    intended_license_id INTEGER REFERENCES license_records(id),
    is_seeded_defect INTEGER NOT NULL DEFAULT 0,
    seeded_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_music_events_episode ON music_events(episode_id);
CREATE INDEX IF NOT EXISTS idx_license_library_usage ON license_records(library, usage_type);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        "DROP TABLE IF EXISTS music_events;"
        "DROP TABLE IF EXISTS episodes;"
        "DROP TABLE IF EXISTS license_records;"
    )
    conn.commit()
    init_db(conn)


def insert_license(conn: sqlite3.Connection, lic: LicenseRecord) -> int:
    cur = conn.execute(
        "INSERT INTO license_records "
        "(library, usage_type, term_start, term_end, territory, media_type, pro) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lic.library, lic.usage_type, lic.term_start, lic.term_end, lic.territory,
         lic.media_type, lic.pro),
    )
    return cur.lastrowid


def insert_episode(conn: sqlite3.Connection, ep: Episode) -> int:
    cur = conn.execute(
        "INSERT INTO episodes (program, episode_number, episode_title, air_date) "
        "VALUES (?, ?, ?, ?)",
        (ep.program, ep.episode_number, ep.episode_title, ep.air_date),
    )
    return cur.lastrowid


def insert_music_event(conn: sqlite3.Connection, ev: MusicEvent) -> int:
    cur = conn.execute(
        "INSERT INTO music_events "
        "(episode_id, air_date, cue_title, composer, publisher, pro, usage_type, "
        " library, territory, media_type, in_timecode, out_timecode, duration_seconds, "
        " composer_share_pct, publisher_share_pct, intended_license_id, "
        " is_seeded_defect, seeded_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ev.episode_id, ev.air_date, ev.cue_title, ev.composer, ev.publisher, ev.pro,
         ev.usage_type, ev.library, ev.territory, ev.media_type, ev.in_timecode,
         ev.out_timecode, ev.duration_seconds, ev.composer_share_pct,
         ev.publisher_share_pct, ev.intended_license_id,
         1 if ev.is_seeded_defect else 0, ev.seeded_reason),
    )
    return cur.lastrowid


def fetch_all_licenses(conn: sqlite3.Connection) -> List[LicenseRecord]:
    rows = conn.execute("SELECT * FROM license_records").fetchall()
    return [
        LicenseRecord(
            id=r["id"], library=r["library"], usage_type=r["usage_type"],
            term_start=r["term_start"], term_end=r["term_end"],
            territory=r["territory"], media_type=r["media_type"], pro=r["pro"],
        )
        for r in rows
    ]


def fetch_all_episodes(conn: sqlite3.Connection) -> List[Episode]:
    rows = conn.execute("SELECT * FROM episodes ORDER BY id").fetchall()
    return [
        Episode(id=r["id"], program=r["program"], episode_number=r["episode_number"],
                episode_title=r["episode_title"], air_date=r["air_date"])
        for r in rows
    ]


def fetch_episode(conn: sqlite3.Connection, episode_id: int) -> Optional[Episode]:
    r = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
    if r is None:
        return None
    return Episode(id=r["id"], program=r["program"], episode_number=r["episode_number"],
                    episode_title=r["episode_title"], air_date=r["air_date"])


def fetch_events_for_episode(conn: sqlite3.Connection, episode_id: int) -> List[MusicEvent]:
    rows = conn.execute(
        "SELECT * FROM music_events WHERE episode_id = ? ORDER BY id", (episode_id,)
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def fetch_all_events(conn: sqlite3.Connection) -> List[MusicEvent]:
    rows = conn.execute("SELECT * FROM music_events ORDER BY id").fetchall()
    return [_row_to_event(r) for r in rows]


def _row_to_event(r: sqlite3.Row) -> MusicEvent:
    return MusicEvent(
        id=r["id"], episode_id=r["episode_id"], air_date=r["air_date"],
        cue_title=r["cue_title"],
        composer=r["composer"], publisher=r["publisher"], pro=r["pro"],
        usage_type=r["usage_type"], library=r["library"], territory=r["territory"],
        media_type=r["media_type"], in_timecode=r["in_timecode"],
        out_timecode=r["out_timecode"], duration_seconds=r["duration_seconds"],
        composer_share_pct=r["composer_share_pct"],
        publisher_share_pct=r["publisher_share_pct"],
        intended_license_id=r["intended_license_id"],
        is_seeded_defect=bool(r["is_seeded_defect"]), seeded_reason=r["seeded_reason"],
    )
