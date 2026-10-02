"""The gate: indexed reconciliation of music events against license records.

For every event, this looks up candidate license records by the categorical
key (library, usage_type) in a prebuilt dict, then checks the four remaining
dimensions (term covering the air date, territory containment, media-type
containment, PRO match) only against that small candidate set. This is the
"presumably optimized" engine BUILDER.md asks be diffed against an
independently written brute-force oracle (oracle.py); see docs/oracle_diff_summary.txt
for the diff run and README Validation for why the two are expected to
always agree.

Territory and media type are containment relations, not equality: a
"World" license covers a "United States" air, but not the reverse. See
_territory_covers / _media_covers.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from cue_sheet_gate.models import (
    Episode,
    EpisodeReconciliation,
    EventVerdict,
    LicenseRecord,
    LICENSE_EXPIRED,
    LICENSE_NOT_YET_EFFECTIVE,
    MusicEvent,
    NO_LICENSE_RECORD,
    PRO_MISMATCH,
    Refused,
    GateRefusedError,
    WRONG_MEDIA_TYPE,
    WRONG_TERRITORY,
)

# Containment order, broadest first. A license whose territory/media appears
# at or before the requested value's position covers that request.
_TERRITORY_RANK = {
    "United States": 0,
    "United States and Canada": 1,
    "World": 2,
}
_MEDIA_RANK = {
    "Broadcast Television": 0,
    "Broadcast and Streaming": 1,
    "All Media": 2,
}


def _territory_covers(license_territory: str, event_territory: str) -> bool:
    return _TERRITORY_RANK[license_territory] >= _TERRITORY_RANK[event_territory]


def _media_covers(license_media: str, event_media: str) -> bool:
    return _MEDIA_RANK[license_media] >= _MEDIA_RANK[event_media]


def build_license_index(
    licenses: List[LicenseRecord],
) -> Dict[Tuple[str, str], List[LicenseRecord]]:
    """Index by (library, usage_type). Multiple records may share a key."""
    index: Dict[Tuple[str, str], List[LicenseRecord]] = {}
    for lic in licenses:
        index.setdefault((lic.library, lic.usage_type), []).append(lic)
    return index


def find_covering_license(
    event: MusicEvent, index: Dict[Tuple[str, str], List[LicenseRecord]]
) -> Tuple[Optional[LicenseRecord], Optional[str]]:
    """Return (covering_license, None) if covered, else (None, reason).

    When no candidate covers the event, the reason reported is the first
    failing dimension, checked in a fixed order (term, territory, media,
    PRO) against the best candidate (the one that fails latest in that
    order), so a near-miss is reported more specifically than "no license
    record found" whenever a same-key candidate exists at all.
    """
    candidates = index.get((event.library, event.usage_type), [])
    if not candidates:
        return None, NO_LICENSE_RECORD

    best_reason = None
    best_rank = -1
    for lic in candidates:
        reason, rank = _evaluate(lic, event)
        if reason is None:
            return lic, None
        if rank > best_rank:
            best_rank = rank
            best_reason = reason
    return None, best_reason


def _evaluate(lic: LicenseRecord, event: MusicEvent) -> Tuple[Optional[str], int]:
    """Check one candidate in a fixed dimension order. Rank = how far it got."""
    if event.air_date < lic.term_start:
        return LICENSE_NOT_YET_EFFECTIVE, 0
    if event.air_date > lic.term_end:
        return LICENSE_EXPIRED, 0
    if not _territory_covers(lic.territory, event.territory):
        return WRONG_TERRITORY, 1
    if not _media_covers(lic.media_type, event.media_type):
        return WRONG_MEDIA_TYPE, 2
    if lic.pro != event.pro:
        return PRO_MISMATCH, 3
    return None, 4


def reconcile_event(
    event: MusicEvent, index: Dict[Tuple[str, str], List[LicenseRecord]]
) -> EventVerdict:
    lic, reason = find_covering_license(event, index)
    return EventVerdict(
        event_id=event.id, cue_title=event.cue_title, covered=lic is not None,
        reason=reason,
    )


def reconcile_episode(
    episode: Episode,
    events: List[MusicEvent],
    index: Dict[Tuple[str, str], List[LicenseRecord]],
) -> EpisodeReconciliation:
    verdicts = [reconcile_event(ev, index) for ev in events]
    return EpisodeReconciliation(
        episode_id=episode.id, program=episode.program,
        episode_title=episode.episode_title, air_date=episode.air_date,
        event_verdicts=verdicts,
    )


def gate_episode(
    episode: Episode, events: List[MusicEvent], licenses: List[LicenseRecord]
):
    """Return an EpisodeReconciliation (passed) or a Refused result object.

    This is the non-raising entry point: a caller inspects the return type
    (or .passed) rather than catching an exception. gate_episode_or_raise
    below wraps this for a CLI that wants a non-zero exit code instead.
    """
    index = build_license_index(licenses)
    recon = reconcile_episode(episode, events, index)
    if recon.passed:
        return recon
    return Refused(
        episode_id=recon.episode_id, program=recon.program,
        episode_title=recon.episode_title, air_date=recon.air_date,
        violations=recon.violations,
    )


def gate_episode_or_raise(
    episode: Episode, events: List[MusicEvent], licenses: List[LicenseRecord]
) -> EpisodeReconciliation:
    """Strict entry point for CLI use: raises GateRefusedError on refusal.

    A caller that lets this propagate gets a non-zero process exit; this is
    the "refuses to produce" path when a hard stop is wanted instead of a
    result object to branch on.
    """
    result = gate_episode(episode, events, licenses)
    if isinstance(result, Refused):
        raise GateRefusedError(result)
    return result
