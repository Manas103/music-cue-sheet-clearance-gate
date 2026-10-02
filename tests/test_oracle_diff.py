"""Diff the indexed reconciliation engine against the independent
brute-force oracle across the full 240-event synthetic dataset.

reconcile.py and oracle.py are two separately written implementations of
the same covering rules (see oracle.py's module docstring for why). This
test is the thing that would catch an indexing bug reconcile.py could have
that a plain nested-loop scan could not: if the two ever disagree, this is
the only place that would notice.
"""

from cue_sheet_gate import db, reconcile
from cue_sheet_gate.oracle import brute_force_reconcile_all


def test_engine_and_oracle_agree_on_every_event(dataset):
    conn, summary = dataset
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

    assert mismatches == []
    assert len(events) == 240
