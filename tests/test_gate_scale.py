"""The two release-blocking claims, measured against the full 60-episode
synthetic dataset: exact set match, not just a count, mirroring
drawing-set-release-check's test_45_of_45_seeded_release_defects_caught.
"""

import pytest

from cue_sheet_gate import db, reconcile
from cue_sheet_gate.models import GateRefusedError, Refused


def test_dataset_shape_is_60_episodes_40_seeded_defects_across_20_episodes(dataset):
    _, summary = dataset
    assert summary["n_episodes"] == 60
    assert summary["n_events"] == 240
    assert summary["n_seeded_defects"] == 40
    assert summary["n_defect_episodes"] == 20
    assert summary["n_clean_episodes"] == 40


def test_40_of_40_seeded_defects_caught_naming_cue_and_reason(dataset):
    conn, summary = dataset
    licenses = db.fetch_all_licenses(conn)
    episodes = db.fetch_all_episodes(conn)

    caught = set()
    for ep in episodes:
        events = db.fetch_events_for_episode(conn, ep.id)
        result = reconcile.gate_episode(ep, events, licenses)
        if isinstance(result, Refused):
            for v in result.violations:
                caught.add((ep.id, v.cue_title, v.reason))

    expected = set(summary["expected_defects"])
    assert len(expected) == 40
    # Exact set match: not just that 40 were caught, but that they are
    # exactly the 40 the generator seeded, naming the same cue and reason.
    assert caught == expected


def test_0_false_holds_across_40_clean_episodes(dataset):
    conn, summary = dataset
    licenses = db.fetch_all_licenses(conn)
    episodes = db.fetch_all_episodes(conn)
    defect_episode_ids = {eid for eid, _, _ in summary["expected_defects"]}

    false_holds = []
    passed_count = 0
    for ep in episodes:
        if ep.id in defect_episode_ids:
            continue
        events = db.fetch_events_for_episode(conn, ep.id)
        result = reconcile.gate_episode(ep, events, licenses)
        if isinstance(result, Refused):
            false_holds.append((ep.id, result.violations))
        else:
            passed_count += 1

    assert false_holds == []
    assert passed_count == 40


def test_refused_episode_raises_via_strict_entry_point(dataset):
    conn, summary = dataset
    licenses = db.fetch_all_licenses(conn)
    defect_episode_id = summary["expected_defects"][0][0]
    episode = db.fetch_episode(conn, defect_episode_id)
    events = db.fetch_events_for_episode(conn, defect_episode_id)

    with pytest.raises(GateRefusedError) as excinfo:
        reconcile.gate_episode_or_raise(episode, events, licenses)
    assert excinfo.value.refused.episode_id == defect_episode_id
    assert len(excinfo.value.refused.violations) >= 1


def test_passed_episode_does_not_raise_via_strict_entry_point(dataset):
    conn, summary = dataset
    licenses = db.fetch_all_licenses(conn)
    defect_episode_ids = {eid for eid, _, _ in summary["expected_defects"]}
    episodes = db.fetch_all_episodes(conn)
    clean_episode = next(ep for ep in episodes if ep.id not in defect_episode_ids)
    events = db.fetch_events_for_episode(conn, clean_episode.id)

    result = reconcile.gate_episode_or_raise(clean_episode, events, licenses)
    assert result.passed
