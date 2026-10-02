"""ASCAP/BMI-style cue sheet export, one row per music cue, 12 named columns.

The 12 fields below follow the information every ASCAP and BMI cue sheet
template asks for (ASCAP's cue sheet template and BMI's "How to Read a Cue
Sheet" guidance both list the same substance: the program, the episode, the
air date, and then per cue the title, the writer(s), the publisher(s), the
PRO, the use, the timing, and the share split). This module names them
exactly as a cue sheet reader would expect, and documents the exact column
order in README.

Only episodes that pass the gate get a real cue sheet. A refused episode
still produces a workbook, so the file exists and is easy to find next to
its clean siblings, but every data row is replaced with the refusal
(episode id, cue, reason), the tab is named "REFUSED", and the header
reads "CUE SHEET REFUSED, NOT FOR DISTRIBUTION" instead of the normal
program/episode header. This is a deliberate choice over silently skipping
the file: a missing file next to 59 real ones looks like a tooling bug, a
file that screams REFUSED at the top does not.
"""

from __future__ import annotations

from typing import List

from openpyxl import Workbook
from openpyxl.styles import Font

from cue_sheet_gate.models import Episode, EpisodeReconciliation, MusicEvent, Refused

# The 12 required fields, in the order they are written. Keep this list and
# the README's description of it in sync; a test asserts the header row
# equals this exactly.
CUE_SHEET_COLUMNS = [
    "Program/Series Title",
    "Episode Title/Number",
    "Air Date",
    "Cue Title",
    "Composer",
    "Publisher",
    "Performing Rights Organization (PRO)",
    "Usage Type",
    "Duration (Timing)",
    "In-Cue Timecode",
    "Out-Cue Timecode",
    "Composer/Publisher Share (%)",
]
assert len(CUE_SHEET_COLUMNS) == 12


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


def _event_row(event: MusicEvent, episode: Episode) -> list:
    return [
        episode.program,
        f"{episode.episode_title} (#{episode.episode_number})",
        episode.air_date,
        event.cue_title,
        event.composer,
        event.publisher,
        event.pro,
        event.usage_type,
        _format_duration(event.duration_seconds),
        event.in_timecode,
        event.out_timecode,
        f"{event.composer_share_pct:.1f}% / {event.publisher_share_pct:.1f}%",
    ]


def export_cue_sheet(
    episode: Episode,
    events: List[MusicEvent],
    gate_result,
    out_path: str,
) -> bool:
    """Write a cue sheet workbook for one episode. Returns True if the
    workbook is a real, distributable cue sheet (gate passed) and False if
    it is a refusal placeholder (gate refused).
    """
    wb = Workbook()
    ws = wb.active

    if isinstance(gate_result, Refused):
        ws.title = "REFUSED"
        ws.append(["CUE SHEET REFUSED, NOT FOR DISTRIBUTION"])
        ws["A1"].font = Font(bold=True, color="CC0000")
        ws.append([])
        ws.append(["Program", episode.program])
        ws.append(["Episode", f"{episode.episode_title} (#{episode.episode_number})"])
        ws.append(["Air date", episode.air_date])
        ws.append([])
        ws.append(["Cue Title", "Reason"])
        for v in gate_result.violations:
            ws.append([v.cue_title, v.reason])
        for col, width in zip("AB", (40, 45)):
            ws.column_dimensions[col].width = width
        wb.save(out_path)
        return False

    assert isinstance(gate_result, EpisodeReconciliation) and gate_result.passed
    ws.title = "Cue Sheet"
    ws.append(CUE_SHEET_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for event in events:
        ws.append(_event_row(event, episode))
    for i, _ in enumerate(CUE_SHEET_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 24
    wb.save(out_path)
    return True
