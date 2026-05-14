from __future__ import annotations

from pathlib import Path
from typing import Iterable

import librosa
import numpy as np

from .constants import LANE_COUNT, MIN_NOTE_SPACING
from .models import NoteEvent, TrackAnalysis


class TrackBuilder:
    def build_chart(self, file_path: Path) -> TrackAnalysis:
        hop_length = 512
        audio, sample_rate = librosa.load(str(file_path), sr=22050, mono=True)
        if audio.size == 0:
            raise ValueError("El archivo no contiene audio utilizable.")

        harmonic_audio, percussive_audio = librosa.effects.hpss(audio)
        onset_envelope = librosa.onset.onset_strength(
            y=percussive_audio,
            sr=sample_rate,
            hop_length=hop_length,
        )
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            hop_length=hop_length,
        )

        melody_curve = self.extract_melody_curve(
            harmonic_audio=harmonic_audio,
            sample_rate=sample_rate,
            hop_length=hop_length,
        )
        normalized_tempo = float(np.asarray(tempo).reshape(-1)[0])
        if normalized_tempo <= 0:
            normalized_tempo = 120.0

        notes = self.build_piu_style_notes(
            audio=audio,
            harmonic_audio=harmonic_audio,
            sample_rate=sample_rate,
            hop_length=hop_length,
            tempo=normalized_tempo,
            beat_frames=beat_frames,
            onset_envelope=onset_envelope,
            melody_curve=melody_curve,
        )
        return TrackAnalysis(tempo=normalized_tempo, notes=notes)

    def build_piu_style_notes(
        self,
        audio: np.ndarray,
        harmonic_audio: np.ndarray,
        sample_rate: int,
        hop_length: int,
        tempo: float,
        beat_frames: np.ndarray,
        onset_envelope: np.ndarray,
        melody_curve: np.ndarray,
    ) -> list[NoteEvent]:
        duration = float(librosa.get_duration(y=audio, sr=sample_rate))
        beat_times = librosa.frames_to_time(
            np.asarray(beat_frames).reshape(-1),
            sr=sample_rate,
            hop_length=hop_length,
        )
        beat_interval = 60.0 / max(1.0, tempo)
        beat_offset = float(beat_times[0]) if beat_times.size else 0.0
        if beat_times.size < 4:
            beat_times = np.arange(beat_offset, duration + beat_interval, beat_interval)

        grid_times = self.build_quantized_grid(
            beat_offset=beat_offset,
            duration=duration,
            beat_interval=beat_interval,
        )
        if grid_times.size == 0:
            return []

        rms = librosa.feature.rms(y=audio, hop_length=hop_length)[0]
        harmonic_rms = librosa.feature.rms(y=harmonic_audio, hop_length=hop_length)[0]
        energy = self.grid_energy(
            grid_times=grid_times,
            onset_envelope=onset_envelope,
            rms=rms,
            sample_rate=sample_rate,
            hop_length=hop_length,
        )
        harmonic_energy = self.grid_energy(
            grid_times=grid_times,
            onset_envelope=harmonic_rms,
            rms=harmonic_rms,
            sample_rate=sample_rate,
            hop_length=hop_length,
        )
        accents = self.detect_grid_accents(energy)
        phrase_energy = self.smooth_grid_energy(energy, window_size=16)
        low, mid, high = self.energy_thresholds(phrase_energy)

        pitch_floor, pitch_ceiling = self.melody_range(melody_curve)
        pattern_cursor = 0
        last_lane: int | None = None
        last_time_by_lane = [-999.0 for _ in range(LANE_COUNT)]
        occupied: set[tuple[int, int]] = set()
        notes: list[NoteEvent] = []

        for index, hit_time in enumerate(grid_times):
            beat_fraction = index % 4
            beat_in_measure = (index // 4) % 4
            measure_index = index // 16
            current_energy = phrase_energy[index]
            has_accent = accents[index]

            if not self.should_place_step(
                beat_fraction=beat_fraction,
                beat_in_measure=beat_in_measure,
                measure_index=measure_index,
                current_energy=current_energy,
                has_accent=has_accent,
                low=low,
                mid=mid,
                high=high,
            ):
                continue

            melodic_lane = self.melody_lane_for_time(
                hit_time=hit_time,
                melody_curve=melody_curve,
                sample_rate=sample_rate,
                hop_length=hop_length,
                pitch_floor=pitch_floor,
                pitch_ceiling=pitch_ceiling,
            )
            lanes = self.pattern_lanes(
                pattern_cursor=pattern_cursor,
                melodic_lane=melodic_lane,
                last_lane=last_lane,
                strong_step=beat_fraction == 0,
            )
            pattern_cursor += 1

            if self.should_place_jump(
                beat_fraction=beat_fraction,
                beat_in_measure=beat_in_measure,
                measure_index=measure_index,
                current_energy=current_energy,
                has_accent=has_accent,
                high=high,
            ):
                lanes = self.jump_lanes(pattern_cursor, melodic_lane)

            added_lanes = self.add_step_notes(
                notes=notes,
                lanes=lanes,
                hit_time=float(hit_time),
                duration=0.0,
                last_time_by_lane=last_time_by_lane,
                occupied=occupied,
            )
            if added_lanes:
                last_lane = added_lanes[-1]

        return sorted(notes, key=lambda note: (note.hit_time, note.lane))

    def build_quantized_grid(
        self,
        beat_offset: float,
        duration: float,
        beat_interval: float,
    ) -> np.ndarray:
        step_interval = beat_interval / 4.0
        if step_interval <= 0:
            return np.array([], dtype=float)

        start_time = beat_offset
        while start_time - step_interval >= 0.0:
            start_time -= step_interval

        return np.arange(start_time, duration + step_interval, step_interval, dtype=float)

    def grid_energy(
        self,
        grid_times: np.ndarray,
        onset_envelope: np.ndarray,
        rms: np.ndarray,
        sample_rate: int,
        hop_length: int,
    ) -> np.ndarray:
        onset = self.normalize_curve(onset_envelope)
        volume = self.normalize_curve(rms)
        frame_seconds = hop_length / sample_rate
        values: list[float] = []

        for hit_time in grid_times:
            frame = max(0, int(round(hit_time / frame_seconds)))
            onset_value = self.local_curve_value(onset, frame, radius=1)
            volume_value = self.local_curve_value(volume, frame, radius=2)
            values.append((onset_value * 0.68) + (volume_value * 0.32))

        return np.asarray(values, dtype=float)

    def detect_grid_accents(self, energy: np.ndarray) -> np.ndarray:
        if energy.size == 0:
            return np.array([], dtype=bool)

        floor = max(float(np.percentile(energy, 62)), 0.12)
        accents = np.zeros(energy.size, dtype=bool)
        for index, value in enumerate(energy):
            start = max(0, index - 1)
            stop = min(energy.size, index + 2)
            accents[index] = value >= floor and value >= float(np.max(energy[start:stop]))
        return accents

    def smooth_grid_energy(self, energy: np.ndarray, window_size: int) -> np.ndarray:
        if energy.size == 0:
            return energy

        window_size = max(1, min(window_size, energy.size))
        kernel = np.ones(window_size, dtype=float) / window_size
        return np.convolve(energy, kernel, mode="same")

    def energy_thresholds(self, energy: np.ndarray) -> tuple[float, float, float]:
        if energy.size == 0:
            return 0.0, 0.0, 0.0

        return (
            float(np.percentile(energy, 30)),
            float(np.percentile(energy, 58)),
            float(np.percentile(energy, 78)),
        )

    def should_place_step(
        self,
        beat_fraction: int,
        beat_in_measure: int,
        measure_index: int,
        current_energy: float,
        has_accent: bool,
        low: float,
        mid: float,
        high: float,
    ) -> bool:
        if current_energy < low * 0.82 and not has_accent:
            return False

        if beat_fraction == 0:
            return current_energy >= low or beat_in_measure in {0, 2}

        if beat_fraction == 2:
            return has_accent or current_energy >= mid or (measure_index + beat_in_measure) % 3 == 0

        if current_energy >= high and has_accent:
            return True

        return current_energy >= high * 1.04 and (measure_index + beat_in_measure + beat_fraction) % 4 == 0

    def pattern_lanes(
        self,
        pattern_cursor: int,
        melodic_lane: int | None,
        last_lane: int | None,
        strong_step: bool,
    ) -> list[int]:
        patterns = [
            [0, 4, 1, 3],
            [1, 2, 3, 2],
            [0, 2, 4, 2],
            [3, 1, 4, 0],
            [2, 0, 3, 1],
            [4, 2, 1, 2],
        ]
        pattern = patterns[(pattern_cursor // 4) % len(patterns)]
        lane = pattern[pattern_cursor % len(pattern)]

        if melodic_lane is not None:
            if strong_step:
                lane = melodic_lane
            else:
                lane = int(round((lane + melodic_lane) / 2))

        if last_lane is not None and lane == last_lane:
            lane = (lane + 2) % LANE_COUNT

        return [max(0, min(LANE_COUNT - 1, lane))]

    def should_place_jump(
        self,
        beat_fraction: int,
        beat_in_measure: int,
        measure_index: int,
        current_energy: float,
        has_accent: bool,
        high: float,
    ) -> bool:
        if beat_fraction != 0 or current_energy < high:
            return False

        return has_accent or (beat_in_measure in {0, 2} and measure_index % 2 == 1)

    def jump_lanes(self, pattern_cursor: int, melodic_lane: int | None) -> list[int]:
        jump_pairs = [(0, 4), (1, 3), (0, 3), (1, 4), (2, 4), (0, 2)]
        if melodic_lane is None:
            return list(jump_pairs[pattern_cursor % len(jump_pairs)])

        candidates = [pair for pair in jump_pairs if melodic_lane in pair]
        if candidates:
            return list(candidates[pattern_cursor % len(candidates)])
        return list(jump_pairs[pattern_cursor % len(jump_pairs)])

    def hold_duration_for_step(
        self,
        index: int,
        beat_fraction: int,
        beat_interval: float,
        phrase_energy: np.ndarray,
        harmonic_energy: np.ndarray,
        high: float,
    ) -> float:
        if beat_fraction != 0 or index + 8 >= harmonic_energy.size:
            return 0.0

        harmonic_slice = harmonic_energy[index : index + 8]
        phrase_slice = phrase_energy[index : index + 8]
        if float(np.mean(harmonic_slice)) < 0.48 or float(np.max(phrase_slice)) >= high * 1.08:
            return 0.0

        return round(beat_interval * (2.0 if float(np.mean(harmonic_slice)) > 0.68 else 1.0), 3)

    def add_step_notes(
        self,
        notes: list[NoteEvent],
        lanes: Iterable[int],
        hit_time: float,
        duration: float,
        last_time_by_lane: list[float],
        occupied: set[tuple[int, int]],
    ) -> list[int]:
        added_lanes: list[int] = []
        time_key = int(round(hit_time * 1000))

        for lane in lanes:
            if lane < 0 or lane >= LANE_COUNT:
                continue
            if (time_key, lane) in occupied:
                continue
            if hit_time - last_time_by_lane[lane] < 0.07:
                continue

            notes.append(NoteEvent(lane=lane, hit_time=hit_time, duration=duration))
            occupied.add((time_key, lane))
            last_time_by_lane[lane] = hit_time
            added_lanes.append(lane)

        return added_lanes

    def normalize_curve(self, curve: np.ndarray) -> np.ndarray:
        if curve.size == 0:
            return np.array([], dtype=float)

        curve = np.asarray(curve, dtype=float)
        ceiling = float(np.percentile(curve, 95))
        if ceiling <= 0.0:
            return np.zeros(curve.size, dtype=float)
        return np.clip(curve / ceiling, 0.0, 1.0)

    def local_curve_value(self, curve: np.ndarray, frame: int, radius: int) -> float:
        if curve.size == 0:
            return 0.0

        frame = max(0, min(curve.size - 1, frame))
        start = max(0, frame - radius)
        stop = min(curve.size, frame + radius + 1)
        return float(np.max(curve[start:stop]))

    def melody_lane_for_time(
        self,
        hit_time: float,
        melody_curve: np.ndarray,
        sample_rate: int,
        hop_length: int,
        pitch_floor: float,
        pitch_ceiling: float,
    ) -> int | None:
        frame = int(round(hit_time / (hop_length / sample_rate)))
        return self.melody_lane_for_frame(
            frame=frame,
            melody_curve=melody_curve,
            pitch_floor=pitch_floor,
            pitch_ceiling=pitch_ceiling,
        )

    def extract_melody_curve(
        self,
        harmonic_audio: np.ndarray,
        sample_rate: int,
        hop_length: int,
    ) -> np.ndarray:
        dominant_curve = self.extract_dominant_pitch_curve(
            harmonic_audio=harmonic_audio,
            sample_rate=sample_rate,
            hop_length=hop_length,
        )
        valid_ratio = np.count_nonzero(np.isfinite(dominant_curve)) / max(1, dominant_curve.size)
        if valid_ratio >= 0.35:
            return dominant_curve

        try:
            f0, voiced_flag, _ = librosa.pyin(
                harmonic_audio,
                sr=sample_rate,
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
                hop_length=hop_length,
            )
        except Exception:
            return dominant_curve

        melody_size = max(dominant_curve.size, f0.size)
        melody_curve = np.full(melody_size, np.nan, dtype=float)
        if dominant_curve.size:
            melody_curve[: dominant_curve.size] = dominant_curve

        if not f0.size:
            return melody_curve

        midi_values = librosa.hz_to_midi(f0)
        refined_curve = np.where(voiced_flag, midi_values, np.nan)
        voiced_pitch = np.isfinite(refined_curve)
        melody_slice = melody_curve[: f0.size]
        melody_slice[voiced_pitch] = refined_curve[voiced_pitch]
        return melody_curve

    def build_melody_event_frames(
        self,
        melody_curve: np.ndarray,
        onset_envelope: np.ndarray,
        beat_frames: np.ndarray,
        sample_rate: int,
        hop_length: int,
    ) -> np.ndarray:
        if melody_curve.size == 0:
            return np.array([], dtype=int)

        finite_pitch = np.isfinite(melody_curve)
        if np.count_nonzero(finite_pitch) < 8:
            return np.array([], dtype=int)

        smoothed_curve = self.smooth_melody_curve(melody_curve)
        pitch_floor, pitch_ceiling = self.melody_range(smoothed_curve)
        if pitch_ceiling <= pitch_floor:
            return np.array([], dtype=int)

        frame_seconds = hop_length / sample_rate
        min_gap_frames = max(1, int(round(MIN_NOTE_SPACING / frame_seconds)))
        sustain_gap_frames = max(min_gap_frames + 1, int(round(0.42 / frame_seconds)))
        max_onset_strength = float(np.max(onset_envelope)) if onset_envelope.size else 0.0
        accent_floor = max_onset_strength * 0.28

        events: list[int] = []
        beat_frame_set = {int(frame) for frame in np.asarray(beat_frames).reshape(-1)}
        previous_frame = -999_999
        previous_lane: int | None = None
        last_sustain_frame = -999_999

        for frame, pitch_value in enumerate(smoothed_curve):
            if not np.isfinite(pitch_value):
                continue

            lane = self.lane_for_pitch(
                pitch_value=float(pitch_value),
                pitch_floor=pitch_floor,
                pitch_ceiling=pitch_ceiling,
            )
            has_lane_change = previous_lane is not None and lane != previous_lane
            has_accent = self.is_local_onset_peak(frame, onset_envelope, accent_floor)
            is_main_beat = self.is_near_main_beat(frame, beat_frame_set)
            needs_sustain = frame - last_sustain_frame >= sustain_gap_frames

            should_add = (
                previous_lane is None
                or has_lane_change
                or has_accent
                or is_main_beat
                or needs_sustain
            )
            if should_add and frame - previous_frame >= min_gap_frames:
                events.append(frame)
                previous_frame = frame
                last_sustain_frame = frame

            previous_lane = lane

        return np.asarray(events, dtype=int)

    def is_near_main_beat(self, frame: int, beat_frame_set: set[int]) -> bool:
        return any((frame + offset) in beat_frame_set for offset in range(-1, 2))

    def smooth_melody_curve(self, melody_curve: np.ndarray) -> np.ndarray:
        finite_pitch = np.isfinite(melody_curve)
        if np.count_nonzero(finite_pitch) < 2:
            return melody_curve

        frame_indices = np.arange(melody_curve.size)
        interpolated = np.interp(
            frame_indices,
            frame_indices[finite_pitch],
            melody_curve[finite_pitch],
        )
        window_size = 5
        kernel = np.ones(window_size, dtype=float) / window_size
        smoothed = np.convolve(interpolated, kernel, mode="same")
        smoothed[~finite_pitch] = np.nan
        return smoothed

    def is_local_onset_peak(
        self,
        frame: int,
        onset_envelope: np.ndarray,
        accent_floor: float,
    ) -> bool:
        if onset_envelope.size == 0 or accent_floor <= 0.0:
            return False

        strength_index = min(frame, onset_envelope.size - 1)
        strength = float(onset_envelope[strength_index])
        if strength < accent_floor:
            return False

        start = max(0, strength_index - 1)
        stop = min(onset_envelope.size, strength_index + 2)
        return strength >= float(np.max(onset_envelope[start:stop]))

    def extract_dominant_pitch_curve(
        self,
        harmonic_audio: np.ndarray,
        sample_rate: int,
        hop_length: int,
    ) -> np.ndarray:
        pitches, magnitudes = librosa.piptrack(
            y=harmonic_audio,
            sr=sample_rate,
            hop_length=hop_length,
        )

        if not magnitudes.size:
            return np.array([], dtype=float)

        peak_indices = np.argmax(magnitudes, axis=0)
        frame_indices = np.arange(magnitudes.shape[1])
        peak_magnitudes = magnitudes[peak_indices, frame_indices]
        peak_pitches = pitches[peak_indices, frame_indices]

        magnitude_floor = float(np.max(peak_magnitudes)) * 0.12
        valid_pitch = (peak_pitches > 0.0) & (peak_magnitudes >= magnitude_floor)
        dominant_curve = np.full(peak_pitches.shape, np.nan, dtype=float)
        dominant_curve[valid_pitch] = librosa.hz_to_midi(peak_pitches[valid_pitch])
        return dominant_curve

    def assign_lanes(
        self,
        event_frames: np.ndarray,
        event_times: np.ndarray,
        melody_curve: np.ndarray,
    ) -> list[NoteEvent]:
        pitch_floor, pitch_ceiling = self.melody_range(melody_curve)

        notes: list[NoteEvent] = []
        previous_time = -999.0

        for frame, event_time in zip(event_frames, event_times):
            hit_time = float(event_time)
            if hit_time - previous_time < MIN_NOTE_SPACING:
                continue

            lane = self.melody_lane_for_frame(
                frame=int(frame),
                melody_curve=melody_curve,
                pitch_floor=pitch_floor,
                pitch_ceiling=pitch_ceiling,
            )
            if lane is None:
                continue

            notes.append(NoteEvent(lane=lane, hit_time=hit_time))
            previous_time = hit_time

        return notes

    def melody_range(self, melody_curve: np.ndarray) -> tuple[float, float]:
        valid_pitches = melody_curve[np.isfinite(melody_curve)]
        if valid_pitches.size == 0:
            return 0.0, 0.0

        if valid_pitches.size < 4:
            return float(np.min(valid_pitches)), float(np.max(valid_pitches))

        pitch_floor = float(np.percentile(valid_pitches, 10))
        pitch_ceiling = float(np.percentile(valid_pitches, 90))
        if pitch_ceiling <= pitch_floor:
            pitch_floor = float(np.min(valid_pitches))
            pitch_ceiling = float(np.max(valid_pitches))
        return pitch_floor, pitch_ceiling

    def melody_lane_for_frame(
        self,
        frame: int,
        melody_curve: np.ndarray,
        pitch_floor: float,
        pitch_ceiling: float,
    ) -> int | None:
        if melody_curve.size == 0:
            return None

        start = max(0, frame - 2)
        stop = min(melody_curve.size, frame + 3)
        local_pitches = melody_curve[start:stop]
        valid_pitches = local_pitches[np.isfinite(local_pitches)]
        if valid_pitches.size == 0:
            return None

        pitch_value = float(np.median(valid_pitches))
        if pitch_ceiling <= pitch_floor:
            return LANE_COUNT // 2

        normalized = (pitch_value - pitch_floor) / (pitch_ceiling - pitch_floor)
        return self.lane_for_normalized_pitch(normalized)

    def lane_for_pitch(
        self,
        pitch_value: float,
        pitch_floor: float,
        pitch_ceiling: float,
    ) -> int:
        if pitch_ceiling <= pitch_floor:
            return LANE_COUNT // 2

        normalized = (pitch_value - pitch_floor) / (pitch_ceiling - pitch_floor)
        return self.lane_for_normalized_pitch(normalized)

    def lane_for_normalized_pitch(self, normalized: float) -> int:
        normalized = float(np.clip(normalized, 0.0, 1.0))
        lane = int(np.rint(normalized * (LANE_COUNT - 1)))
        return min(LANE_COUNT - 1, max(0, lane))
