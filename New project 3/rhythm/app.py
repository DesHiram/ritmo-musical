from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import pygame

from .audio import TrackBuilder
from .constants import FPS, LIBRARY_FILENAME, WINDOW_HEIGHT, WINDOW_WIDTH
from .library import SongLibrary
from .models import TrackAnalysis
from .rendering import RhythmRenderer


class RhythmPrototype:
    def __init__(self) -> None:
        pygame.init()
        pygame.mixer.init()
        pygame.display.set_caption("Python Rhythm Prototype")

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("arial", 30, bold=True)
        self.body_font = pygame.font.SysFont("arial", 22)
        self.small_font = pygame.font.SysFont("arial", 18)

        self.tk_root = tk.Tk()
        self.tk_root.withdraw()
        self.tk_root.attributes("-topmost", True)

        project_root = Path(__file__).resolve().parent.parent
        self.current_screen = "setup"
        self.library = SongLibrary(project_root / LIBRARY_FILENAME)

        self.selected_file: Path | None = None
        self.analysis_source: Path | None = None
        self.analysis: TrackAnalysis | None = None
        self.analysis_cache: dict[str, TrackAnalysis] = {}
        self.status_message = self.library.warning or (
            "Sube una cancion o elige una guardada para generar la pista."
        )
        self.is_playing = False
        self.playback_started_at = 0.0

        self.track_builder = TrackBuilder()
        self.renderer = RhythmRenderer(
            self.screen,
            self.title_font,
            self.body_font,
            self.small_font,
        )

        if self.library.saved_songs:
            self.select_saved_song(0, update_status=False)

    def run(self) -> None:
        running = True
        while running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                elif event.type == pygame.MOUSEWHEEL and self.current_screen == "setup":
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
        if self.current_screen != "visualizer":
            return

        if key == pygame.K_ESCAPE:
            self.return_to_setup()
        elif key == pygame.K_SPACE:
            self.replay_current_track()

    def handle_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.current_screen == "setup":
            self.handle_setup_click(mouse_pos)
            return

        self.handle_visualizer_click(mouse_pos)

    def handle_setup_click(self, mouse_pos: tuple[int, int]) -> None:
        if self.renderer.upload_button.collidepoint(mouse_pos):
            self.select_audio_file()
            return

        if self.renderer.generate_button.collidepoint(mouse_pos):
            self.generate_track()
            return

        if self.renderer.view_button.collidepoint(mouse_pos):
            self.open_visualizer()
            return

        if self.renderer.scroll_up_button.collidepoint(mouse_pos):
            self.library.scroll_song_list(-1)
            return

        if self.renderer.scroll_down_button.collidepoint(mouse_pos):
            self.library.scroll_song_list(1)
            return

        selected_index = self.renderer.song_index_from_position(self.library, mouse_pos)
        if selected_index is not None:
            self.select_saved_song(selected_index)

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

        if save_error:
            self.status_message = f"Archivo listo: {selected_path.name}. {save_error}"
        elif self.is_selected_track_ready():
            self.status_message = (
                f"Archivo listo: {selected_path.name}. La pista ya estaba generada."
            )
        else:
            self.status_message = f"Archivo listo y guardado: {selected_path.name}"

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
            self.current_screen = "visualizer"

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
        self.current_screen = "visualizer"
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
            self.status_message = f"Reproduciendo: {self.analysis_source.name}"

    def return_to_setup(self) -> None:
        self.stop_playback()
        self.current_screen = "setup"

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
                f"La cancion guardada '{song.name}' ya no se encuentra en disco."
            )
        elif self.is_selected_track_ready():
            self.status_message = (
                f"Seleccionaste {song.name}. La pista ya esta lista para abrir o reproducir."
            )
        else:
            self.status_message = f"Seleccionaste {song.name}. Lista para generar la pista."

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
            self.is_playing = True
            return True
        except Exception as exc:  # pragma: no cover - UI path
            self.is_playing = False
            self.playback_started_at = 0.0
            self.status_message = f"No se pudo reproducir la pista: {exc}"
            return False

    def stop_playback(self) -> None:
        pygame.mixer.music.stop()
        self.is_playing = False
        self.playback_started_at = 0.0

    def update_playback_state(self) -> None:
        if self.is_playing and not pygame.mixer.music.get_busy():
            self.is_playing = False
            self.playback_started_at = 0.0
            if self.analysis:
                self.status_message = (
                    "Reproduccion finalizada. Puedes volver a reproducir la pista cuando quieras."
                )

    def current_song_time(self) -> float:
        if not self.is_playing:
            return 0.0
        return max(0.0, (pygame.time.get_ticks() / 1000.0) - self.playback_started_at)

    def draw(self) -> None:
        self.renderer.draw(self)
