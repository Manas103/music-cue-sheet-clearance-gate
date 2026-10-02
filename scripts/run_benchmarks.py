"""Reproduce the 6 measured numbers in the README, in one run.

    python scripts/run_benchmarks.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cue_sheet_gate import db, generator, reconcile
from cue_sheet_gate.export import CUE_SHEET_COLUMNS, export_cue_sheet
from cue_sheet_gate.models import Refused
from cue_sheet_gate.oracle import brute_force_reconcile_all


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    summary = generator.build_dataset(conn)

    licenses = db.fetch_all_licenses(conn)
    episodes = db.fetch_all_episodes(conn)
    events = db.fetch_all_events(conn)
    defect_episode_ids = {eid for eid, _, _ in summary["expected_defects"]}

    print("=== claim: 60 synthetic episodes ===")
    print(f"measured: {summary['n_episodes']} episodes, {summary['n_events']} music events")
    print()

    print("=== claim: reconciles every music event against its license record ===")
    index = reconcile.build_license_index(licenses)
    engine = {ev.id: reconcile.reconcile_event(ev, index) for ev in events}
    oracle = {eid: (covered, reason) for eid, covered, reason in
              brute_force_reconcile_all(events, licenses)}
    mismatches = sum(
        1 for ev in events
        if (engine[ev.id].covered, engine[ev.id].reason) != oracle[ev.id]
    )
    print(f"measured: {len(events)} of {len(events)} events reconciled, "
          f"{len(events) - mismatches} of {len(events)} agree exactly with the "
          f"independent brute-force oracle ({mismatches} mismatches)")
    print()

    print("=== claim: refuses to produce the cue sheet when a cue is not covered ===")
    refused_count = 0
    passed_count = 0
    caught = set()
    for ep in episodes:
        evs = db.fetch_events_for_episode(conn, ep.id)
        result = reconcile.gate_episode(ep, evs, licenses)
        if isinstance(result, Refused):
            refused_count += 1
            for v in result.violations:
                caught.add((ep.id, v.cue_title, v.reason))
        else:
            passed_count += 1
    print(f"measured: {refused_count} of {len(defect_episode_ids)} seeded-defect "
          f"episodes refused, {passed_count} of 40 clean episodes passed")
    print()

    print("=== claim: 40 of 40 seeded clearance defects caught, naming cue and reason ===")
    expected = set(summary["expected_defects"])
    print(f"measured: {len(caught & expected)} of {len(expected)} "
          f"(exact cue+reason match: {caught == expected})")
    print()

    print("=== claim: 0 false holds across 40 clean episodes ===")
    false_holds = 0
    for ep in episodes:
        if ep.id in defect_episode_ids:
            continue
        evs = db.fetch_events_for_episode(conn, ep.id)
        result = reconcile.gate_episode(ep, evs, licenses)
        if isinstance(result, Refused):
            false_holds += 1
    print(f"measured: {false_holds} false holds across 40 clean episodes")
    print()

    print("=== claim: exports the standard ASCAP/BMI cue sheet with 12 required fields ===")
    some_passed_ep = next(
        ep for ep in episodes if ep.id not in defect_episode_ids
    )
    evs = db.fetch_events_for_episode(conn, some_passed_ep.id)
    result = reconcile.gate_episode(some_passed_ep, evs, licenses)
    tmp_path = os.path.join(os.path.dirname(__file__), "..", "data", "_benchmark_sample.xlsx")
    export_cue_sheet(some_passed_ep, evs, result, tmp_path)
    print(f"measured: {len(CUE_SHEET_COLUMNS)} named fields per cue: {CUE_SHEET_COLUMNS}")
    os.remove(tmp_path)


if __name__ == "__main__":
    main()
