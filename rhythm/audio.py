from __future__ import annotations

from pathlib import Path

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

        harmonic_audio, _ = librosa.effects.hpss(audio)
        onset_envelope = librosa.onset.onset_strength(
            y=harmonic_audio,
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
        melody_frames = self.build_melody_event_frames(
            melody_curve=melody_curve,
            onset_envelope=onset_envelope,
            beat_frames=beat_frames,
            sample_rate=sample_rate,
            hop_length=hop_length,
        )
        if melody_frames.size < 8:
            raise ValueError("No se detecto melodia suficiente para construir la pista.")

        event_times = librosa.frames_to_time(
            melody_frames,
            sr=sample_rate,
            hop_length=hop_length,
        )
        notes = self.assign_lanes(
            event_frames=melody_frames,
            event_times=event_times,
            melody_curve=melody_curve,
        )
        normalized_tempo = float(np.asarray(tempo).reshape(-1)[0])
        return TrackAnalysis(tempo=normalized_tempo, notes=notes)

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
