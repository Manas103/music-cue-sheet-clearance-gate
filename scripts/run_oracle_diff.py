"""Diff the indexed reconciliation engine against the independent
brute-force oracle across every event in the 60-episode synthetic
dataset, and print an exact-agreement summary.

    python scripts/run_oracle_diff.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cue_sheet_gate import db, generator, reconcile
from cue_sheet_gate.oracle import brute_force_reconcile_all


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    generator.build_dataset(conn)

    licenses = db.fetch_all_licenses(conn)
    events = db.fetch_all_events(conn)

    index = reconcile.build_license_index(licenses)
    engine = {ev.id: reconcile.reconcile_event(ev, index) for ev in events}
    oracle = {eid: (covered, reason) for eid, covered, reason in
              brute_force_reconcile_all(events, licenses)}

    mismatches = []
    for ev in events:
        v = engine[ev.id]
        o_covered, o_reason = oracle[ev.id]
        if v.covered != o_covered or v.reason != o_reason:
            mismatches.append((ev.id, ev.cue_title, (v.covered, v.reason), (o_covered, o_reason)))

    print(f"events compared: {len(events)}")
    print(f"mismatches: {len(mismatches)}")
    for m in mismatches:
        print(f"  event {m[0]} ({m[1]!r}): engine={m[2]} oracle={m[3]}")

    if not mismatches:
        print("exact agreement: indexed engine and brute-force oracle "
              f"agree on all {len(events)} events")


if __name__ == "__main__":
    main()
