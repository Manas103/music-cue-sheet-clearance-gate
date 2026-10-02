"""Invariant checks that hold regardless of which specific episode or event
is examined: conservation identities, not "it produced plausible output".
"""

from cue_sheet_gate import db


def test_every_event_share_percentages_sum_to_100(dataset):
    conn, _ = dataset
    events = db.fetch_all_events(conn)
    assert len(events) == 240
    for ev in events:
        total = ev.composer_share_pct + ev.publisher_share_pct
        assert abs(total - 100.0) < 1e-9, (ev.id, ev.cue_title, total)


def test_every_event_out_timecode_is_after_in_timecode(dataset):
    conn, _ = dataset
    events = db.fetch_all_events(conn)

    def frames(tc):
        h, m, s, f = (int(x) for x in tc.split(":"))
        return ((h * 60 + m) * 60 + s) * 30 + f

    for ev in events:
        assert frames(ev.out_timecode) > frames(ev.in_timecode), (ev.id, ev.cue_title)


def test_every_episode_has_exactly_4_music_events(dataset):
    conn, _ = dataset
    episodes = db.fetch_all_episodes(conn)
    for ep in episodes:
        events = db.fetch_events_for_episode(conn, ep.id)
        assert len(events) == 4, ep.id


def test_defect_episodes_have_exactly_2_seeded_defects_and_2_clean_events(dataset):
    conn, summary = dataset
    defect_episode_ids = {eid for eid, _, _ in summary["expected_defects"]}
    for ep_id in defect_episode_ids:
        events = db.fetch_events_for_episode(conn, ep_id)
        seeded = [e for e in events if e.is_seeded_defect]
        clean = [e for e in events if not e.is_seeded_defect]
        assert len(seeded) == 2, ep_id
        assert len(clean) == 2, ep_id


def test_license_term_start_is_never_after_term_end(dataset):
    conn, _ = dataset
    licenses = db.fetch_all_licenses(conn)
    assert len(licenses) > 0
    for lic in licenses:
        assert lic.term_start <= lic.term_end, lic.id
