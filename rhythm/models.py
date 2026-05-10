from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NoteEvent:
    lane: int
    hit_time: float
    duration: float = 0.0


@dataclass
class TrackAnalysis:
    tempo: float
    notes: list[NoteEvent]


@dataclass(frozen=True)
class SavedSong:
    name: str
    path: str

    @property
    def display_name(self) -> str:
        return Path(self.name).stem or self.name
