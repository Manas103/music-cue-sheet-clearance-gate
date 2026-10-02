"""Independent brute-force reference oracle.

This is deliberately not a call into reconcile.py. It is a second, separately
written pass that scans every license record for every event with plain
nested loops and no index, re-deriving the same containment and term rules
from scratch. The point (BUILDER.md section 2, the same pattern as
treasury-basis-implied-repo-monitor's CTD oracle and
geodatabase-integrity-delivery-qc's brute-force overlap scan) is that an
indexing bug in reconcile.py's dict lookup would still show up here as a
disagreement, because this code never builds or trusts that index.

Deliberately obviously correct, not fast: O(events x licenses), straight
list scan, no early exit tricks beyond "stop at the first fully covering
record found."
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from cue_sheet_gate.models import (
    LicenseRecord,
    LICENSE_EXPIRED,
    LICENSE_NOT_YET_EFFECTIVE,
    MusicEvent,
    NO_LICENSE_RECORD,
    PRO_MISMATCH,
    WRONG_MEDIA_TYPE,
    WRONG_TERRITORY,
)

# Written out again, independently, rather than imported from reconcile.py.
# If reconcile.py's rank table were ever edited wrong, this copy would not
# move with it, which is exactly the point of a reference oracle.
_TERRITORY_ORDER = ["United States", "United States and Canada", "World"]
_MEDIA_ORDER = ["Broadcast Television", "Broadcast and Streaming", "All Media"]


def _territory_is_covered(license_territory: str, needed_territory: str) -> bool:
    for t in _TERRITORY_ORDER:
        if t == needed_territory:
            return True
        if t == license_territory:
            return False
    raise ValueError(f"unknown territory: {needed_territory!r} / {license_territory!r}")


def _media_is_covered(license_media: str, needed_media: str) -> bool:
    for m in _MEDIA_ORDER:
        if m == needed_media:
            return True
        if m == license_media:
            return False
    raise ValueError(f"unknown media type: {needed_media!r} / {license_media!r}")


def brute_force_reconcile_event(
    event: MusicEvent, all_licenses: List[LicenseRecord]
) -> Tuple[bool, Optional[str]]:
    """Scan every license record in the table, no filtering shortcuts.

    Returns (True, None) on the first fully covering record found, or
    (False, reason) naming the most specific failure seen across every
    record sharing this event's library and usage type (or NO_LICENSE_RECORD
    if not one single record in the whole table matches even that much).
    """
    same_key_seen = False
    furthest_failure = None
    furthest_stage = -1

    for lic in all_licenses:
        if lic.library != event.library:
            continue
        if lic.usage_type != event.usage_type:
            continue
        same_key_seen = True

        if event.air_date < lic.term_start:
            stage, reason = 0, LICENSE_NOT_YET_EFFECTIVE
        elif event.air_date > lic.term_end:
            stage, reason = 0, LICENSE_EXPIRED
        elif not _territory_is_covered(lic.territory, event.territory):
            stage, reason = 1, WRONG_TERRITORY
        elif not _media_is_covered(lic.media_type, event.media_type):
            stage, reason = 2, WRONG_MEDIA_TYPE
        elif lic.pro != event.pro:
            stage, reason = 3, PRO_MISMATCH
        else:
            return True, None

        if stage > furthest_stage:
            furthest_stage = stage
            furthest_failure = reason

    if not same_key_seen:
        return False, NO_LICENSE_RECORD
    return False, furthest_failure


def brute_force_reconcile_all(
    events: List[MusicEvent], all_licenses: List[LicenseRecord]
) -> List[Tuple[int, bool, Optional[str]]]:
    """Reconcile every event against every license, event by event, episode by episode.

    No batching, no grouping by episode or key: a plain loop over the event
    list, each one independently scanning the full license table.
    """
    results = []
    for event in events:
        covered, reason = brute_force_reconcile_event(event, all_licenses)
        results.append((event.id, covered, reason))
    return results
