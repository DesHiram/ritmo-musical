from __future__ import annotations

import json
from pathlib import Path

from .constants import VISIBLE_LIBRARY_ROWS
from .models import SavedSong


class SongLibrary:
    def __init__(self, library_file: Path) -> None:
        self.library_file = library_file
        self.warning = ""
        self.saved_songs = self._load_saved_songs()
        self.song_scroll = 0
        self.selected_song_index: int | None = None

    def remember_song(self, file_path: Path) -> str | None:
        normalized_key = self.normalize_song_key(file_path)
        updated_song = SavedSong(name=file_path.name, path=str(file_path))
        existing_index = None

        for index, song in enumerate(self.saved_songs):
            if self.normalize_song_key(song.path) == normalized_key:
                existing_index = index
                break

        if existing_index is None:
            self.saved_songs.insert(0, updated_song)
            self.selected_song_index = 0
            self.song_scroll = 0
        else:
            self.saved_songs[existing_index] = updated_song
            self.selected_song_index = existing_index
            self.ensure_song_visible(existing_index)

        return self.persist_saved_songs()

    def select_song(self, index: int) -> SavedSong | None:
        if index < 0 or index >= len(self.saved_songs):
            return None

        self.selected_song_index = index
        self.ensure_song_visible(index)
        return self.saved_songs[index]

    def remove_song(self, index: int) -> tuple[SavedSong | None, str | None]:
        if index < 0 or index >= len(self.saved_songs):
            return None, None

        removed_song = self.saved_songs.pop(index)
        if not self.saved_songs:
            self.selected_song_index = None
            self.song_scroll = 0
        else:
            self.selected_song_index = min(index, len(self.saved_songs) - 1)
            self.song_scroll = min(self.song_scroll, self.max_song_scroll())
            self.ensure_song_visible(self.selected_song_index)

        return removed_song, self.persist_saved_songs()

    def match_selection(self, file_path: Path) -> int | None:
        normalized_key = self.normalize_song_key(file_path)
        self.selected_song_index = None

        for index, song in enumerate(self.saved_songs):
            if self.normalize_song_key(song.path) == normalized_key:
                self.selected_song_index = index
                self.ensure_song_visible(index)
                return index

        return None

    def max_song_scroll(self) -> int:
        return max(0, len(self.saved_songs) - VISIBLE_LIBRARY_ROWS)

    def scroll_song_list(self, delta: int) -> None:
        self.song_scroll = max(0, min(self.song_scroll + delta, self.max_song_scroll()))

    def ensure_song_visible(self, index: int) -> None:
        if index < self.song_scroll:
            self.song_scroll = index
            return

        if index >= self.song_scroll + VISIBLE_LIBRARY_ROWS:
            self.song_scroll = index - VISIBLE_LIBRARY_ROWS + 1

    def visible_song_indices(self) -> range:
        start = self.song_scroll
        end = min(len(self.saved_songs), start + VISIBLE_LIBRARY_ROWS)
        return range(start, end)

    def normalize_song_key(self, file_path: Path | str) -> str:
        candidate = Path(file_path).expanduser()
        try:
            normalized = candidate.resolve()
        except OSError:
            normalized = candidate
        return str(normalized).casefold()

    def _load_saved_songs(self) -> list[SavedSong]:
        if not self.library_file.exists():
            return []

        try:
            payload = json.loads(self.library_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.warning = f"No se pudo leer la biblioteca guardada: {exc}"
            return []

        songs: list[SavedSong] = []
        seen_keys: set[str] = set()

        for item in payload:
            if not isinstance(item, dict):
                continue

            raw_path = item.get("path")
            if not raw_path:
                continue

            song_key = self.normalize_song_key(str(raw_path))
            if song_key in seen_keys:
                continue

            seen_keys.add(song_key)
            song_name = str(item.get("name") or Path(str(raw_path)).name or "Cancion")
            songs.append(SavedSong(name=song_name, path=str(raw_path)))

        return songs

    def persist_saved_songs(self) -> str | None:
        payload = [{"name": song.name, "path": song.path} for song in self.saved_songs]

        try:
            self.library_file.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            return f"No se pudo guardar la biblioteca: {exc}"

        return None
