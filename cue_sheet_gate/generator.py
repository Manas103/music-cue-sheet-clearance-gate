"""Synthetic dataset builder: 60 episodes, 20 of them carrying exactly 2
seeded clearance defects each (40 total), the remaining 40 clean.

Every fact this module states about a defect (which cue, which reason) is
verified against the independent oracle (oracle.py) at construction time,
not just asserted: build_dataset() raises if a "clean" construction does
not actually come back covered, or a "defect" construction does not come
back refused for exactly the intended reason. This means the measured
40/40 and 0/40 numbers cannot be an artifact of the generator and the gate
agreeing by construction without the gate doing real work; the oracle is
the one piece of code in this repo that never imports reconcile.py, so it
cannot have inherited a shared bug.

All names, dates and figures below are synthetic. "Harborline" is not a
real television program; every composer, publisher and library name is
invented for this dataset.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, timedelta
from typing import List, Tuple

from cue_sheet_gate import db
from cue_sheet_gate.models import (
    ALL_REASON_CODES,
    LICENSE_EXPIRED,
    LICENSE_NOT_YET_EFFECTIVE,
    LicenseRecord,
    Episode,
    MusicEvent,
    NO_LICENSE_RECORD,
    PRO_MISMATCH,
    WRONG_MEDIA_TYPE,
    WRONG_TERRITORY,
)
from cue_sheet_gate.oracle import brute_force_reconcile_event

PROGRAM = "Harborline"

LIBRARIES = [
    "APM Music",
    "Associated Production Music",
    "Extreme Music",
    "Universal Production Music",
    "Sony Orchestral",
    "Warner Chappell Production",
]
USAGE_TYPES = ["Theme", "Background", "Visual Vocal", "Source"]

TERRITORY_ORDER = ["United States", "United States and Canada", "World"]
MEDIA_ORDER = ["Broadcast Television", "Broadcast and Streaming", "All Media"]
PROS = ["ASCAP", "BMI"]

# (composer, publisher, pro) - fixed vocabulary, half ASCAP half BMI, so a
# PRO_MISMATCH defect means "this event claims the wrong PRO for its
# composer" rather than an arbitrary relabeling.
COMPOSERS = [
    ("Renata Oyelaran", "Oyelaran Music Publishing", "ASCAP"),
    ("Marcus Voss", "Voss Brothers Publishing", "ASCAP"),
    ("Ines Caballero", "Caballero Scoring Co.", "ASCAP"),
    ("Theo Kirchner", "Kirchner Cue Works", "ASCAP"),
    ("Priya Nandakumar", "Nandakumar Music Group", "ASCAP"),
    ("Dalton Reyes", "Reyes Sync Publishing", "BMI"),
    ("Hana Ferreira", "Ferreira Production Music", "BMI"),
    ("Lukas Brennan", "Brennan Scoring House", "BMI"),
    ("Odessa Nwankwo", "Nwankwo Music Works", "BMI"),
    ("Samuel Trask", "Trask Cue House", "BMI"),
]
COMPOSERS_BY_PRO = {
    "ASCAP": [c for c in COMPOSERS if c[2] == "ASCAP"],
    "BMI": [c for c in COMPOSERS if c[2] == "BMI"],
}

CUE_BASE_NAMES = [
    "Midnight Skyline", "Quiet Harbor", "Chrome and Rain", "Low Tide Drive",
    "Second Shift", "Glass Pier", "Static Horizon", "Night Freight",
    "Copper Light", "Undertow", "Dead Reckoning", "Harbor Signal",
    "Slow Burn Approach", "Fog Line", "Last Call Theme", "Switchyard",
]

RESERVED_NO_LICENSE_LIBRARY = "Library Not Under Contract"
RESERVED_NO_LICENSE_USAGE = "Background"

DATASET_SEED = 20260801  # fixed, so the dataset is exactly reproducible


class GeneratorInvariantError(RuntimeError):
    """Raised if a constructed event does not verify against the oracle.

    Should never fire in a clean run; it exists so a future change to the
    containment tables or construction logic fails loudly at build time
    instead of silently shipping a defect the gate cannot actually catch,
    or a "clean" episode that the gate would in fact refuse.
    """


def _rank(order: List[str], value: str) -> int:
    return order.index(value)


def _format_timecode(total_frames: int) -> str:
    seconds_total, frames = divmod(total_frames, 30)
    minutes_total, seconds = divmod(seconds_total, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def _timecode_to_frames(tc: str) -> int:
    h, m, s, f = (int(x) for x in tc.split(":"))
    return ((h * 60 + m) * 60 + s) * 30 + f


def _build_base_licenses(rng: random.Random) -> Tuple[List[LicenseRecord], List[Tuple[str, str]]]:
    """24 base (library, usage_type) combos, 1 license each, plus a second,
    non-overlapping-term renewal record added to 3 of those combos (so the
    gate's candidate list is sometimes length 2, exercising the multi-
    candidate ranking path in reconcile.find_covering_license).

    Returns (licenses_without_ids, single_record_keys); single_record_keys
    lists the 21 combos left with exactly one license, which is the pool
    defect construction draws from, so a defect's "pick a date outside the
    term" can never accidentally land inside a second license's term for
    the same key.
    """
    licenses: List[LicenseRecord] = []
    base_keys = [(lib, usage) for lib in LIBRARIES for usage in USAGE_TYPES]
    assert len(base_keys) == 24

    for lib, usage in base_keys:
        start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 180))
        end = start + timedelta(days=rng.randint(540, 900))
        licenses.append(LicenseRecord(
            id=None, library=lib, usage_type=usage,
            term_start=start.isoformat(), term_end=end.isoformat(),
            territory=rng.choice(TERRITORY_ORDER), media_type=rng.choice(MEDIA_ORDER),
            pro=rng.choice(PROS),
        ))

    renewal_keys = rng.sample(base_keys, 3)
    for lib, usage in renewal_keys:
        original = next(l for l in licenses if l.library == lib and l.usage_type == usage)
        renewal_start = date.fromisoformat(original.term_end) + timedelta(days=1)
        renewal_end = renewal_start + timedelta(days=rng.randint(540, 900))
        licenses.append(LicenseRecord(
            id=None, library=lib, usage_type=usage,
            term_start=renewal_start.isoformat(), term_end=renewal_end.isoformat(),
            territory=rng.choice(TERRITORY_ORDER), media_type=rng.choice(MEDIA_ORDER),
            pro=rng.choice(PROS),
        ))

    single_record_keys = [k for k in base_keys if k not in renewal_keys]
    return licenses, single_record_keys


def _new_cue_title(rng: random.Random, cue_seq: int) -> str:
    return f"{rng.choice(CUE_BASE_NAMES)} (cue {cue_seq:04d})"


def _shares(rng: random.Random) -> Tuple[float, float]:
    composer_share = round(rng.uniform(40.0, 65.0), 1)
    publisher_share = round(100.0 - composer_share, 1)
    return composer_share, publisher_share


def _timecodes(rng: random.Random, duration: float) -> Tuple[str, str]:
    in_tc = _format_timecode(rng.randint(0, 2700))
    out_tc = _format_timecode(_timecode_to_frames(in_tc) + int(round(duration * 30)))
    return in_tc, out_tc


def _make_clean_event_for_date(
    rng: random.Random, episode_id: int, cue_seq: int, air_date: date,
    licenses_covering_date: List[LicenseRecord],
) -> MusicEvent:
    """Build an event guaranteed covered: pick any license whose term
    already covers air_date, then pick territory/media at or below its
    rank and a PRO equal to its PRO, so the oracle's coverage check can
    only succeed.
    """
    lic = rng.choice(licenses_covering_date)
    composer, publisher, _ = rng.choice(COMPOSERS_BY_PRO[lic.pro])
    territory = TERRITORY_ORDER[rng.randint(0, _rank(TERRITORY_ORDER, lic.territory))]
    media = MEDIA_ORDER[rng.randint(0, _rank(MEDIA_ORDER, lic.media_type))]
    duration = round(rng.uniform(8.0, 45.0), 1)
    composer_share, publisher_share = _shares(rng)
    in_tc, out_tc = _timecodes(rng, duration)

    return MusicEvent(
        id=None, episode_id=episode_id, air_date=air_date.isoformat(),
        cue_title=_new_cue_title(rng, cue_seq), composer=composer, publisher=publisher,
        pro=lic.pro, usage_type=lic.usage_type, library=lic.library, territory=territory,
        media_type=media, in_timecode=in_tc, out_timecode=out_tc, duration_seconds=duration,
        composer_share_pct=composer_share, publisher_share_pct=publisher_share,
        intended_license_id=lic.id, is_seeded_defect=False, seeded_reason=None,
    )


def _make_defect_event(
    rng: random.Random, episode_id: int, cue_seq: int, reason: str, episode_air_date: date,
    single_record_keys: List[Tuple[str, str]], stored_licenses: List[LicenseRecord],
    forced_license: LicenseRecord = None,
) -> MusicEvent:
    """Build an event deliberately not covered, for exactly one named reason.

    For LICENSE_EXPIRED / LICENSE_NOT_YET_EFFECTIVE, episode_air_date IS the
    bad date, computed by the caller against forced_license specifically
    (the caller must pass the exact same license here; picking a second,
    independent random license for the event would risk a license that
    actually does cover this date, which is exactly the bug this parameter
    exists to prevent). Every other field is otherwise clean. For the other
    four reasons, episode_air_date is a normal date inside some license's
    term, and exactly one non-date field is broken.
    """
    if reason == NO_LICENSE_RECORD:
        pro = rng.choice(PROS)
        composer, publisher, _ = rng.choice(COMPOSERS_BY_PRO[pro])
        duration = round(rng.uniform(8.0, 45.0), 1)
        composer_share, publisher_share = _shares(rng)
        in_tc, out_tc = _timecodes(rng, duration)
        return MusicEvent(
            id=None, episode_id=episode_id, air_date=episode_air_date.isoformat(),
            cue_title=_new_cue_title(rng, cue_seq), composer=composer, publisher=publisher,
            pro=pro, usage_type=RESERVED_NO_LICENSE_USAGE, library=RESERVED_NO_LICENSE_LIBRARY,
            territory=rng.choice(TERRITORY_ORDER), media_type=rng.choice(MEDIA_ORDER),
            in_timecode=in_tc, out_timecode=out_tc, duration_seconds=duration,
            composer_share_pct=composer_share, publisher_share_pct=publisher_share,
            intended_license_id=None, is_seeded_defect=True, seeded_reason=reason,
        )

    if reason in (LICENSE_EXPIRED, LICENSE_NOT_YET_EFFECTIVE):
        if forced_license is None:
            raise GeneratorInvariantError(
                f"{reason!r} defect construction requires forced_license"
            )
        lic = forced_license
        composer, publisher, _ = rng.choice(COMPOSERS_BY_PRO[lic.pro])
        territory = TERRITORY_ORDER[rng.randint(0, _rank(TERRITORY_ORDER, lic.territory))]
        media = MEDIA_ORDER[rng.randint(0, _rank(MEDIA_ORDER, lic.media_type))]
        duration = round(rng.uniform(8.0, 45.0), 1)
        composer_share, publisher_share = _shares(rng)
        in_tc, out_tc = _timecodes(rng, duration)
        return MusicEvent(
            id=None, episode_id=episode_id, air_date=episode_air_date.isoformat(),
            cue_title=_new_cue_title(rng, cue_seq), composer=composer, publisher=publisher,
            pro=lic.pro, usage_type=lic.usage_type, library=lic.library, territory=territory,
            media_type=media, in_timecode=in_tc, out_timecode=out_tc, duration_seconds=duration,
            composer_share_pct=composer_share, publisher_share_pct=publisher_share,
            intended_license_id=lic.id, is_seeded_defect=True, seeded_reason=reason,
        )

    # WRONG_TERRITORY, WRONG_MEDIA_TYPE, PRO_MISMATCH: episode_air_date is a
    # normal in-term date; find licenses that already cover this date, then
    # break exactly one other dimension. Not restricted to single-record
    # keys: even a key with a renewal has non-overlapping terms by
    # construction, so at most one of its two records can cover any given
    # date, which means there is still exactly one candidate per key here,
    # the same as the single-record case.
    candidates = [
        l for l in stored_licenses
        if l.term_start <= episode_air_date.isoformat() <= l.term_end
    ]
    rng.shuffle(candidates)
    for lic in candidates:
        if reason == WRONG_TERRITORY:
            lic_rank = _rank(TERRITORY_ORDER, lic.territory)
            if lic_rank >= len(TERRITORY_ORDER) - 1:
                continue
            territory = TERRITORY_ORDER[lic_rank + 1]
            media = MEDIA_ORDER[rng.randint(0, _rank(MEDIA_ORDER, lic.media_type))]
            pro = lic.pro
        elif reason == WRONG_MEDIA_TYPE:
            media_rank = _rank(MEDIA_ORDER, lic.media_type)
            if media_rank >= len(MEDIA_ORDER) - 1:
                continue
            media = MEDIA_ORDER[media_rank + 1]
            territory = TERRITORY_ORDER[rng.randint(0, _rank(TERRITORY_ORDER, lic.territory))]
            pro = lic.pro
        elif reason == PRO_MISMATCH:
            territory = TERRITORY_ORDER[rng.randint(0, _rank(TERRITORY_ORDER, lic.territory))]
            media = MEDIA_ORDER[rng.randint(0, _rank(MEDIA_ORDER, lic.media_type))]
            pro = "BMI" if lic.pro == "ASCAP" else "ASCAP"
        else:
            raise ValueError(f"unknown reason code: {reason!r}")

        composer, publisher, _ = rng.choice(COMPOSERS_BY_PRO[pro])
        duration = round(rng.uniform(8.0, 45.0), 1)
        composer_share, publisher_share = _shares(rng)
        in_tc, out_tc = _timecodes(rng, duration)
        return MusicEvent(
            id=None, episode_id=episode_id, air_date=episode_air_date.isoformat(),
            cue_title=_new_cue_title(rng, cue_seq), composer=composer, publisher=publisher,
            pro=pro, usage_type=lic.usage_type, library=lic.library, territory=territory,
            media_type=media, in_timecode=in_tc, out_timecode=out_tc, duration_seconds=duration,
            composer_share_pct=composer_share, publisher_share_pct=publisher_share,
            intended_license_id=lic.id, is_seeded_defect=True, seeded_reason=reason,
        )

    raise GeneratorInvariantError(
        f"no single-record-key license admitted a {reason!r} defect on {episode_air_date}"
    )


def build_dataset(conn) -> dict:
    """Build the full 60-episode synthetic dataset into conn (already init_db'd).

    Returns a summary dict: counts and the exact list of
    (episode_id, cue_title, reason) expected for every seeded defect, so
    tests can assert the gate's findings match this list exactly, not just
    its length.
    """
    rng = random.Random(DATASET_SEED)
    licenses, single_record_keys = _build_base_licenses(rng)
    for lic in licenses:
        db.insert_license(conn, lic)
    stored_licenses = db.fetch_all_licenses(conn)

    reason_cycle = list(ALL_REASON_CODES)
    expected_defects = []  # (episode_id, cue_title, reason)
    cue_seq = 0
    defect_slot = 0

    episode_numbers = list(range(1, 61))
    rng.shuffle(episode_numbers)
    defect_episode_numbers = set(episode_numbers[:20])

    for ep_num in range(1, 61):
        is_defect_episode = ep_num in defect_episode_numbers
        reasons_here = []
        if is_defect_episode:
            reasons_here = [
                reason_cycle[(defect_slot + i) % len(reason_cycle)] for i in range(2)
            ]
            defect_slot += 2

        date_boundary_reasons = [
            r for r in reasons_here if r in (LICENSE_EXPIRED, LICENSE_NOT_YET_EFFECTIVE)
        ]
        # The cycle is paired two-at-a-time starting at an even offset
        # (NO_LICENSE_RECORD, LICENSE_EXPIRED), (LICENSE_NOT_YET_EFFECTIVE,
        # WRONG_TERRITORY), (WRONG_MEDIA_TYPE, PRO_MISMATCH), repeating; a
        # single episode's two slots never straddle a pair boundary, so at
        # most one date-boundary reason ever lands in the same episode.
        if len(date_boundary_reasons) > 1:
            raise GeneratorInvariantError(
                f"episode {ep_num} was assigned two date-boundary reasons "
                f"({date_boundary_reasons}); the gate cannot have two "
                "different air dates for one episode"
            )

        forced_license = None
        if date_boundary_reasons:
            reason = date_boundary_reasons[0]
            # The 2 clean events in this same episode still need a license
            # that covers whatever air_date gets picked, even though the
            # defect license deliberately does not. Retry the (library,
            # usage_type) pick, not the air_date math, until some other
            # license in the table covers the resulting date.
            licenses_covering_date = []
            for _ in range(25):
                lib, usage = rng.choice(single_record_keys)
                candidate_license = next(
                    l for l in stored_licenses if l.library == lib and l.usage_type == usage
                )
                if reason == LICENSE_EXPIRED:
                    candidate_date = date.fromisoformat(candidate_license.term_end) + timedelta(
                        days=rng.randint(10, 60)
                    )
                else:
                    candidate_date = date.fromisoformat(
                        candidate_license.term_start
                    ) - timedelta(days=rng.randint(10, 60))
                covering = [
                    l for l in stored_licenses
                    if l.term_start <= candidate_date.isoformat() <= l.term_end
                ]
                if covering:
                    forced_license, air_date, licenses_covering_date = (
                        candidate_license, candidate_date, covering,
                    )
                    break
            if forced_license is None:
                raise GeneratorInvariantError(
                    f"episode {ep_num}: could not find a {reason!r} date that "
                    "still leaves some license covering it for the episode's "
                    "clean events"
                )
        else:
            air_date = date(2024, 1, 1) + timedelta(days=rng.randint(0, 850))
            licenses_covering_date = [
                l for l in stored_licenses if l.term_start <= air_date.isoformat() <= l.term_end
            ]
            if not licenses_covering_date:
                # Extremely unlikely with these term lengths, but handled:
                # shift to a date guaranteed to be covered by some license.
                licenses_covering_date = [rng.choice(stored_licenses)]
                air_date = date.fromisoformat(
                    licenses_covering_date[0].term_start
                ) + timedelta(days=rng.randint(0, 30))

        episode = Episode(
            id=None, program=PROGRAM, episode_number=ep_num,
            episode_title=f"Episode {ep_num}", air_date=air_date.isoformat(),
        )
        episode_id = db.insert_episode(conn, episode)

        n_defects_here = len(reasons_here)
        n_clean_here = 4 - n_defects_here

        for _ in range(n_clean_here):
            cue_seq += 1
            event = _make_clean_event_for_date(
                rng, episode_id, cue_seq, air_date, licenses_covering_date
            )
            covered, reason_seen = brute_force_reconcile_event(
                replace(event, id=-1), stored_licenses
            )
            if not covered:
                raise GeneratorInvariantError(
                    f"clean construction for cue {event.cue_title!r} in episode "
                    f"{ep_num} did not verify as covered (oracle said {reason_seen!r})"
                )
            db.insert_music_event(conn, event)

        for reason in reasons_here:
            cue_seq += 1
            if reason in (LICENSE_EXPIRED, LICENSE_NOT_YET_EFFECTIVE):
                this_forced_license = forced_license
            else:
                this_forced_license = None
            event = _make_defect_event(
                rng, episode_id, cue_seq, reason, air_date, single_record_keys,
                stored_licenses, forced_license=this_forced_license,
            )
            covered, reason_seen = brute_force_reconcile_event(
                replace(event, id=-1), stored_licenses
            )
            if covered or reason_seen != reason:
                raise GeneratorInvariantError(
                    f"defect construction for cue {event.cue_title!r} in episode "
                    f"{ep_num} did not verify as refused for {reason!r} "
                    f"(oracle said covered={covered}, reason={reason_seen!r})"
                )
            db.insert_music_event(conn, event)
            expected_defects.append((episode_id, event.cue_title, reason))

    episodes = db.fetch_all_episodes(conn)
    events = db.fetch_all_events(conn)
    return {
        "n_episodes": len(episodes),
        "n_events": len(events),
        "n_seeded_defects": sum(1 for e in events if e.is_seeded_defect),
        "n_defect_episodes": len({e.episode_id for e in events if e.is_seeded_defect}),
        "n_clean_episodes": len(episodes) - len(defect_episode_numbers),
        "expected_defects": expected_defects,
    }
