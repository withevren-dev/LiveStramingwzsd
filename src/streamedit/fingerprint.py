"""고정 인트로/아웃트로(오프닝/클로징) 클립 감지 (2단계).

사용자가 '매번 동일하게 쓰는' 오프닝/클로징 클립을 레퍼런스로 등록해 두면,
VOD의 앞/뒤 구간에서 오디오 지문(로그-에너지 엔벨로프)의 정규화 상호상관으로
정확한 위치를 찾아 잘라낼 컷을 만든다.

무거운 의존성을 피하려고 numpy + 표준 wave 모듈만 사용한다.
"""

from __future__ import annotations

import wave

import numpy as np

from .ffmpeg_utils import extract_audio
from .timeline import Segment

HOP = 0.05  # 엔벨로프 프레임 간격(초)


def _read_wav_mono(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
        width = w.getsampwidth()
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if data.size:
        data /= float(np.iinfo(dtype).max)
    return data, sr


def _log_energy_envelope(signal: np.ndarray, sr: int) -> np.ndarray:
    hop = max(1, int(sr * HOP))
    n_frames = len(signal) // hop
    if n_frames == 0:
        return np.zeros(0, dtype=np.float32)
    frames = signal[: n_frames * hop].reshape(n_frames, hop)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-10)
    env = np.log(rms + 1e-6)
    return env.astype(np.float32)


def _zscore(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    mu = x.mean()
    sd = x.std()
    return (x - mu) / sd if sd > 1e-8 else x - mu


def _best_match(target_env: np.ndarray, ref_env: np.ndarray):
    """target_env 안에서 ref_env가 가장 잘 맞는 프레임 오프셋과 상관값."""
    m = len(ref_env)
    if m == 0 or len(target_env) < m:
        return None, -1.0
    ref = _zscore(ref_env)
    best_off, best_corr = 0, -1.0
    for off in range(0, len(target_env) - m + 1):
        window = _zscore(target_env[off : off + m])
        corr = float(np.dot(window, ref) / m)
        if corr > best_corr:
            best_corr, best_off = corr, off
    return best_off, best_corr


def _envelope_from_media(path: str, workdir: str, name: str) -> tuple[np.ndarray, float]:
    import os

    wav = os.path.join(workdir, f"{name}.wav")
    extract_audio(path, wav)
    sig, sr = _read_wav_mono(wav)
    env = _log_energy_envelope(sig, sr)
    dur = len(sig) / sr if sr else 0.0
    return env, dur


def detect_fixed_clips(
    video: str,
    workdir: str,
    *,
    intro_ref: str | None = None,
    outro_ref: str | None = None,
    total: float,
    search_window: float = 300.0,
    threshold: float = 0.55,
) -> list[Segment]:
    """인트로/아웃트로 레퍼런스 클립이 VOD의 앞/뒤에서 매칭되는 구간을 컷으로 반환.

    search_window: 앞/뒤 이 시간(초) 범위 안에서만 탐색.
    threshold: 정규화 상호상관이 이 값 이상이어야 매칭으로 인정.
    """
    cuts: list[Segment] = []
    win_frames = int(search_window / HOP)

    if intro_ref:
        ref_env, ref_dur = _envelope_from_media(intro_ref, workdir, "intro_ref")
        head_env, _ = _envelope_from_media(video, workdir, "head")
        head_env = head_env[:win_frames]
        off, corr = _best_match(head_env, ref_env)
        if off is not None and corr >= threshold:
            start = off * HOP
            cuts.append(Segment(max(0.0, start), min(total, start + ref_dur)))

    if outro_ref:
        ref_env, ref_dur = _envelope_from_media(outro_ref, workdir, "outro_ref")
        tail_env, _ = _envelope_from_media(video, workdir, "tail")
        tail_start_frame = max(0, len(tail_env) - win_frames)
        tail_slice = tail_env[tail_start_frame:]
        off, corr = _best_match(tail_slice, ref_env)
        if off is not None and corr >= threshold:
            start = (tail_start_frame + off) * HOP
            cuts.append(Segment(max(0.0, start), min(total, start + ref_dur)))

    return cuts
