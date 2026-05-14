from __future__ import annotations

import math
import os
from pathlib import Path
import random
import shutil
import sys
from typing import TYPE_CHECKING

import imageio.v2 as imageio
import pygame

from .constants import (
    BACKGROUND_COLOR,
    BUTTON_COLOR,
    BUTTON_DISABLED,
    BUTTON_HOVER,
    CARD_BORDER,
    CARD_COLOR,
    HIT_ZONE_Y,
    LANE_BOTTOM,
    LANE_COLORS,
    LANE_COUNT,
    LANE_TOP,
    LEAD_IN_SECONDS,
    LIST_ITEM_COLOR,
    LIST_ITEM_HOVER,
    LIST_ITEM_SELECTED,
    MUTED_TEXT,
    PANEL_COLOR,
    TEXT_COLOR,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    APP_TITLE,
)
from .library import SongLibrary


def configure_ffmpeg() -> None:
    if os.environ.get("IMAGEIO_FFMPEG_EXE"):
        return

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path


configure_ffmpeg()

if TYPE_CHECKING:
    from .app import RhythmPrototype


class LoopingVideo:
    def __init__(self, file_path: Path, size: tuple[int, int]) -> None:
        self.file_path = file_path
        self.size = size
        self.reader = None
        self.frame_count = 0
        self.fps = 24.0
        self.current_index = -1
        self.current_surface: pygame.Surface | None = None
        self.open()

    def open(self) -> None:
        try:
            self.reader = imageio.get_reader(str(self.file_path))
            metadata = self.reader.get_meta_data()
            self.fps = float(metadata.get("fps") or 24.0)
            frame_count = metadata.get("nframes") or 0
            self.frame_count = int(frame_count) if frame_count != float("inf") else 0
            if self.frame_count <= 0 and metadata.get("duration"):
                self.frame_count = max(1, int(float(metadata["duration"]) * self.fps))
        except Exception:
            self.reader = None

    def frame_for_time(self, song_time: float, advance: bool) -> pygame.Surface | None:
        if self.reader is None:
            return self.current_surface

        if advance:
            target_index = int(max(0.0, song_time) * self.fps)
            if self.frame_count > 0:
                target_index %= self.frame_count
        else:
            target_index = max(0, self.current_index)

        if target_index == self.current_index and self.current_surface is not None:
            return self.current_surface

        try:
            frame = self.reader.get_data(target_index)
        except Exception:
            try:
                self.reader.close()
            except Exception:
                pass
            self.open()
            target_index = 0
            try:
                frame = self.reader.get_data(target_index) if self.reader is not None else None
            except Exception:
                return self.current_surface

        if frame is None:
            return self.current_surface

        frame_format = "RGBA" if frame.shape[2] == 4 else "RGB"
        frame_surface = pygame.image.frombuffer(frame.tobytes(), frame.shape[1::-1], frame_format).convert()
        self.current_surface = cover_scale(frame_surface, self.size)
        self.current_index = target_index
        return self.current_surface


def resource_path(*parts: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base_path.joinpath(*parts)


def resource_glob(*parts: str) -> list[Path]:
    if not parts:
        return []

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return sorted(base_path.joinpath(*parts[:-1]).glob(parts[-1]))


def cover_scale(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    target_width, target_height = size
    source_width, source_height = surface.get_size()
    scale = max(target_width / source_width, target_height / source_height)
    scaled = pygame.transform.smoothscale(
        surface,
        (int(source_width * scale), int(source_height * scale)),
    )
    crop_rect = pygame.Rect(0, 0, target_width, target_height)
    crop_rect.center = scaled.get_rect().center
    return scaled.subsurface(crop_rect).copy()


class RhythmRenderer:
    def __init__(
        self,
        screen: pygame.Surface,
        title_font: pygame.font.Font,
        body_font: pygame.font.Font,
        small_font: pygame.font.Font,
    ) -> None:
        self.screen = screen
        self.title_font = title_font
        self.body_font = body_font
        self.small_font = small_font
        self.header_title_font = pygame.font.SysFont("arial", 44, bold=True)

        self.settings_button = pygame.Rect(WINDOW_WIDTH - 92, 30, 48, 48)
        self.upload_button = pygame.Rect(44, 112, 190, 46)
        self.back_button = pygame.Rect(WINDOW_WIDTH - 190, 112, 146, 46)

        self.replay_button = pygame.Rect(0, 0, 1, 1)
        self.stop_button = pygame.Rect(0, 0, 1, 1)
        self.view_button = pygame.Rect(0, 0, 1, 1)
        self.generate_button = pygame.Rect(0, 0, 1, 1)

        self.pause_button = pygame.Rect(WINDOW_WIDTH - 76, 24, 48, 42)
        self.pause_menu = pygame.Rect(WINDOW_WIDTH // 2 - 160, WINDOW_HEIGHT // 2 - 112, 320, 224)
        self.pause_continue_button = pygame.Rect(self.pause_menu.x + 36, self.pause_menu.y + 58, 248, 42)
        self.pause_replay_button = pygame.Rect(self.pause_menu.x + 36, self.pause_menu.y + 110, 248, 42)
        self.pause_exit_button = pygame.Rect(self.pause_menu.x + 36, self.pause_menu.y + 162, 248, 42)

        self.selection_card = pygame.Rect(36, 158, WINDOW_WIDTH - 72, 96)
        self.library_panel = pygame.Rect(44, 126, WINDOW_WIDTH - 88, 524)
        self.scroll_up_button = pygame.Rect(self.library_panel.right - 92, self.library_panel.y + 18, 36, 32)
        self.scroll_down_button = pygame.Rect(self.library_panel.right - 48, self.library_panel.y + 18, 36, 32)
        self.clear_library_button = pygame.Rect(self.library_panel.right - 228, self.library_panel.y + 18, 112, 32)
        self.home_start_button = pygame.Rect(self.library_panel.right - 262, self.library_panel.bottom - 58, 150, 38)

        self.lane_area = pygame.Rect(74, LANE_TOP, 852, LANE_BOTTOM - LANE_TOP)
        self.video_panel = pygame.Rect(
            self.lane_area.x + 24,
            LANE_TOP + 10,
            self.lane_area.width - 48,
            HIT_ZONE_Y + 58 - (LANE_TOP + 10),
        )
        self.background_image = self.load_background_image()
        self.header_logo = self.load_header_logo()
        self.settings_icon = self.load_settings_icon()
        self.lane_icons = self.load_lane_icons()
        self.video_loop = self.load_video_loop()
        self.visualizer_particles = self.build_visualizer_particles()
        self.menu_scene = self.build_menu_scene_surface()
        self.visualizer_scene = self.build_visualizer_scene_surface()
        self.lane_scene = self.build_lane_scene_surface()

    def draw(self, app: RhythmPrototype) -> None:
        if app.current_screen == "home":
            self.draw_home_screen(app)
            return

        if app.current_screen == "settings":
            self.draw_settings_screen(app)
            return

        self.draw_game_screen(app)

    def draw_home_screen(self, app: RhythmPrototype) -> None:
        self.screen.blit(self.menu_scene, (0, 0))
        self.draw_app_header(app, "")
        self.draw_library_panel(app, mode="home")

    def draw_settings_screen(self, app: RhythmPrototype) -> None:
        self.screen.blit(self.menu_scene, (0, 0))
        self.draw_app_header(app, "Configuracion")
        self.draw_button(self.upload_button, "Subir cancion", True)
        self.draw_button(self.back_button, "Volver", True)
        status_surface = self.small_font.render(
            self.fit_text(app.status_message, self.small_font, WINDOW_WIDTH - 88),
            True,
            MUTED_TEXT,
        )
        self.screen.blit(status_surface, (44, 172))
        self.library_panel.y = 212
        self.scroll_up_button.y = self.library_panel.y + 18
        self.scroll_down_button.y = self.library_panel.y + 18
        self.draw_library_panel(app, mode="settings")
        self.library_panel.y = 126
        self.scroll_up_button.y = self.library_panel.y + 18
        self.scroll_down_button.y = self.library_panel.y + 18

    def draw_app_header(self, app: RhythmPrototype, section: str) -> None:
        header = pygame.Rect(28, 18, WINDOW_WIDTH - 56, 86)
        self.draw_glass_rect(header, PANEL_COLOR, border_radius=20)
        title_y = header.y + (27 if section else 43)
        if self.header_logo is not None:
            max_logo_size = (300, 76) if not section else (220, 52)
            logo = self.scale_to_fit(self.header_logo, max_logo_size)
            logo_rect = logo.get_rect(midleft=(header.x + 22, title_y))
            self.screen.blit(logo, logo_rect)
        else:
            glow = self.header_title_font.render(APP_TITLE, True, (255, 78, 206))
            title = self.header_title_font.render(APP_TITLE, True, TEXT_COLOR)
            glow_rect = glow.get_rect(midleft=(header.x + 26, title_y + 4))
            title_rect = title.get_rect(midleft=(header.x + 22, title_y))
            self.screen.blit(glow, glow_rect)
            self.screen.blit(title, title_rect)
        if section:
            subtitle = self.small_font.render(section.upper(), True, MUTED_TEXT)
            subtitle_rect = subtitle.get_rect(midleft=(header.x + 22, header.y + 66))
            self.screen.blit(subtitle, subtitle_rect)

        count_text = self.small_font.render(
            f"{len(app.library.saved_songs)} canciones",
            True,
            (255, 244, 142),
        )
        self.screen.blit(count_text, (WINDOW_WIDTH - 250, 58))
        if app.current_screen == "home":
            self.draw_icon_button(self.settings_button, "gear", True)

    def draw_setup_screen(self, app: RhythmPrototype) -> None:
        pygame.draw.rect(self.screen, PANEL_COLOR, (0, 0, WINDOW_WIDTH, 126))
        title = self.title_font.render("", True, TEXT_COLOR)
        subtitle = self.small_font.render(
            "Primero eliges la cancion. Cuando generas la pista, se abre la pantalla de visualizacion.",
            True,
            MUTED_TEXT,
        )
        self.screen.blit(title, (36, 10))
        self.screen.blit(subtitle, (36, 86))

        self.draw_button(self.upload_button, "Subir audio", True)
        self.draw_button(self.generate_button, "Generar pista", app.selected_file is not None)
        self.draw_button(self.view_button, "Abrir pista", app.is_selected_track_ready())

        songs_saved = self.small_font.render(
            f"Canciones guardadas: {len(app.library.saved_songs)}",
            True,
            TEXT_COLOR,
        )
        self.screen.blit(songs_saved, (690, 48))

        status_surface = self.small_font.render(
            self.fit_text(app.status_message, self.small_font, WINDOW_WIDTH - 72),
            True,
            MUTED_TEXT,
        )
        self.screen.blit(status_surface, (36, 103))

        self.draw_selection_card(app)
        self.draw_library_panel(app)

    def draw_selection_card(self, app: RhythmPrototype) -> None:
        pygame.draw.rect(self.screen, CARD_COLOR, self.selection_card, border_radius=18)
        pygame.draw.rect(
            self.screen,
            CARD_BORDER,
            self.selection_card,
            width=2,
            border_radius=18,
        )

        label = self.small_font.render("Seleccion actual", True, MUTED_TEXT)
        self.screen.blit(label, (self.selection_card.x + 18, self.selection_card.y + 12))

        if not app.selected_file:
            hint = self.body_font.render(
                "Todavia no elegiste ninguna cancion.",
                True,
                TEXT_COLOR,
            )
            self.screen.blit(hint, (self.selection_card.x + 18, self.selection_card.y + 42))
            return

        song_name = self.body_font.render(
            self.fit_text(app.selected_file.stem, self.body_font, self.selection_card.width - 36),
            True,
            TEXT_COLOR,
        )
        self.screen.blit(song_name, (self.selection_card.x + 18, self.selection_card.y + 34))

        song_path = self.small_font.render(
            self.fit_text(str(app.selected_file), self.small_font, self.selection_card.width - 36),
            True,
            MUTED_TEXT,
        )
        self.screen.blit(song_path, (self.selection_card.x + 18, self.selection_card.y + 63))

        if not app.selected_file.exists():
            detail_text = "El archivo ya no se encuentra en disco."
        elif app.is_selected_track_ready():
            detail_text = "La pista ya esta generada. Puedes abrirla o reproducirla otra vez."
        else:
            detail_text = "Lista para generar una pista nueva."

        detail = self.small_font.render(detail_text, True, MUTED_TEXT)
        self.screen.blit(detail, (self.selection_card.right - 400, self.selection_card.y + 14))

    def draw_library_panel(self, app: RhythmPrototype, mode: str = "home") -> None:
        self.configure_library_controls(mode)
        self.draw_glass_rect(self.library_panel, CARD_COLOR, border_radius=24)

        title_text = "Canciones guardadas" if mode == "home" else "Administrar canciones"
        helper_text = (
            "Elige una pista y pulsa Play para jugar."
            if mode == "home"
            else "Sube nuevas canciones o elimina las que ya no quieras ver en el repertorio."
        )
        title = self.body_font.render(title_text, True, TEXT_COLOR)
        helper = self.small_font.render(helper_text, True, MUTED_TEXT)
        self.screen.blit(title, (self.library_panel.x + 20, self.library_panel.y + 16))
        self.screen.blit(helper, (self.library_panel.x + 20, self.library_panel.y + 42))

        self.draw_button(
            self.scroll_up_button,
            "/\\",
            app.library.song_scroll > 0,
            font=self.small_font,
        )
        self.draw_button(
            self.scroll_down_button,
            "\\/",
            app.library.song_scroll < app.library.max_song_scroll(),
            font=self.small_font,
        )
        if mode == "settings":
            self.draw_button(
                self.clear_library_button,
                "Vaciar",
                bool(app.library.saved_songs),
                font=self.small_font,
            )
        if not app.library.saved_songs:
            hint = self.body_font.render(
                "Aun no tienes canciones guardadas. Entra a configuracion y sube una.",
                True,
                MUTED_TEXT,
            )
            hint_rect = hint.get_rect(center=self.library_panel.center)
            self.screen.blit(hint, hint_rect)
            return

        mouse_pos = pygame.mouse.get_pos()
        for row_offset, song_index in enumerate(app.library.visible_song_indices()):
            song = app.library.saved_songs[song_index]
            row_rect = self.song_row_rect(row_offset)
            song_exists = Path(song.path).exists()

            if song_index == app.library.selected_song_index:
                row_color = LIST_ITEM_SELECTED
            elif row_rect.collidepoint(mouse_pos):
                row_color = LIST_ITEM_HOVER
            else:
                row_color = LIST_ITEM_COLOR

            self.draw_song_row(row_rect, row_color, song.display_name, song_index, song_exists, mode)

            if mode == "home":
                action_rect = self.song_action_rect(row_offset, mode)
                accent = LANE_COLORS[song_index % len(LANE_COLORS)]
                self.draw_song_play_button(action_rect, accent, song_index, song_exists)
            else:
                action_rect = self.song_action_rect(row_offset, mode)
                self.draw_button(action_rect, "Eliminar", True, font=self.small_font)

    def draw_song_row(
        self,
        row_rect: pygame.Rect,
        row_color: tuple[int, ...],
        song_name: str,
        song_index: int,
        song_exists: bool,
        mode: str,
    ) -> None:
        fill = row_color if len(row_color) == 4 else (*row_color, 255)
        if mode == "home":
            surface = pygame.Surface(row_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(surface, (248, 251, 255, 236), surface.get_rect(), border_radius=12)
            pygame.draw.rect(surface, (*LANE_COLORS[song_index % len(LANE_COLORS)], 42), surface.get_rect(), border_radius=12)
            pygame.draw.rect(surface, (255, 255, 255, 210), surface.get_rect(), width=2, border_radius=12)
            self.screen.blit(surface, row_rect)
            text_color = (38, 45, 67)
        else:
            self.draw_glass_rect(row_rect, fill, border_radius=14, border_alpha=70)
            text_color = TEXT_COLOR

        accent = LANE_COLORS[song_index % len(LANE_COLORS)]
        if mode != "home":
            cover_center = (row_rect.x + 42, row_rect.centery)
            self.draw_song_cover(cover_center, 24, accent, song_index, mode)

        number = self.small_font.render(str(song_index + 1), True, accent if mode == "home" else TEXT_COLOR)
        self.screen.blit(number, (row_rect.x + 9, row_rect.y + 8))

        title_x = row_rect.x + (42 if mode == "home" else 78)
        action_rect = self.song_action_rect(
            (row_rect.y - self.library_panel.y - 74) // 76,
            mode,
        )
        title_max_width = action_rect.x - title_x - 18
        title = self.body_font.render(
            self.fit_text(song_name, self.body_font, title_max_width),
            True,
            text_color if song_exists else (145, 151, 170),
        )
        self.screen.blit(title, title.get_rect(midleft=(title_x, row_rect.centery)))

    def draw_song_cover(
        self,
        center: tuple[int, int],
        radius: int,
        accent: tuple[int, int, int],
        song_index: int,
        mode: str,
    ) -> None:
        shadow_color = (0, 0, 0, 65) if mode == "home" else (0, 0, 0, 110)
        pygame.draw.circle(self.screen, shadow_color, (center[0] + 2, center[1] + 3), radius + 3)
        pygame.draw.circle(self.screen, (20, 24, 47), center, radius)
        pygame.draw.circle(self.screen, accent, center, radius, 3)

        inner = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for step in range(radius, 0, -1):
            amount = step / radius
            color = tuple(int(channel * amount + 18 * (1 - amount)) for channel in accent)
            pygame.draw.circle(inner, (*color, 190), (radius, radius), step)

        self.screen.blit(inner, (center[0] - radius, center[1] - radius))
        pygame.draw.circle(self.screen, (255, 255, 255, 230), center, radius, 2)

        play_points = [
            (center[0] - 6, center[1] - 10),
            (center[0] - 6, center[1] + 10),
            (center[0] + 11, center[1]),
        ]
        pygame.draw.polygon(self.screen, (255, 255, 255), play_points)
        if song_index % 2 == 0:
            pygame.draw.arc(
                self.screen,
                (255, 255, 255, 130),
                pygame.Rect(center[0] - 18, center[1] - 18, 36, 36),
                0.35,
                3.4,
                2,
            )

    def draw_song_play_button(
        self,
        rect: pygame.Rect,
        accent: tuple[int, int, int],
        song_index: int,
        enabled: bool,
    ) -> None:
        mouse_over = enabled and rect.collidepoint(pygame.mouse.get_pos())
        radius = min(rect.width, rect.height) // 2
        center = rect.center

        glow_size = 10 if mouse_over else 6
        glow = pygame.Surface((rect.width + glow_size * 2, rect.height + glow_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            (*accent, 82 if mouse_over else 46),
            (glow.get_width() // 2, glow.get_height() // 2),
            radius + glow_size // 2,
        )
        self.screen.blit(glow, (rect.x - glow_size, rect.y - glow_size))

        button_accent = accent if enabled else (126, 132, 154)
        self.draw_song_cover(center, radius - 2, button_accent, song_index, "home")

    def draw_pill_button(self, rect: pygame.Rect, label: str, enabled: bool) -> None:
        mouse_over = rect.collidepoint(pygame.mouse.get_pos())
        if enabled:
            left_color = (26, 150, 255) if mouse_over else (37, 126, 255)
            right_color = (67, 235, 255) if mouse_over else (40, 214, 246)
        else:
            left_color = (126, 132, 154)
            right_color = (152, 158, 178)
        if mouse_over and enabled:
            glow_rect = rect.inflate(8, 8)
            glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (69, 227, 255, 70), glow.get_rect(), border_radius=glow_rect.height // 2)
            self.screen.blit(glow, glow_rect)
        self.draw_gradient_rect(rect, left_color, right_color, border_radius=rect.height // 2)
        border_color = (255, 255, 255, 245) if mouse_over and enabled else (255, 255, 255, 190)
        pygame.draw.rect(self.screen, border_color, rect, width=2, border_radius=rect.height // 2)
        if mouse_over and enabled:
            shine_rect = pygame.Rect(rect.x + 12, rect.y + 6, rect.width - 24, 5)
            pygame.draw.rect(self.screen, (255, 255, 255, 95), shine_rect, border_radius=3)
        text = self.body_font.render(label, True, (255, 255, 255))
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_game_screen(self, app: RhythmPrototype) -> None:
        self.screen.blit(self.visualizer_scene, (0, 0))
        self.draw_video_panel(app)
        self.screen.blit(self.lane_scene, (0, 0))
        self.draw_lane_view(app)
        self.draw_button(self.pause_button, "||", True, font=self.body_font)

        if app.is_paused:
            self.draw_pause_overlay()
        elif app.analysis and not app.is_playing:
            hint = self.small_font.render(
                self.fit_text(app.status_message, self.small_font, self.lane_area.width - 80),
                True,
                TEXT_COLOR,
            )
            hint_rect = hint.get_rect(center=(WINDOW_WIDTH // 2, LANE_TOP + 34))
            self.screen.blit(hint, hint_rect)

    def draw_visualizer_screen(self, app: RhythmPrototype) -> None:
        self.screen.blit(self.visualizer_scene, (0, 0))

        panel_surface = pygame.Surface((WINDOW_WIDTH, 126), pygame.SRCALPHA)
        panel_surface.fill((7, 10, 28, 170))
        pygame.draw.line(panel_surface, (255, 255, 255, 34), (0, 125), (WINDOW_WIDTH, 125), 2)
        self.screen.blit(panel_surface, (0, 0))

        title = self.title_font.render("Visualizacion de la pista", True, TEXT_COLOR)
        subtitle = self.small_font.render(
            "Aqui puedes ver la pista generada y reproducirla todas las veces que quieras.",
            True,
            MUTED_TEXT,
        )
        self.screen.blit(title, (36, 10))
        self.screen.blit(subtitle, (36, 86))

        self.draw_button(self.replay_button, "Reproducir otra vez", app.analysis is not None)
        self.draw_button(self.stop_button, "Detener", app.is_playing)
        self.draw_button(self.back_button, "Volver", True)

        track_name = app.analysis_source.stem if app.analysis_source else "Sin pista"
        info_text = f"Pista: {track_name}"
        if app.analysis:
            info_text += f" | {len(app.analysis.notes)} notas | {app.analysis.tempo:.1f} BPM"
        info_surface = self.small_font.render(
            self.fit_text(info_text, self.small_font, WINDOW_WIDTH - 72),
            True,
            TEXT_COLOR,
        )
        self.screen.blit(info_surface, (36, 103))

        self.draw_lane_view(app)

        if app.analysis and not app.is_playing:
            hint = self.small_font.render(
                self.fit_text(
                    app.status_message,
                    self.small_font,
                    self.lane_area.width - 80,
                ),
                True,
                TEXT_COLOR,
            )
            hint_rect = hint.get_rect(center=(WINDOW_WIDTH // 2, LANE_TOP + 34))
            self.screen.blit(hint, hint_rect)

    def draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        enabled: bool,
        font: pygame.font.Font | None = None,
    ) -> None:
        button_font = font or self.body_font
        mouse_over = rect.collidepoint(pygame.mouse.get_pos())
        if enabled:
            left_color = BUTTON_HOVER if mouse_over else BUTTON_COLOR
            right_color = (81, 221, 255) if mouse_over else (122, 89, 255)
            self.draw_gradient_rect(rect, left_color, right_color, border_radius=14)
        else:
            self.draw_gradient_rect(rect, BUTTON_DISABLED, (78, 82, 120), border_radius=14)
        pygame.draw.rect(self.screen, (255, 255, 255, 180), rect, width=2, border_radius=14)
        shine_rect = pygame.Rect(rect.x + 5, rect.y + 5, rect.width - 10, max(6, rect.height // 3))
        shine = pygame.Surface(shine_rect.size, pygame.SRCALPHA)
        shine.fill((255, 255, 255, 38 if enabled else 18))
        self.screen.blit(shine, shine_rect)
        text_surface = button_font.render(label, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def draw_icon_button(self, rect: pygame.Rect, icon: str, enabled: bool) -> None:
        mouse_over = rect.collidepoint(pygame.mouse.get_pos())
        left_color = BUTTON_HOVER if mouse_over else (255, 90, 209)
        right_color = (78, 226, 255) if mouse_over else (124, 96, 255)
        self.draw_gradient_rect(rect, left_color if enabled else BUTTON_DISABLED, right_color, border_radius=14)
        pygame.draw.rect(self.screen, (255, 255, 255, 190), rect, width=2, border_radius=14)
        if icon == "gear":
            if self.settings_icon is not None:
                icon_rect = self.settings_icon.get_rect(center=rect.center)
                self.screen.blit(self.settings_icon, icon_rect)
            else:
                pygame.draw.circle(self.screen, TEXT_COLOR, rect.center, 13, 3)
                pygame.draw.circle(self.screen, TEXT_COLOR, rect.center, 4)

    def draw_pause_overlay(self) -> None:
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((9, 10, 34, 146))
        self.screen.blit(overlay, (0, 0))

        self.draw_glass_rect(self.pause_menu, (255, 255, 255, 48), border_radius=24)
        title = self.title_font.render("Pausa", True, TEXT_COLOR)
        title_rect = title.get_rect(center=(self.pause_menu.centerx, self.pause_menu.y + 30))
        self.screen.blit(title, title_rect)
        self.draw_button(self.pause_continue_button, "Continue", True, font=self.body_font)
        self.draw_button(self.pause_replay_button, "Replay", True, font=self.body_font)
        self.draw_button(self.pause_exit_button, "Exit", True, font=self.body_font)

    def draw_video_panel(self, app: RhythmPrototype) -> None:
        frame = None
        if self.video_loop is not None and app.analysis is not None:
            frame = self.video_loop.frame_for_time(app.current_song_time(), app.is_playing and not app.is_paused)

        video_surface = pygame.Surface(self.video_panel.size, pygame.SRCALPHA)
        if frame is not None:
            video_surface.blit(frame, (0, 0))
            video_surface.set_alpha(145)
        else:
            video_surface.fill((255, 255, 255, 18))

        self.screen.blit(video_surface, self.video_panel)

    def video_mask_points(self) -> list[tuple[int, int]]:
        left_top, right_top = self.track_bounds_for_y(LANE_TOP + 10)
        left_bottom, right_bottom = self.track_bounds_for_y(HIT_ZONE_Y + 50)
        points = [
            (left_top, LANE_TOP + 10),
            (right_top, LANE_TOP + 10),
            (right_bottom, HIT_ZONE_Y + 50),
            (left_bottom, HIT_ZONE_Y + 50),
        ]
        return [
            (int(x - self.video_panel.x), int(y - self.video_panel.y))
            for x, y in points
        ]

    def draw_lane_view(self, app: RhythmPrototype) -> None:
        if not app.analysis:
            hint = self.body_font.render(
                "La pista aparecera aqui cuando generes una visualizacion.",
                True,
                MUTED_TEXT,
            )
            hint_rect = hint.get_rect(center=(WINDOW_WIDTH // 2, LANE_TOP + 88))
            self.screen.blit(hint, hint_rect)
            return

        self.draw_notes(app, app.current_song_time())

    def draw_notes(self, app: RhythmPrototype, song_time: float) -> None:
        notes_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        travel_start = 0.0
        travel_end = HIT_ZONE_Y + 18.0
        burst_duration = 0.46

        for note in app.analysis.notes:
            spawn_time = note.hit_time - LEAD_IN_SECONDS
            if song_time < spawn_time or song_time > note.hit_time + burst_duration:
                continue

            if song_time <= note.hit_time:
                progress = max(0.0, min(1.0, (song_time - spawn_time) / LEAD_IN_SECONDS))
                y_position = self.lerp(travel_start, travel_end, progress ** 0.92)
                self.draw_note_gem(notes_surface, note.lane, y_position, progress)
                continue

            burst_progress = (song_time - note.hit_time) / burst_duration
            self.draw_note_burst(notes_surface, note.lane, travel_end, burst_progress, note.hit_time)

        self.screen.blit(notes_surface, (0, 0))

    def song_row_rect(self, row_offset: int) -> pygame.Rect:
        return pygame.Rect(
            self.library_panel.x + 20,
            self.library_panel.y + 74 + row_offset * 76,
            self.library_panel.width - 40,
            64,
        )

    def song_action_rect(self, row_offset: int, mode: str = "home") -> pygame.Rect:
        row_rect = self.song_row_rect(row_offset)
        if mode == "home":
            return pygame.Rect(row_rect.right - 64, row_rect.y + 8, 48, 48)
        return pygame.Rect(row_rect.right - 126, row_rect.y + 13, 104, 38)

    def configure_library_controls(self, mode: str) -> None:
        self.scroll_up_button.update(self.library_panel.right - 92, self.library_panel.y + 18, 36, 32)
        self.scroll_down_button.update(self.library_panel.right - 48, self.library_panel.y + 18, 36, 32)
        self.clear_library_button.update(self.scroll_up_button.x - 124, self.library_panel.y + 18, 112, 32)

    def song_index_from_position(
        self,
        library: SongLibrary,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        for row_offset, song_index in enumerate(library.visible_song_indices()):
            if self.song_row_rect(row_offset).collidepoint(mouse_pos):
                return song_index

        return None

    def start_song_index_from_position(
        self,
        library: SongLibrary,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        for row_offset, song_index in enumerate(library.visible_song_indices()):
            if self.song_action_rect(row_offset, "home").collidepoint(mouse_pos):
                return song_index

        return None

    def delete_song_index_from_position(
        self,
        library: SongLibrary,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        for row_offset, song_index in enumerate(library.visible_song_indices()):
            if self.song_action_rect(row_offset, "settings").collidepoint(mouse_pos):
                return song_index

        return None

    def load_background_image(self) -> pygame.Surface | None:
        background_path = resource_path("assets", "cpdito", "FondoLoginRegistro.jpg.jpeg")
        if not background_path.exists():
            return None

        try:
            image = pygame.image.load(str(background_path)).convert()
        except (FileNotFoundError, pygame.error):
            return None
        return cover_scale(image, (WINDOW_WIDTH, WINDOW_HEIGHT))

    def load_header_logo(self) -> pygame.Surface | None:
        logo_path = resource_path("assets", "cpdito", "CPD Hero transparent.png")
        if not logo_path.exists():
            return None

        try:
            return pygame.image.load(str(logo_path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return None

    def load_settings_icon(self) -> pygame.Surface | None:
        icon_path = resource_path("assets", "cpdito", "settings-1630709_640.webp")
        if not icon_path.exists():
            return None

        try:
            icon = pygame.image.load(str(icon_path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return None

        return pygame.transform.smoothscale(icon, (34, 34))

    @staticmethod
    def scale_to_fit(surface: pygame.Surface, max_size: tuple[int, int]) -> pygame.Surface:
        source_width, source_height = surface.get_size()
        max_width, max_height = max_size
        scale = min(max_width / source_width, max_height / source_height)
        target_size = (
            max(1, int(source_width * scale)),
            max(1, int(source_height * scale)),
        )
        return pygame.transform.smoothscale(surface, target_size)

    def load_lane_icons(self) -> list[pygame.Surface | None]:
        icon_names = [
            "Aplauso-CPD-FeriaSR.png",
            "Chasquido-CPD-FeriaSR.png",
            "Pecho-CPD-FeriaSR.png",
            "Piso-CPD-FeriaSR.png",
            "Sentadilla-CPD-FeriaSR.png",
        ]
        icons: list[pygame.Surface | None] = []
        for icon_name in icon_names:
            icon_path = resource_path("assets", "cpdito", icon_name)
            if not icon_path.exists():
                icons.append(None)
                continue
            try:
                icon = pygame.image.load(str(icon_path)).convert_alpha()
            except (FileNotFoundError, pygame.error):
                icons.append(None)
                continue
            icons.append(cover_scale(icon, (86, 86)))
        return icons

    def load_video_loop(self) -> LoopingVideo | None:
        video_path = resource_path("assets", "cpdito", "cpdito bailarín.mp4")
        if not video_path.exists():
            video_matches = resource_glob("assets", "cpdito", "cpdito bailar*.mp4")
            video_path = video_matches[0] if video_matches else video_path
        if not video_path.exists():
            return None
        return LoopingVideo(video_path, self.video_panel.size)

    @staticmethod
    def fit_text(text: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text

        trimmed = text
        while trimmed and font.size(f"{trimmed}...")[0] > max_width:
            trimmed = trimmed[:-1]

        return f"{trimmed}..." if trimmed else "..."

    def build_visualizer_particles(self) -> list[tuple[int, int, int, int]]:
        rng = random.Random(19)
        particles: list[tuple[int, int, int, int]] = []
        for _ in range(32):
            particles.append(
                (
                    rng.randint(self.lane_area.x + 30, self.lane_area.right - 30),
                    rng.randint(LANE_TOP + 26, HIT_ZONE_Y - 110),
                    rng.randint(1, 3),
                    rng.randint(22, 72),
                )
            )
        return particles

    @staticmethod
    def lerp(start: float, end: float, amount: float) -> float:
        return start + (end - start) * amount

    @staticmethod
    def to_int_points(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
        return [(int(x), int(y)) for x, y in points]

    def draw_gradient_rect(
        self,
        rect: pygame.Rect,
        left_color: tuple[int, int, int],
        right_color: tuple[int, int, int],
        border_radius: int = 0,
    ) -> None:
        gradient = pygame.Surface(rect.size, pygame.SRCALPHA)
        for x_pos in range(max(1, rect.width)):
            amount = x_pos / max(1, rect.width - 1)
            color = tuple(
                int(self.lerp(left, right, amount))
                for left, right in zip(left_color, right_color)
            )
            pygame.draw.line(gradient, color, (x_pos, 0), (x_pos, rect.height))

        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=border_radius)
        gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(gradient, rect)

    def draw_glass_rect(
        self,
        rect: pygame.Rect,
        color: tuple[int, ...],
        border_radius: int = 18,
        border_alpha: int = 112,
    ) -> None:
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        fill = color if len(color) == 4 else (*color, 48)
        pygame.draw.rect(surface, fill, surface.get_rect(), border_radius=border_radius)
        pygame.draw.rect(
            surface,
            (255, 255, 255, border_alpha),
            surface.get_rect(),
            width=2,
            border_radius=border_radius,
        )
        pygame.draw.line(
            surface,
            (255, 255, 255, min(160, border_alpha + 42)),
            (border_radius, 5),
            (rect.width - border_radius, 5),
            2,
        )
        self.screen.blit(surface, rect)

    def build_menu_scene_surface(self) -> pygame.Surface:
        scene = self.background_image.copy() if self.background_image else pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        top = (255, 84, 190)
        mid = (111, 88, 255)
        bottom = (34, 219, 229)

        if self.background_image is None:
            for y_pos in range(WINDOW_HEIGHT):
                blend = y_pos / max(1, WINDOW_HEIGHT - 1)
                if blend < 0.52:
                    local_blend = blend / 0.52
                    color = tuple(int(self.lerp(a, b, local_blend)) for a, b in zip(top, mid))
                else:
                    local_blend = (blend - 0.52) / 0.48
                    color = tuple(int(self.lerp(a, b, local_blend)) for a, b in zip(mid, bottom))
                pygame.draw.line(scene, color, (0, y_pos), (WINDOW_WIDTH, y_pos))
        return scene

    def track_bounds_for_y(self, y: float) -> tuple[float, float]:
        clamped_progress = max(0.0, min(1.0, (y - LANE_TOP) / max(1, HIT_ZONE_Y - LANE_TOP)))
        half_width = self.lerp(
            self.lane_area.width * 0.31,
            self.lane_area.width * 0.49,
            clamped_progress ** 0.9,
        )
        center_shift = self.lerp(-18.0, 16.0, clamped_progress)
        center_x = self.lane_area.centerx + center_shift
        return center_x - half_width, center_x + half_width

    def lane_edges_for_y(self, lane: int, y: float) -> tuple[float, float]:
        left_bound, right_bound = self.track_bounds_for_y(y)
        lane_width = (right_bound - left_bound) / LANE_COUNT
        lane_left = left_bound + lane * lane_width
        return lane_left, lane_left + lane_width

    def lane_center_for_y(self, lane: int, y: float) -> float:
        lane_left, lane_right = self.lane_edges_for_y(lane, y)
        return (lane_left + lane_right) / 2.0

    def lane_beam_points(self, lane: int) -> tuple[tuple[float, float], tuple[float, float]]:
        top_y = 0.0
        bottom_y = HIT_ZONE_Y + 18.0
        return (
            (self.lane_center_for_y(lane, top_y), top_y),
            (self.lane_center_for_y(lane, bottom_y), bottom_y),
        )

    def lane_beam_center_for_y(self, lane: int, y: float) -> float:
        (top_x, top_y), (bottom_x, bottom_y) = self.lane_beam_points(lane)
        progress = (y - top_y) / max(1.0, bottom_y - top_y)
        return self.lerp(top_x, bottom_x, max(0.0, min(1.0, progress)))

    def scale_polygon(
        self,
        points: list[tuple[float, float]],
        scale_x: float,
        scale_y: float,
    ) -> list[tuple[float, float]]:
        center_x = sum(x for x, _ in points) / len(points)
        center_y = sum(y for _, y in points) / len(points)
        return [
            (
                center_x + (x - center_x) * scale_x,
                center_y + (y - center_y) * scale_y,
            )
            for x, y in points
        ]

    def draw_glow_line(
        self,
        surface: pygame.Surface,
        color: tuple[int, int, int],
        start: tuple[float, float],
        end: tuple[float, float],
        core_width: int,
    ) -> None:
        start_pos = (int(start[0]), int(start[1]))
        end_pos = (int(end[0]), int(end[1]))
        for extra_width, alpha in ((18, 18), (12, 28), (8, 46), (4, 72)):
            pygame.draw.line(
                surface,
                (*color, alpha),
                start_pos,
                end_pos,
                max(1, core_width + extra_width),
            )

        boosted = tuple(min(255, channel + 56) for channel in color)
        pygame.draw.line(surface, (*boosted, 180), start_pos, end_pos, core_width + 2)
        pygame.draw.line(surface, (255, 255, 255, 220), start_pos, end_pos, max(1, core_width))

    def draw_lane_emblem(
        self,
        surface: pygame.Surface,
        lane: int,
        center: tuple[int, int],
    ) -> None:
        x_pos, y_pos = center
        emblem_color = (255, 242, 205, 230)

        if lane == 0:
            bolt = [
                (x_pos - 4, y_pos - 11),
                (x_pos + 3, y_pos - 11),
                (x_pos - 1, y_pos - 2),
                (x_pos + 7, y_pos - 2),
                (x_pos - 5, y_pos + 11),
                (x_pos - 1, y_pos + 2),
                (x_pos - 8, y_pos + 2),
            ]
            pygame.draw.polygon(surface, emblem_color, bolt)
            return

        if lane == 1:
            pygame.draw.polygon(
                surface,
                emblem_color,
                [(x_pos, y_pos - 11), (x_pos - 10, y_pos + 7), (x_pos + 10, y_pos + 7)],
                2,
            )
            return

        if lane == 2:
            pygame.draw.circle(surface, emblem_color, (x_pos, y_pos), 8, 2)
            pygame.draw.line(surface, emblem_color, (x_pos - 5, y_pos + 5), (x_pos + 5, y_pos - 5), 2)
            return

        if lane == 3:
            flame = [
                (x_pos, y_pos - 11),
                (x_pos + 5, y_pos - 2),
                (x_pos + 2, y_pos + 10),
                (x_pos, y_pos + 12),
                (x_pos - 6, y_pos + 4),
                (x_pos - 3, y_pos - 4),
            ]
            pygame.draw.polygon(surface, emblem_color, flame)
            return

        pygame.draw.lines(
            surface,
            emblem_color,
            False,
            [(x_pos - 9, y_pos - 7), (x_pos - 1, y_pos + 1), (x_pos - 9, y_pos + 9)],
            2,
        )
        pygame.draw.lines(
            surface,
            emblem_color,
            False,
            [(x_pos, y_pos - 7), (x_pos + 8, y_pos + 1), (x_pos, y_pos + 9)],
            2,
        )

    def draw_lane_receptor(self, surface: pygame.Surface, lane: int) -> None:
        lane_color = LANE_COLORS[lane]
        center_y = HIT_ZONE_Y + 28
        center_x = self.lane_center_for_y(lane, center_y)
        tile_rect = pygame.Rect(0, 0, 96, 96)
        tile_rect.center = (int(center_x), int(center_y))
        glow_rect = tile_rect.inflate(18, 18)

        pygame.draw.rect(surface, (*lane_color, 52), glow_rect, border_radius=22)
        pygame.draw.rect(surface, (10, 18, 48, 214), tile_rect, border_radius=18)
        pygame.draw.rect(surface, (*lane_color, 132), tile_rect.inflate(-8, -8), border_radius=15)
        pygame.draw.rect(surface, (255, 255, 255, 228), tile_rect, width=3, border_radius=18)
        pygame.draw.line(
            surface,
            (255, 255, 255, 142),
            (tile_rect.x + 14, tile_rect.y + 10),
            (tile_rect.right - 14, tile_rect.y + 10),
            2,
        )
        icon = self.lane_icons[lane] if lane < len(self.lane_icons) else None
        if icon is not None:
            icon_rect = icon.get_rect(center=tile_rect.center)
            surface.blit(icon, icon_rect)
        else:
            self.draw_lane_emblem(surface, lane, (int(center_x), int(center_y + 1)))

    def draw_note_gem(
        self,
        surface: pygame.Surface,
        lane: int,
        y_pos: float,
        progress: float,
    ) -> None:
        lane_color = LANE_COLORS[lane]
        center_x = self.lane_beam_center_for_y(lane, y_pos)
        size = self.lerp(10.0, 22.0, progress ** 0.9)
        trail_start_y = y_pos - size * 2.2
        trail_end_y = y_pos + size * 0.1
        trail_start = (self.lane_beam_center_for_y(lane, trail_start_y), trail_start_y)
        trail_end = (self.lane_beam_center_for_y(lane, trail_end_y), trail_end_y)
        points = [
            (center_x, y_pos - size),
            (center_x - size * 0.88, y_pos),
            (center_x, y_pos + size),
            (center_x + size * 0.88, y_pos),
        ]
        glow_points = self.scale_polygon(points, 1.48, 1.48)
        inner_glint = self.scale_polygon(points, 0.58, 0.58)

        self.draw_glow_line(surface, lane_color, trail_start, trail_end, max(1, int(size * 0.18)))
        pygame.draw.polygon(surface, (*lane_color, 34), self.to_int_points(glow_points))
        pygame.draw.polygon(surface, (*lane_color, 196), self.to_int_points(points))
        pygame.draw.polygon(surface, (255, 255, 255, 135), self.to_int_points(inner_glint))
        pygame.draw.polygon(surface, (255, 255, 255, 228), self.to_int_points(points), 2)

    def draw_note_burst(
        self,
        surface: pygame.Surface,
        lane: int,
        y_pos: float,
        progress: float,
        seed_time: float,
    ) -> None:
        lane_color = LANE_COLORS[lane]
        center_x = self.lane_beam_center_for_y(lane, y_pos)
        center = (int(center_x), int(y_pos))
        eased = 1.0 - (1.0 - progress) ** 2
        fade = max(0.0, 1.0 - progress)

        ring_radius = int(self.lerp(10.0, 54.0, eased))
        ring_alpha = int(150 * fade)
        if ring_alpha > 0:
            for extra_radius, alpha_scale in ((10, 0.28), (4, 0.55), (0, 1.0)):
                pygame.draw.circle(
                    surface,
                    (*lane_color, int(ring_alpha * alpha_scale)),
                    center,
                    ring_radius + extra_radius,
                    2,
                )

        flash_radius = int(self.lerp(20.0, 72.0, eased))
        flash_alpha = int(72 * fade)
        if flash_alpha > 0:
            flash = pygame.Surface((flash_radius * 2, flash_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                flash,
                (*lane_color, flash_alpha),
                (flash_radius, flash_radius),
                flash_radius,
            )
            surface.blit(flash, (center[0] - flash_radius, center[1] - flash_radius), special_flags=pygame.BLEND_ADD)

        rng = random.Random(lane * 1009 + int(seed_time * 1000))
        shard_count = 14
        for shard_index in range(shard_count):
            angle = (math.tau * shard_index / shard_count) + rng.uniform(-0.18, 0.18)
            distance = self.lerp(12.0, rng.uniform(46.0, 86.0), eased)
            x_pos = center_x + math.cos(angle) * distance
            y_shard = y_pos + math.sin(angle) * distance * 0.76
            shard_size = self.lerp(rng.uniform(7.0, 12.0), 1.5, progress)
            alpha = int(rng.uniform(150, 235) * fade)
            if alpha <= 0:
                continue

            tangent = angle + math.pi / 2
            points = [
                (x_pos + math.cos(angle) * shard_size, y_shard + math.sin(angle) * shard_size),
                (x_pos + math.cos(tangent) * shard_size * 0.44, y_shard + math.sin(tangent) * shard_size * 0.44),
                (x_pos - math.cos(angle) * shard_size, y_shard - math.sin(angle) * shard_size),
                (x_pos - math.cos(tangent) * shard_size * 0.44, y_shard - math.sin(tangent) * shard_size * 0.44),
            ]
            pygame.draw.polygon(surface, (*lane_color, alpha), self.to_int_points(points))
            pygame.draw.line(surface, (255, 255, 255, min(220, alpha + 30)), center, (int(x_pos), int(y_shard)), 1)

        star_alpha = int(245 * fade)
        if star_alpha > 0:
            star_span = int(self.lerp(22.0, 50.0, eased))
            pygame.draw.line(surface, (255, 255, 255, star_alpha), (center[0] - star_span, center[1]), (center[0] + star_span, center[1]), 3)
            pygame.draw.line(surface, (255, 255, 255, star_alpha), (center[0], center[1] - star_span), (center[0], center[1] + star_span), 3)

    def build_visualizer_scene_surface(self) -> pygame.Surface:
        scene = self.background_image.copy() if self.background_image else pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        dawn_top = (32, 20, 114)
        dawn_mid = (255, 74, 181)
        night_bottom = (12, 204, 216)

        if self.background_image is None:
            for y_pos in range(WINDOW_HEIGHT):
                blend = y_pos / max(1, WINDOW_HEIGHT - 1)
                if blend < 0.58:
                    local_blend = blend / 0.58
                    color = tuple(
                        int(self.lerp(top, mid, local_blend))
                        for top, mid in zip(dawn_top, dawn_mid)
                    )
                else:
                    local_blend = (blend - 0.58) / 0.42
                    color = tuple(
                        int(self.lerp(mid, bottom, local_blend))
                        for mid, bottom in zip(dawn_mid, night_bottom)
                    )
                pygame.draw.line(scene, color, (0, y_pos), (WINDOW_WIDTH, y_pos))

        return scene

    def build_lane_scene_surface(self) -> pygame.Surface:
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

        left_top, right_top = self.track_bounds_for_y(LANE_TOP + 10)
        left_bottom, right_bottom = self.track_bounds_for_y(HIT_ZONE_Y + 50)
        track_shadow = [
            (left_top, LANE_TOP + 10),
            (right_top, LANE_TOP + 10),
            (right_bottom, HIT_ZONE_Y + 50),
            (left_bottom, HIT_ZONE_Y + 50),
        ]
        pygame.draw.polygon(overlay, (255, 255, 255, 34), self.to_int_points(track_shadow))
        pygame.draw.polygon(overlay, (255, 255, 255, 94), self.to_int_points(track_shadow), 2)

        for lane, lane_color in enumerate(LANE_COLORS):
            (top_center_x, beam_top_y), (bottom_center_x, beam_bottom_y) = self.lane_beam_points(lane)
            beam_points = [
                (top_center_x - 8, beam_top_y),
                (top_center_x + 8, beam_top_y),
                (bottom_center_x + 42, beam_bottom_y),
                (bottom_center_x - 42, beam_bottom_y),
            ]
            pygame.draw.polygon(overlay, (*lane_color, 28), self.to_int_points(beam_points))
            self.draw_glow_line(
                overlay,
                lane_color,
                (top_center_x, beam_top_y),
                (bottom_center_x, beam_bottom_y),
                3,
            )

        floor_glow = pygame.Rect(self.lane_area.x + 110, HIT_ZONE_Y - 6, self.lane_area.width - 220, 86)
        pygame.draw.ellipse(overlay, (255, 255, 255, 22), floor_glow)

        for lane in range(LANE_COUNT):
            self.draw_lane_receptor(overlay, lane)

        return overlay
