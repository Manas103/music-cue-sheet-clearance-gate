"""Plain dataclasses shared by the generator, the gate, the oracle and export.

Nothing here does reconciliation logic; this module only holds data shapes
so that reconcile.py and oracle.py can be read side by side without wading
through field definitions twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Fixed reason-code vocabulary. Every refusal names one of these, never a
# free-text explanation, so tests can assert on exact strings.
NO_LICENSE_RECORD = "no license record found"
LICENSE_EXPIRED = "license expired before air date"
LICENSE_NOT_YET_EFFECTIVE = "license not yet effective on air date"
WRONG_TERRITORY = "wrong territory"
WRONG_MEDIA_TYPE = "wrong media type"
PRO_MISMATCH = "performing-rights organization mismatch"

ALL_REASON_CODES = (
    NO_LICENSE_RECORD,
    LICENSE_EXPIRED,
    LICENSE_NOT_YET_EFFECTIVE,
    WRONG_TERRITORY,
    WRONG_MEDIA_TYPE,
    PRO_MISMATCH,
)


@dataclass(frozen=True)
class LicenseRecord:
    id: Optional[int]
    library: str
    usage_type: str
    term_start: str  # ISO date "YYYY-MM-DD"
    term_end: str  # ISO date "YYYY-MM-DD"
    territory: str
    media_type: str
    pro: str


@dataclass(frozen=True)
class Episode:
    id: Optional[int]
    program: str
    episode_number: int
    episode_title: str
    air_date: str  # ISO date "YYYY-MM-DD"


@dataclass(frozen=True)
class MusicEvent:
    id: Optional[int]
    episode_id: int
    air_date: str  # ISO date "YYYY-MM-DD"; denormalized from the episode so
                   # every cue sheet row and every gate check carries its own
                   # air date, matching a real ASCAP/BMI cue sheet row.
    cue_title: str
    composer: str
    publisher: str
    pro: str
    usage_type: str
    library: str
    territory: str
    media_type: str
    in_timecode: str  # "HH:MM:SS:FF"
    out_timecode: str
    duration_seconds: float
    composer_share_pct: float
    publisher_share_pct: float
    # Informational only: the license the generator intended this event to
    # match (or None, for a deliberately license-less seeded defect). The
    # gate never reads this field; it always searches the full license
    # table independently. It exists so tests and the demo can state what
    # the generator meant to happen, separate from what the gate decides.
    intended_license_id: Optional[int] = None
    is_seeded_defect: bool = False
    seeded_reason: Optional[str] = None


@dataclass(frozen=True)
class EventVerdict:
    event_id: int
    cue_title: str
    covered: bool
    reason: Optional[str]  # None when covered


@dataclass(frozen=True)
class EpisodeReconciliation:
    episode_id: int
    program: str
    episode_title: str
    air_date: str
    event_verdicts: list = field(default_factory=list)  # list[EventVerdict]

    @property
    def passed(self) -> bool:
        return all(v.covered for v in self.event_verdicts)

    @property
    def violations(self) -> list:
        return [v for v in self.event_verdicts if not v.covered]


@dataclass(frozen=True)
class Refused:
    """Explicit refusal result. Returned, never silently swallowed.

    Carries the exact cue title and reason for every violation so a caller
    (or a human reading a log) can see what blocked the episode without
    re-running the gate.
    """

    episode_id: int
    program: str
    episode_title: str
    air_date: str
    violations: list  # list[EventVerdict], all with covered=False


class GateRefusedError(Exception):
    """Raised by the strict (CLI-facing) entry point instead of returning Refused.

    Carries the same Refused object so a caller that wants the non-zero-exit
    behavior can catch this, and a caller that wants the result-object
    behavior can call the non-raising function instead. Both paths share one
    underlying reconciliation; neither re-derives the verdict.
    """

    def __init__(self, refused: Refused):
        self.refused = refused
        cues = ", ".join(f"{v.cue_title} ({v.reason})" for v in refused.violations)
        super().__init__(
            f"episode {refused.episode_id} ({refused.program} "
            f"{refused.episode_title}) refused: {cues}"
        )
