"""무음 구간 감지 (1단계).

ffmpeg의 silencedetect 필터로 무음 구간을 찾아 '잘라낼 컷' 목록을 만든다.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from .timeline import Segment


def detect_silence(
    audio_or_video: str,
    *,
    noise_db: float = -35.0,
    min_silence: float = 0.6,
) -> list[Segment]:
    """무음 구간(잘라낼 후보) 리스트 반환.

    noise_db: 이 값보다 조용하면 무음으로 간주(dB, 낮을수록 엄격).
    min_silence: 이 길이 이상 지속돼야 무음 구간으로 인정(초).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg가 필요합니다.")

    proc = subprocess.run(
        [
            ffmpeg, "-i", audio_or_video,
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
            "-f", "null", "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    log = proc.stderr

    starts = [float(m) for m in re.findall(r"silence_start:\s*([-\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([-\d.]+)", log)]

    cuts: list[Segment] = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        if e is None:
            # 파일 끝까지 무음인 경우: 매우 큰 값으로 두면 subtract에서 클램프됨
            e = s + 10 ** 9
        if e > s:
            cuts.append(Segment(max(0.0, s), e))
    return cuts
