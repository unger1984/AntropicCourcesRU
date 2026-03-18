#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


def parse_timestamp(value: str) -> int:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return (
        int(hh) * 3600 * 1000
        + int(mm) * 60 * 1000
        + int(ss) * 1000
        + int(ms)
    )


def parse_srt(path: Path) -> List[Cue]:
    content = path.read_text(encoding="utf-8").replace("\r", "")
    blocks = [block.strip() for block in content.split("\n\n") if block.strip()]
    cues: List[Cue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        index = int(lines[0])
        start_raw, end_raw = lines[1].split(" --> ")
        text = " ".join(lines[2:])
        cues.append(
            Cue(
                index=index,
                start_ms=parse_timestamp(start_raw),
                end_ms=parse_timestamp(end_raw),
                text=text,
            )
        )
    return cues


def run(cmd: Iterable[str]) -> None:
    subprocess.run(list(cmd), check=True)


def probe_duration_seconds(path: Path) -> float:
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(output)


def atempo_chain(speed: float) -> str:
    if speed <= 0:
        raise ValueError("speed must be > 0")
    parts: List[str] = []
    remaining = speed
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def synthesize_segments(cues: List[Cue], voice: str, workdir: Path) -> List[Path]:
    adjusted_segments: List[Path] = []
    for cue in cues:
        raw_aiff = workdir / f"{cue.index:04d}.aiff"
        adjusted_wav = workdir / f"{cue.index:04d}_adj.wav"
        run(["say", "-v", voice, "-o", str(raw_aiff), cue.text])
        raw_duration_ms = probe_duration_seconds(raw_aiff) * 1000
        if raw_duration_ms > cue.duration_ms and cue.duration_ms > 0:
            speed = raw_duration_ms / cue.duration_ms
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw_aiff),
                    "-filter:a",
                    atempo_chain(speed),
                    str(adjusted_wav),
                ]
            )
        else:
            run(["ffmpeg", "-y", "-i", str(raw_aiff), str(adjusted_wav)])
        adjusted_segments.append(adjusted_wav)
    return adjusted_segments


def build_filter_complex(cues: List[Cue], segments: List[Path]) -> str:
    lines: List[str] = []
    mix_inputs: List[str] = []
    for idx, cue in enumerate(cues):
        delay = cue.start_ms
        lines.append(
            f"[{idx}:a]adelay={delay}|{delay},volume=1[seg{idx}]"
        )
        mix_inputs.append(f"[seg{idx}]")
    lines.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0[outa]")
    return ";".join(lines)


def build_dub(srt_path: Path, video_path: Path, out_audio: Path, out_video: Path, voice: str) -> None:
    cues = parse_srt(srt_path)
    if not cues:
        raise SystemExit(f"No cues found in {srt_path}")
    out_audio.parent.mkdir(parents=True, exist_ok=True)
    out_video.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ru_dub_") as tmp:
        workdir = Path(tmp)
        segments = synthesize_segments(cues, voice, workdir)
        filter_complex = build_filter_complex(cues, segments)

        audio_cmd = ["ffmpeg", "-y"]
        for segment in segments:
            audio_cmd.extend(["-i", str(segment)])
        audio_cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[outa]",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out_audio),
            ]
        )
        run(audio_cmd)

        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(out_audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(out_video),
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Russian dubbed lesson media from an SRT file.")
    parser.add_argument("--srt", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--out-audio", required=True, type=Path)
    parser.add_argument("--out-video", required=True, type=Path)
    parser.add_argument("--voice", default="Milena")
    args = parser.parse_args()
    build_dub(args.srt, args.video, args.out_audio, args.out_video, args.voice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
