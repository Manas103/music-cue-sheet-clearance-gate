"""Build the synthetic 60-episode dataset into data/cue_sheet_gate.db.

Regenerate with:

    python scripts/build_database.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cue_sheet_gate import db, generator

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cue_sheet_gate.db")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    summary = generator.build_dataset(conn)
    conn.close()

    print(f"Built {DB_PATH}")
    print(f"episodes: {summary['n_episodes']}")
    print(f"music events: {summary['n_events']}")
    print(f"seeded defects: {summary['n_seeded_defects']} "
          f"across {summary['n_defect_episodes']} episodes")
    print(f"clean episodes: {summary['n_clean_episodes']}")


if __name__ == "__main__":
    main()
