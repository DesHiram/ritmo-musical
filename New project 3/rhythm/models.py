from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    lane: int
    hit_time: float


@dataclass
class TrackAnalysis:
    tempo: float
    notes: list[NoteEvent]


@dataclass(frozen=True)
class SavedSong:
    name: str
    path: str
