from __future__ import annotations

from pathlib import Path
import random
from typing import TYPE_CHECKING

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
)
from .library import SongLibrary

if TYPE_CHECKING:
    from .app import RhythmPrototype


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

        self.upload_button = pygame.Rect(36, 36, 180, 44)
        self.generate_button = pygame.Rect(232, 36, 200, 44)
        self.view_button = pygame.Rect(448, 36, 190, 44)

        self.replay_button = pygame.Rect(36, 36, 210, 44)
        self.stop_button = pygame.Rect(262, 36, 140, 44)
        self.back_button = pygame.Rect(418, 36, 170, 44)

        self.selection_card = pygame.Rect(36, 158, WINDOW_WIDTH - 72, 96)
        self.library_panel = pygame.Rect(36, 272, WINDOW_WIDTH - 72, 400)
        self.scroll_up_button = pygame.Rect(self.library_panel.right - 92, self.library_panel.y + 18, 36, 32)
        self.scroll_down_button = pygame.Rect(self.library_panel.right - 48, self.library_panel.y + 18, 36, 32)

        self.lane_area = pygame.Rect(74, LANE_TOP, 852, LANE_BOTTOM - LANE_TOP)
        self.visualizer_particles = self.build_visualizer_particles()
        self.visualizer_scene = self.build_visualizer_scene_surface()

    def draw(self, app: RhythmPrototype) -> None:
        self.screen.fill(BACKGROUND_COLOR)
        if app.current_screen == "setup":
            self.draw_setup_screen(app)
            return

        self.draw_visualizer_screen(app)

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
            self.fit_text(app.selected_file.name, self.body_font, self.selection_card.width - 36),
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

    def draw_library_panel(self, app: RhythmPrototype) -> None:
        pygame.draw.rect(self.screen, CARD_COLOR, self.library_panel, border_radius=18)
        pygame.draw.rect(
            self.screen,
            CARD_BORDER,
            self.library_panel,
            width=2,
            border_radius=18,
        )

        title = self.body_font.render("Canciones guardadas", True, TEXT_COLOR)
        helper = self.small_font.render(
            "Haz clic en una cancion para seleccionarla. La lista queda guardada entre sesiones.",
            True,
            MUTED_TEXT,
        )
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

        if not app.library.saved_songs:
            hint = self.body_font.render(
                "Aun no tienes canciones guardadas. Sube una para empezar.",
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

            pygame.draw.rect(self.screen, row_color, row_rect, border_radius=14)
            pygame.draw.rect(self.screen, CARD_BORDER, row_rect, width=1, border_radius=14)

            name_text = self.body_font.render(
                self.fit_text(song.name, self.body_font, row_rect.width - 180),
                True,
                TEXT_COLOR,
            )
            self.screen.blit(name_text, (row_rect.x + 14, row_rect.y + 8))

            state_label = "Disponible" if song_exists else "No encontrada"
            state_color = TEXT_COLOR if song_exists else MUTED_TEXT
            state_text = self.small_font.render(state_label, True, state_color)
            self.screen.blit(state_text, (row_rect.right - 120, row_rect.y + 10))

            path_text = self.small_font.render(
                self.fit_text(song.path, self.small_font, row_rect.width - 28),
                True,
                MUTED_TEXT,
            )
            self.screen.blit(path_text, (row_rect.x + 14, row_rect.y + 28))

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

        track_name = app.analysis_source.name if app.analysis_source else "Sin pista"
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
        color = BUTTON_COLOR if enabled else BUTTON_DISABLED
        if enabled and mouse_over:
            color = BUTTON_HOVER

        pygame.draw.rect(self.screen, color, rect, border_radius=12)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, width=2, border_radius=12)
        text_surface = button_font.render(label, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

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
        travel_start = LANE_TOP - 12
        travel_end = HIT_ZONE_Y - 24

        for note in app.analysis.notes:
            spawn_time = note.hit_time - LEAD_IN_SECONDS
            if song_time < spawn_time or song_time > note.hit_time + 0.2:
                continue

            progress = max(0.0, min(1.0, (song_time - spawn_time) / LEAD_IN_SECONDS))
            y_position = self.lerp(travel_start, travel_end, progress ** 0.92)
            self.draw_note_gem(notes_surface, note.lane, y_position, progress)

        self.screen.blit(notes_surface, (0, 0))

    def song_row_rect(self, row_offset: int) -> pygame.Rect:
        return pygame.Rect(
            self.library_panel.x + 20,
            self.library_panel.y + 64 + row_offset * 56,
            self.library_panel.width - 40,
            48,
        )

    def song_index_from_position(
        self,
        library: SongLibrary,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        for row_offset, song_index in enumerate(library.visible_song_indices()):
            if self.song_row_rect(row_offset).collidepoint(mouse_pos):
                return song_index

        return None

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
        center_y = HIT_ZONE_Y + 26
        center_x = self.lane_center_for_y(lane, center_y)
        points = [
            (center_x, center_y + 36),
            (center_x - 30, center_y + 8),
            (center_x - 22, center_y - 28),
            (center_x, center_y - 40),
            (center_x + 22, center_y - 28),
            (center_x + 30, center_y + 8),
        ]
        outer_glow = self.scale_polygon(points, 1.24, 1.18)
        inner_face = self.scale_polygon(points, 0.84, 0.84)
        highlight = [
            (center_x, center_y - 28),
            (center_x - 12, center_y + 6),
            (center_x, center_y + 24),
            (center_x + 12, center_y + 6),
        ]

        pygame.draw.polygon(surface, (*lane_color, 34), self.to_int_points(outer_glow))
        pygame.draw.polygon(surface, (20, 28, 50, 228), self.to_int_points(points))
        pygame.draw.polygon(surface, (*lane_color, 164), self.to_int_points(inner_face))
        pygame.draw.polygon(surface, (255, 255, 255, 210), self.to_int_points(inner_face), 2)
        pygame.draw.polygon(surface, (255, 255, 255, 72), self.to_int_points(highlight))
        pygame.draw.line(
            surface,
            (255, 255, 255, 110),
            (int(center_x), int(center_y - 28)),
            (int(center_x), int(center_y + 21)),
            2,
        )
        self.draw_lane_emblem(surface, lane, (int(center_x), int(center_y + 1)))

    def draw_note_gem(
        self,
        surface: pygame.Surface,
        lane: int,
        y_pos: float,
        progress: float,
    ) -> None:
        lane_color = LANE_COLORS[lane]
        center_x = self.lane_center_for_y(lane, y_pos)
        size = self.lerp(10.0, 22.0, progress ** 0.9)
        trail_start = (center_x, y_pos - size * 2.2)
        trail_end = (center_x, y_pos + size * 0.1)
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

    def build_visualizer_scene_surface(self) -> pygame.Surface:
        scene = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        dawn_top = (6, 24, 94)
        dawn_mid = (8, 58, 158)
        night_bottom = (6, 10, 26)

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

        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(overlay, (42, 128, 255, 76), (166, 92), 196)
        pygame.draw.circle(overlay, (255, 82, 201, 58), (WINDOW_WIDTH - 130, 104), 172)
        pygame.draw.circle(overlay, (255, 116, 92, 56), (WINDOW_WIDTH // 2 + 122, 216), 136)

        left_top, right_top = self.track_bounds_for_y(LANE_TOP + 10)
        left_bottom, right_bottom = self.track_bounds_for_y(HIT_ZONE_Y + 50)
        track_shadow = [
            (left_top, LANE_TOP + 10),
            (right_top, LANE_TOP + 10),
            (right_bottom, HIT_ZONE_Y + 50),
            (left_bottom, HIT_ZONE_Y + 50),
        ]
        pygame.draw.polygon(overlay, (6, 10, 34, 118), self.to_int_points(track_shadow))
        pygame.draw.polygon(overlay, (255, 255, 255, 22), self.to_int_points(track_shadow), 2)

        hill_points = [
            (self.lane_area.x + 90, HIT_ZONE_Y - 18),
            (self.lane_area.x + 210, HIT_ZONE_Y - 120),
            (self.lane_area.x + 340, HIT_ZONE_Y - 54),
            (self.lane_area.x + 500, HIT_ZONE_Y - 138),
            (self.lane_area.x + 700, HIT_ZONE_Y - 10),
            (self.lane_area.x + 90, HIT_ZONE_Y - 10),
        ]
        pygame.draw.polygon(overlay, (7, 18, 34, 165), hill_points)

        house_center_x = self.lane_area.centerx - 126
        house_base_y = HIT_ZONE_Y - 66
        house_body = pygame.Rect(house_center_x - 62, house_base_y - 54, 124, 54)
        pygame.draw.rect(overlay, (15, 20, 24, 225), house_body)
        roof_points = [
            (house_body.left - 16, house_body.top + 10),
            (house_center_x - 12, house_body.top - 48),
            (house_body.right + 20, house_body.top + 10),
            (house_body.right - 12, house_body.top + 18),
        ]
        pygame.draw.polygon(overlay, (11, 17, 19, 235), roof_points)
        window_rect = pygame.Rect(house_center_x + 12, house_base_y - 34, 22, 22)
        pygame.draw.rect(overlay, (255, 228, 148, 142), window_rect, border_radius=3)
        pygame.draw.rect(overlay, (255, 245, 199, 84), window_rect.inflate(8, 8), border_radius=5)
        for index in range(4):
            smoke_center = (
                house_center_x - 18 + index * 7,
                house_base_y - 78 - index * 18,
            )
            pygame.draw.circle(overlay, (220, 232, 255, 34 - index * 5), smoke_center, 9 - index)

        red_lane_x = self.lane_center_for_y(3, LANE_TOP)
        for index in range(4):
            ring_rect = pygame.Rect(0, 0, 54 - index * 6, 12)
            ring_rect.center = (int(red_lane_x + index * 3), LANE_TOP - 58 + index * 34)
            pygame.draw.ellipse(overlay, (255, 82, 92, 22), ring_rect.inflate(26, 18))
            pygame.draw.ellipse(overlay, (255, 90, 102, 188), ring_rect, 3)
            pygame.draw.ellipse(overlay, (255, 255, 255, 84), ring_rect.inflate(-18, -4), 1)

        beam_top_y = 0
        beam_bottom_y = HIT_ZONE_Y + 18
        for lane, lane_color in enumerate(LANE_COLORS):
            top_center_x = self.lane_center_for_y(lane, beam_top_y)
            bottom_center_x = self.lane_center_for_y(lane, beam_bottom_y)
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

        for particle_x, particle_y, radius, alpha in self.visualizer_particles:
            pygame.draw.circle(overlay, (255, 255, 255, alpha), (particle_x, particle_y), radius)

        floor_glow = pygame.Rect(self.lane_area.x + 110, HIT_ZONE_Y - 6, self.lane_area.width - 220, 86)
        pygame.draw.ellipse(overlay, (255, 255, 255, 18), floor_glow)
        pygame.draw.ellipse(overlay, (255, 110, 120, 16), floor_glow.inflate(160, 30))

        for lane in range(LANE_COUNT):
            self.draw_lane_receptor(overlay, lane)

        scene.blit(overlay, (0, 0))
        return scene
