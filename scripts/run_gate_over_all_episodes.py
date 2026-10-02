"""Run the gate over all 60 synthetic episodes, print PASSED/REFUSED per
episode naming every violation's cue and reason, and export a cue sheet
(real or marked-refused) for each one into data/cue_sheets/.

    python scripts/run_gate_over_all_episodes.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cue_sheet_gate import db, generator, reconcile
from cue_sheet_gate.export import export_cue_sheet
from cue_sheet_gate.models import Refused

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cue_sheets")


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    summary = generator.build_dataset(conn)

    os.makedirs(OUT_DIR, exist_ok=True)
    licenses = db.fetch_all_licenses(conn)
    episodes = db.fetch_all_episodes(conn)

    n_passed = 0
    n_refused = 0
    n_defects_caught = 0

    for ep in episodes:
        events = db.fetch_events_for_episode(conn, ep.id)
        result = reconcile.gate_episode(ep, events, licenses)
        out_path = os.path.join(OUT_DIR, f"episode_{ep.episode_number:03d}.xlsx")
        export_cue_sheet(ep, events, result, out_path)

        if isinstance(result, Refused):
            n_refused += 1
            n_defects_caught += len(result.violations)
            print(f"episode {ep.episode_number:3d} ({ep.episode_title}): REFUSED")
            for v in result.violations:
                print(f"    cue {v.cue_title!r}: {v.reason}")
        else:
            n_passed += 1
            rel_path = os.path.relpath(out_path, os.path.dirname(__file__))
            print(f"episode {ep.episode_number:3d} ({ep.episode_title}): PASSED, "
                  f"cue sheet written to {rel_path}")

    print()
    print(f"episodes: {len(episodes)} total, {n_passed} passed, {n_refused} refused")
    print(f"seeded defects caught: {n_defects_caught} "
          f"(expected {summary['n_seeded_defects']})")


if __name__ == "__main__":
    main()
