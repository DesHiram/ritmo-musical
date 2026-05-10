from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog

import pygame

from .audio import TrackBuilder
from .constants import APP_TITLE, FPS, LIBRARY_FILENAME, WINDOW_HEIGHT, WINDOW_WIDTH
from .library import SongLibrary
from .models import TrackAnalysis
from .rendering import RhythmRenderer, resource_path


class RhythmPrototype:
    def __init__(self) -> None:
        pygame.init()
        pygame.mixer.init()
        pygame.display.set_caption(APP_TITLE)

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.set_window_icon()
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("arial", 30, bold=True)
        self.body_font = pygame.font.SysFont("arial", 22)
        self.small_font = pygame.font.SysFont("arial", 18)

        self.tk_root = tk.Tk()
        self.tk_root.withdraw()
        self.tk_root.attributes("-topmost", True)

        if getattr(sys, "frozen", False):
            project_root = Path(sys.executable).resolve().parent
        else:
            project_root = Path(__file__).resolve().parent.parent
        self.current_screen = "home"
        self.library = SongLibrary(project_root / LIBRARY_FILENAME)

        self.selected_file: Path | None = None
        self.analysis_source: Path | None = None
        self.analysis: TrackAnalysis | None = None
        self.analysis_cache: dict[str, TrackAnalysis] = {}
        self.status_message = self.library.warning or "Elige una cancion del repertorio para iniciar."
        self.is_playing = False
        self.is_paused = False
        self.playback_started_at = 0.0
        self.pause_started_at = 0.0
        self.paused_seconds = 0.0

        self.track_builder = TrackBuilder()
        self.renderer = RhythmRenderer(
            self.screen,
            self.title_font,
            self.body_font,
            self.small_font,
        )

        if self.library.saved_songs:
            self.select_saved_song(0, update_status=False)

    def set_window_icon(self) -> None:
        icon_path = resource_path("assets", "cpdito", "icono.png")
        if not icon_path.exists():
            return

        try:
            icon = pygame.image.load(str(icon_path))
            pygame.display.set_icon(icon)
        except (pygame.error, OSError):
            return

    def run(self) -> None:
        running = True
        while running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                elif event.type == pygame.MOUSEWHEEL and self.current_screen in {"home", "settings"}:
                    self.library.scroll_song_list(-event.y)
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event.key)

            self.update_playback_state()
            self.draw()
            pygame.display.flip()

        pygame.mixer.music.stop()
        self.tk_root.destroy()
        pygame.quit()

    def handle_keydown(self, key: int) -> None:
        if self.current_screen != "game":
            return

        if key == pygame.K_ESCAPE:
            if self.is_paused:
                self.continue_track()
            else:
                self.pause_track()
        elif key == pygame.K_SPACE:
            if self.is_paused:
                self.continue_track()

    def handle_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.current_screen == "home":
            self.handle_home_click(mouse_pos)
            return

        if self.current_screen == "settings":
            self.handle_settings_click(mouse_pos)
            return

        self.handle_game_click(mouse_pos)

    def handle_home_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.renderer.settings_button.collidepoint(mouse_pos):
            self.current_screen = "settings"
            self.status_message = "Configuracion: sube o elimina canciones del repertorio."
            return

        if self.renderer.scroll_up_button.collidepoint(mouse_pos):
            self.library.scroll_song_list(-1)
            return

        if self.renderer.scroll_down_button.collidepoint(mouse_pos):
            self.library.scroll_song_list(1)
            return

        start_index = self.renderer.start_song_index_from_position(self.library, mouse_pos)
        if start_index is not None:
            self.start_song_from_library(start_index)
            return

        song_index = self.renderer.song_index_from_position(self.library, mouse_pos)
        if song_index is not None:
            self.select_saved_song(song_index)

    def handle_settings_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.renderer.back_button.collidepoint(mouse_pos):
            self.current_screen = "home"
            self.status_message = "Elige una cancion del repertorio para iniciar."
            return

        if self.renderer.upload_button.collidepoint(mouse_pos):
            self.select_audio_file()
            return

        if self.renderer.scroll_up_button.collidepoint(mouse_pos):
            self.library.scroll_song_list(-1)
            return

        if self.renderer.scroll_down_button.collidepoint(mouse_pos):
            self.library.scroll_song_list(1)
            return

        delete_index = self.renderer.delete_song_index_from_position(self.library, mouse_pos)
        if delete_index is not None:
            self.delete_saved_song(delete_index)

    def handle_game_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.is_paused:
            if self.renderer.pause_continue_button.collidepoint(mouse_pos):
                self.continue_track()
                return
            if self.renderer.pause_replay_button.collidepoint(mouse_pos):
                self.replay_current_track()
                return
            if self.renderer.pause_exit_button.collidepoint(mouse_pos):
                self.exit_to_home()
                return

        if self.renderer.pause_button.collidepoint(mouse_pos):
            if self.is_paused:
                self.continue_track()
            else:
                self.pause_track()

    def start_song_from_library(self, index: int) -> None:
        song = self.library.select_song(index)
        if song is None:
            return

        self.selected_file = Path(song.path)
        if not self.selected_file.exists():
            self.status_message = f"La cancion '{song.display_name}' ya no se encuentra en disco."
            return

        self.generate_track()

    def delete_saved_song(self, index: int) -> None:
        removed_song, save_error = self.library.remove_song(index)
        if removed_song is None:
            return

        removed_key = self.normalize_song_key(removed_song.path)
        self.analysis_cache.pop(removed_key, None)
        if self.selected_file and self.normalize_song_key(self.selected_file) == removed_key:
            self.selected_file = None
        if self.analysis_source and self.normalize_song_key(self.analysis_source) == removed_key:
            self.stop_playback()
            self.analysis = None
            self.analysis_source = None

        if save_error:
            self.status_message = save_error
        else:
            self.status_message = f"'{removed_song.display_name}' fue eliminada del repertorio."

    def pause_track(self) -> None:
        if not self.is_playing or self.is_paused:
            return

        pygame.mixer.music.pause()
        self.is_paused = True
        self.pause_started_at = pygame.time.get_ticks() / 1000.0
        self.status_message = "Pausa"

    def continue_track(self) -> None:
        if not self.is_paused:
            return

        now = pygame.time.get_ticks() / 1000.0
        self.paused_seconds += max(0.0, now - self.pause_started_at)
        self.pause_started_at = 0.0
        self.is_paused = False
        pygame.mixer.music.unpause()
        if self.analysis_source:
            self.status_message = f"Reproduciendo: {self.analysis_source.stem}"

    def exit_to_home(self) -> None:
        self.stop_playback()
        self.current_screen = "home"
        self.status_message = "Elige una cancion del repertorio para iniciar."

    def handle_visualizer_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.renderer.replay_button.collidepoint(mouse_pos):
            self.replay_current_track()
            return

        if self.renderer.stop_button.collidepoint(mouse_pos):
            self.stop_playback()
            self.status_message = (
                "Reproduccion detenida. Puedes volver a reproducir la pista cuando quieras."
            )
            return

        if self.renderer.back_button.collidepoint(mouse_pos):
            self.return_to_setup()

    def select_audio_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecciona un archivo de audio",
            filetypes=[
                ("Archivos de audio", "*.mp3 *.wav"),
                ("MP3", "*.mp3"),
                ("WAV", "*.wav"),
            ],
        )
        self.tk_root.update()

        if not file_path:
            self.status_message = "Carga cancelada."
            return

        selected_path = Path(file_path)
        save_error = self.library.remember_song(selected_path)
        self.selected_file = selected_path
        selected_name = selected_path.stem

        if save_error:
            self.status_message = f"Archivo listo: {selected_name}. {save_error}"
        elif self.is_selected_track_ready():
            self.status_message = (
                f"Archivo listo: {selected_name}. Ya puedes iniciarla desde el repertorio."
            )
        else:
            self.status_message = f"Archivo guardado: {selected_name}"

    def generate_track(self) -> None:
        if not self.selected_file:
            self.status_message = "Primero sube un archivo de audio o elige una cancion guardada."
            return

        if not self.selected_file.exists():
            self.status_message = "La cancion seleccionada ya no se encuentra en disco."
            return

        self.stop_playback()
        self.status_message = "Analizando audio y generando pista..."
        self.draw()
        pygame.display.flip()
        pygame.event.pump()

        cache_key = self.normalize_song_key(self.selected_file)
        from_cache = cache_key in self.analysis_cache

        try:
            analysis = self.analysis_cache.get(cache_key)
            if analysis is None:
                analysis = self.track_builder.build_chart(self.selected_file)
                self.analysis_cache[cache_key] = analysis

            if not analysis.notes:
                raise ValueError("No se encontraron beats utiles.")

            self.analysis = analysis
            self.analysis_source = self.selected_file
            self.current_screen = "game"

            if not self.start_playback():
                return

            source_label = "lista" if from_cache else "generada"
            self.status_message = (
                f"Pista {source_label}: {len(self.analysis.notes)} notas | "
                f"{self.analysis.tempo:.1f} BPM"
            )
        except Exception as exc:  # pragma: no cover - UI path
            self.status_message = f"No se pudo generar la pista: {exc}"

    def open_visualizer(self) -> None:
        if not self.is_selected_track_ready():
            self.status_message = "Genera la pista primero para abrir la visualizacion."
            return

        self.stop_playback()
        self.current_screen = "game"
        self.status_message = (
            "Visualizacion lista. Pulsa 'Reproducir otra vez' para escuchar la pista."
        )

    def replay_current_track(self) -> None:
        if not self.analysis or not self.analysis_source:
            self.status_message = "No hay una pista lista para reproducir."
            return

        self.selected_file = self.analysis_source
        self.match_saved_song_selection(self.analysis_source)

        if self.start_playback():
            self.status_message = f"Reproduciendo: {self.analysis_source.stem}"

    def return_to_setup(self) -> None:
        self.stop_playback()
        self.current_screen = "home"

        if self.analysis_source:
            self.selected_file = self.analysis_source
            self.match_saved_song_selection(self.analysis_source)

        self.status_message = (
            "Volviste a la biblioteca. Puedes abrir la pista actual o elegir otra cancion."
        )

    def select_saved_song(self, index: int, update_status: bool = True) -> None:
        song = self.library.select_song(index)
        if song is None:
            return

        self.selected_file = Path(song.path)

        if not update_status:
            return

        if not self.selected_file.exists():
            self.status_message = (
                f"La cancion guardada '{song.display_name}' ya no se encuentra en disco."
            )
        elif self.is_selected_track_ready():
            self.status_message = (
                f"Seleccionaste {song.display_name}. La pista ya esta lista para abrir o reproducir."
            )
        else:
            self.status_message = f"Seleccionaste {song.display_name}. Lista para generar la pista."

    def normalize_song_key(self, file_path: Path | str) -> str:
        return self.library.normalize_song_key(file_path)

    def is_selected_track_ready(self) -> bool:
        if not self.selected_file or not self.analysis or not self.analysis_source:
            return False

        return self.normalize_song_key(self.selected_file) == self.normalize_song_key(
            self.analysis_source
        )

    def match_saved_song_selection(self, file_path: Path) -> None:
        self.library.match_selection(file_path)

    def start_playback(self) -> bool:
        audio_file = self.analysis_source or self.selected_file
        if not audio_file or not self.analysis:
            self.status_message = "No hay una pista lista para reproducir."
            return False

        if not audio_file.exists():
            self.status_message = "El archivo de audio ya no se encuentra en disco."
            return False

        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(str(audio_file))
            pygame.mixer.music.play()
            self.playback_started_at = pygame.time.get_ticks() / 1000.0
            self.pause_started_at = 0.0
            self.paused_seconds = 0.0
            self.is_playing = True
            self.is_paused = False
            return True
        except Exception as exc:  # pragma: no cover - UI path
            self.is_playing = False
            self.playback_started_at = 0.0
            self.status_message = f"No se pudo reproducir la pista: {exc}"
            return False

    def stop_playback(self) -> None:
        pygame.mixer.music.stop()
        self.is_playing = False
        self.is_paused = False
        self.playback_started_at = 0.0
        self.pause_started_at = 0.0
        self.paused_seconds = 0.0

    def update_playback_state(self) -> None:
        if self.is_playing and not self.is_paused and not pygame.mixer.music.get_busy():
            self.is_playing = False
            self.playback_started_at = 0.0
            if self.analysis:
                self.status_message = (
                    "Reproduccion finalizada. Puedes volver a reproducir la pista cuando quieras."
                )

    def current_song_time(self) -> float:
        if not self.is_playing:
            return 0.0
        now = self.pause_started_at if self.is_paused else pygame.time.get_ticks() / 1000.0
        return max(0.0, now - self.playback_started_at - self.paused_seconds)

    def draw(self) -> None:
        self.renderer.draw(self)
