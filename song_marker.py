#!/usr/bin/env python3
"""Mark likely singing segments in Bilibili recordings.

This is a heuristic baseline: it extracts audio features that tend to differ
between speech and singing, smooths the frame-level scores, and emits merged
time ranges. It is designed for fast rough annotation, not perfect MIR.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

np = None


@dataclass
class Segment:
    start: float
    end: float
    confidence: float
    loudness_lift: float = 0.0
    voice_presence: float = 0.0
    pitch_stability: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(
            f"Missing required command: {name}. Install it first, for example `brew install {name}`."
        )


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def download_audio(
    url: str,
    output_dir: Path,
    video_id: str,
    format_selector: str,
    retries: int,
    http_chunk_size: str | None,
    downloader: str | None,
    downloader_args: str | None,
) -> Path:
    require_command("yt-dlp")
    target = output_dir / f"{video_id}.%(ext)s"
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--retries",
        str(retries),
        "--fragment-retries",
        "infinite",
        "-f",
        format_selector,
        "-o",
        str(target),
        url,
    ]
    if downloader:
        cmd[1:1] = ["--downloader", downloader]
    if downloader_args:
        cmd[1:1] = ["--downloader-args", downloader_args]
    if http_chunk_size:
        cmd[1:1] = ["--http-chunk-size", http_chunk_size]
    run(cmd)
    matches = sorted(path for path in output_dir.glob(f"{video_id}.*") if not path.name.endswith(".part") and path.suffix not in (".wav", ".part", ".ytdl"))
    if not matches:
        raise RuntimeError("yt-dlp finished but no source audio/video file was found.")
    return matches[0]


def convert_to_wav(source: Path, wav_path: Path) -> None:
    require_command("ffmpeg")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav_path),
        ]
    )


def robust_scale(values: np.ndarray) -> np.ndarray:
    median = np.nanmedian(values)
    q1, q3 = np.nanpercentile(values, [25, 75])
    iqr = max(q3 - q1, 1e-6)
    return (values - median) / iqr


def moving_average(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values
    kernel = np.ones(width) / width
    return np.convolve(values, kernel, mode="same")


def detect_segments(
    wav_path: Path,
    threshold: float,
    min_duration: float,
    merge_gap: float,
    min_loudness_lift: float = 0.35,
) -> list[Segment]:
    global np
    try:
        import librosa
        import numpy
    except ImportError as exc:
        raise RuntimeError(
            "Missing Python audio dependencies. Run `python -m pip install -r requirements.txt`."
        ) from exc
    np = numpy

    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    hop_length = int(sr * 1.0)
    frame_length = int(sr * 2.0)

    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=frame_length, hop_length=hop_length)[0]
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr, hop_length=hop_length)[0]
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]
    stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    total_band = stft[(freqs >= 80) & (freqs <= 6000), :].sum(axis=0)
    vocal_band = stft[(freqs >= 180) & (freqs <= 3500), :].sum(axis=0)
    voice_presence = vocal_band / np.maximum(total_band, 1e-9)

    rms_db = librosa.amplitude_to_db(rms, ref=1.0)
    local_background = np.array(
        [
            np.nanpercentile(rms_db[max(0, i - 60) : min(len(rms_db), i + 61)], 25)
            for i in range(len(rms_db))
        ]
    )
    loudness_lift = np.clip((rms_db - local_background) / 12.0, 0.0, 1.5)

    pitches, magnitudes = librosa.piptrack(y=y, sr=sr, hop_length=hop_length, fmin=80, fmax=1000)
    voiced_pitch = []
    voiced_strength = []
    for frame in range(pitches.shape[1]):
        mag = magnitudes[:, frame]
        if mag.max() <= 0:
            voiced_pitch.append(np.nan)
            voiced_strength.append(0.0)
            continue
        idx = int(mag.argmax())
        voiced_pitch.append(float(pitches[idx, frame]))
        voiced_strength.append(float(mag[idx]))

    pitch = np.array(voiced_pitch)
    strength = np.array(voiced_strength)
    valid_pitch = np.isfinite(pitch) & (pitch > 0)

    pitch_stability = np.zeros_like(strength)
    for i in range(len(pitch)):
        lo = max(0, i - 4)
        hi = min(len(pitch), i + 5)
        window = pitch[lo:hi]
        window = window[np.isfinite(window) & (window > 0)]
        if len(window) >= 3:
            pitch_stability[i] = 1.0 / (1.0 + np.std(np.log2(window)))

    musical_energy = (
        0.25 * robust_scale(loudness_lift)
        + 0.25 * robust_scale(strength)
        + 0.20 * robust_scale(pitch_stability)
        + 0.15 * robust_scale(voice_presence)
        + 0.05 * robust_scale(bandwidth)
        - 0.10 * robust_scale(zcr)
        - 0.05 * robust_scale(flatness)
    )
    score = 1.0 / (1.0 + np.exp(-musical_energy))
    score = moving_average(score, width=9)
    score = np.where(valid_pitch, score, score * 0.5)
    score = np.where(loudness_lift >= 0.15, score, score * 0.65)

    active = score >= threshold
    raw: list[Segment] = []
    start = None
    for i, is_active in enumerate(active):
        if is_active and start is None:
            start = i
        if start is not None and (not is_active or i == len(active) - 1):
            end_idx = i if not is_active else i + 1
            conf = float(np.mean(score[start:end_idx]))
            raw.append(
                Segment(
                    float(start),
                    float(end_idx),
                    conf,
                    float(np.mean(loudness_lift[start:end_idx])),
                    float(np.mean(voice_presence[start:end_idx])),
                    float(np.mean(pitch_stability[start:end_idx])),
                )
            )
            start = None

    merged: list[Segment] = []
    for seg in raw:
        if not merged or seg.start - merged[-1].end > merge_gap:
            merged.append(seg)
        else:
            prev = merged[-1]
            total = prev.duration + seg.duration
            confidence = (prev.confidence * prev.duration + seg.confidence * seg.duration) / max(total, 1e-6)
            loudness = (prev.loudness_lift * prev.duration + seg.loudness_lift * seg.duration) / max(total, 1e-6)
            voice = (prev.voice_presence * prev.duration + seg.voice_presence * seg.duration) / max(total, 1e-6)
            pitch = (prev.pitch_stability * prev.duration + seg.pitch_stability * seg.duration) / max(total, 1e-6)
            merged[-1] = Segment(prev.start, seg.end, confidence, loudness, voice, pitch)

    return [
        seg
        for seg in merged
        if seg.duration >= min_duration and seg.loudness_lift >= min_loudness_lift
    ]


def fmt_time(seconds: float) -> str:
    seconds = int(round(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def write_markdown(segments: list[Segment], out_path: Path) -> None:
    lines = [
        "| start | end | duration | confidence | loudness_lift | voice_presence | pitch_stability |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for seg in segments:
        lines.append(
            f"| {fmt_time(seg.start)} | {fmt_time(seg.end)} | {fmt_time(seg.duration)} | {seg.confidence:.2f} | {seg.loudness_lift:.2f} | {seg.voice_presence:.2f} | {seg.pitch_stability:.2f} |"
        )
    if not segments:
        lines.append("| - | - | - | - | - | - | - |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect likely singing timestamps in a recording.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Bilibili recording URL.")
    source.add_argument("--audio", type=Path, help="Existing audio/video file to analyze.")
    parser.add_argument("--out", type=Path, default=Path("outputs/segments.md"))
    parser.add_argument("--threshold", type=float, default=0.56)
    parser.add_argument("--min-duration", type=float, default=45.0)
    parser.add_argument("--merge-gap", type=float, default=20.0)
    parser.add_argument(
        "--min-loudness-lift",
        type=float,
        default=0.35,
        help="Minimum average loudness lift of a singing segment.",
    )
    parser.add_argument(
        "--download-format",
        default="worstaudio",
        help="yt-dlp format selector. Defaults to 'worstaudio' for minimum bandwidth.",
    )
    parser.add_argument("--download-retries", type=int, default=20)
    parser.add_argument("--http-chunk-size", default=None, help="Optional yt-dlp HTTP chunk size, for example 512K.")
    parser.add_argument("--downloader", default=None, help="Optional yt-dlp external downloader, for example aria2c.")
    parser.add_argument("--downloader-args", default=None, help="Optional args passed to the external downloader.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        work_dir = Path("work")
        work_dir.mkdir(exist_ok=True)
        source = None
        if args.url:
            import re
            match = re.search(r'(BV[a-zA-Z0-9]+|av[0-9]+)', args.url)
            video_id = match.group(1) if match else "downloaded_audio"
            existing_files = sorted(work_dir.glob(f"{video_id}.*"))
            existing_files = [f for f in existing_files if f.suffix not in (".wav", ".part", ".ytdl")]
            if existing_files:
                source = existing_files[0]
                print(f"Found cached recording: {source}, reusing it!")
            else:
                print(f"Downloading stream {video_id} (using worst audio for minimal bandwidth)...")
                source = download_audio(
                    args.url,
                    work_dir,
                    video_id,
                    args.download_format,
                    args.download_retries,
                    args.http_chunk_size,
                    args.downloader,
                    args.downloader_args,
                )
        else:
            source = args.audio

        if source is None or not source.exists():
            raise RuntimeError(f"Input file does not exist: {source}")

        with tempfile.TemporaryDirectory(prefix="song-marker-") as tmp:
            tmp_path = Path(tmp)
            wav_path = tmp_path / "audio.wav"
            convert_to_wav(source, wav_path)
            segments = detect_segments(
                wav_path,
                args.threshold,
                args.min_duration,
                args.merge_gap,
                args.min_loudness_lift,
            )
            write_markdown(segments, args.out)
            print(f"Wrote {len(segments)} segment(s) to {args.out}")
            return 0
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
