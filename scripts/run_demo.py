"""End-to-end narrative: build the dataset, show one refused episode
(naming its cues and reasons), show one passed episode (cue sheet
exported), then exit non-zero via the strict entry point for the refused
episode specifically, to demonstrate the "refuses to produce" claim is a
real control-flow refusal, not a warning that still produces output.

    python scripts/run_demo.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cue_sheet_gate import db, generator, reconcile
from cue_sheet_gate.export import export_cue_sheet
from cue_sheet_gate.models import GateRefusedError, Refused

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "demo")


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    summary = generator.build_dataset(conn)
    os.makedirs(OUT_DIR, exist_ok=True)

    licenses = db.fetch_all_licenses(conn)
    episodes = db.fetch_all_episodes(conn)
    defect_episode_ids = {eid for eid, _, _ in summary["expected_defects"]}

    refused_ep = next(ep for ep in episodes if ep.id in defect_episode_ids)
    passed_ep = next(ep for ep in episodes if ep.id not in defect_episode_ids)

    print(f"--- episode {refused_ep.episode_number} ({refused_ep.episode_title}), "
          f"air date {refused_ep.air_date} ---")
    events = db.fetch_events_for_episode(conn, refused_ep.id)
    result = reconcile.gate_episode(refused_ep, events, licenses)
    assert isinstance(result, Refused)
    print("gate result: REFUSED")
    for v in result.violations:
        print(f"  cue {v.cue_title!r}: {v.reason}")
    out_path = os.path.join(OUT_DIR, "refused_episode.xlsx")
    export_cue_sheet(refused_ep, events, result, out_path)
    print(f"wrote refusal placeholder workbook: {os.path.relpath(out_path, os.path.dirname(__file__))}")
    print()

    print(f"--- episode {passed_ep.episode_number} ({passed_ep.episode_title}), "
          f"air date {passed_ep.air_date} ---")
    events = db.fetch_events_for_episode(conn, passed_ep.id)
    result = reconcile.gate_episode(passed_ep, events, licenses)
    assert not isinstance(result, Refused)
    print("gate result: PASSED")
    out_path = os.path.join(OUT_DIR, "passed_episode.xlsx")
    export_cue_sheet(passed_ep, events, result, out_path)
    rel_path = os.path.relpath(out_path, os.path.dirname(__file__))
    print(f"wrote real cue sheet: {rel_path} ({len(events)} cues)")
    print()

    print("--- demonstrating the strict entry point on the refused episode ---")
    try:
        reconcile.gate_episode_or_raise(
            refused_ep, db.fetch_events_for_episode(conn, refused_ep.id), licenses
        )
    except GateRefusedError as exc:
        print(f"gate_episode_or_raise raised as expected: {exc}")
        print("a CLI built on this entry point would exit non-zero here")
        sys.exit(2)


if __name__ == "__main__":
    main()
