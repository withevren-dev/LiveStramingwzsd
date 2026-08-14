"""ffmpeg / ffprobe 래퍼."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from .timeline import Timeline


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise RuntimeError(
            f"'{binary}' 를 찾을 수 없습니다. ffmpeg를 설치하세요 "
            "(예: apt-get install ffmpeg / brew install ffmpeg)."
        )
    return path


def probe_duration(path: str) -> float:
    """영상 길이(초)."""
    ffprobe = _require("ffprobe")
    out = subprocess.check_output(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            path,
        ]
    )
    return float(json.loads(out)["format"]["duration"])


def extract_audio(path: str, out_wav: str, sample_rate: int = 16000) -> str:
    """영상에서 모노 16kHz WAV 오디오 추출 (분석/STT 공용)."""
    ffmpeg = _require("ffmpeg")
    subprocess.run(
        [
            ffmpeg, "-y", "-i", path,
            "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-f", "wav", out_wav,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_wav


def render_timeline(
    src: str,
    timeline: Timeline,
    out_path: str,
    *,
    reencode: bool = True,
    crf: int = 20,
    preset: str = "medium",
) -> str:
    """유지 구간들을 잘라 이어붙여 최종 영상을 만든다.

    reencode=True: 프레임 정확도 보장(권장). 컷 경계가 키프레임이 아니어도 정확.
    reencode=False: 스트림 카피(빠르지만 컷 경계가 키프레임으로 스냅됨).
    """
    ffmpeg = _require("ffmpeg")
    segments = list(timeline)
    if not segments:
        raise ValueError("남은 구간이 없습니다. 편집 기준이 너무 공격적입니다.")

    with tempfile.TemporaryDirectory() as tmp:
        parts: list[str] = []
        for i, seg in enumerate(segments):
            part = os.path.join(tmp, f"part_{i:05d}.mp4")
            cmd = [ffmpeg, "-y", "-ss", f"{seg.start:.3f}", "-to", f"{seg.end:.3f}",
                   "-i", src]
            if reencode:
                cmd += [
                    "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                    "-c:a", "aac", "-b:a", "160k",
                    "-avoid_negative_ts", "make_zero",
                ]
            else:
                cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
            cmd.append(part)
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            parts.append(part)

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w") as f:
            for p in parts:
                f.write(f"file '{p}'\n")

        concat_cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        ]
        if reencode:
            concat_cmd += ["-c", "copy"]
        else:
            concat_cmd += ["-c", "copy"]
        concat_cmd.append(out_path)
        subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    return out_path
