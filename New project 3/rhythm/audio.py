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

        onset_envelope = librosa.onset.onset_strength(
            y=audio,
            sr=sample_rate,
            hop_length=hop_length,
        )
        tempo, _ = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            hop_length=hop_length,
        )
        event_frames = np.asarray(
            librosa.onset.onset_detect(
                onset_envelope=onset_envelope,
                sr=sample_rate,
                hop_length=hop_length,
                backtrack=False,
            ),
            dtype=int,
        )

        if event_frames.size == 0:
            raise ValueError("No se detectaron onsets utiles para construir la pista.")

        event_times = librosa.frames_to_time(
            event_frames,
            sr=sample_rate,
            hop_length=hop_length,
        )
        melody_curve = self.extract_melody_curve(
            audio=audio,
            sample_rate=sample_rate,
            hop_length=hop_length,
        )
        notes = self.assign_lanes(
            event_frames=event_frames,
            event_times=event_times,
            onset_envelope=onset_envelope,
            melody_curve=melody_curve,
        )
        normalized_tempo = float(np.asarray(tempo).reshape(-1)[0])
        return TrackAnalysis(tempo=normalized_tempo, notes=notes)

    def extract_melody_curve(
        self,
        audio: np.ndarray,
        sample_rate: int,
        hop_length: int,
    ) -> np.ndarray:
        harmonic_audio, _ = librosa.effects.hpss(audio)
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
        melody_curve[: f0.size][voiced_pitch] = refined_curve[voiced_pitch]
        return melody_curve

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
        onset_envelope: np.ndarray,
        melody_curve: np.ndarray,
    ) -> list[NoteEvent]:
        max_strength = float(np.max(onset_envelope)) if onset_envelope.size else 1.0
        pitch_floor, pitch_ceiling = self.melody_range(melody_curve)

        notes: list[NoteEvent] = []
        previous_melodic_lane: int | None = None
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
            if lane is None and previous_melodic_lane is not None:
                lane = previous_melodic_lane

            if lane is None:
                lane = self.intensity_lane_for_frame(
                    frame=int(frame),
                    onset_envelope=onset_envelope,
                    max_strength=max_strength,
                )
            else:
                previous_melodic_lane = lane

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
        normalized = float(np.clip(normalized, 0.0, 1.0))
        lane = int(np.rint(normalized * (LANE_COUNT - 1)))
        return min(LANE_COUNT - 1, max(0, lane))

    def intensity_lane_for_frame(
        self,
        frame: int,
        onset_envelope: np.ndarray,
        max_strength: float,
    ) -> int:
        if not onset_envelope.size or max_strength <= 0.0:
            return LANE_COUNT // 2

        strength_index = min(frame, onset_envelope.size - 1)
        strength = float(onset_envelope[strength_index])
        normalized = float(np.clip(strength / max_strength, 0.0, 1.0))
        return min(LANE_COUNT - 1, int(normalized * LANE_COUNT))
