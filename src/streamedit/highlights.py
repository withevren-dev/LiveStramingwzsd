"""하이라이트 감지 (3단계).

메인(게임 플레이) 구간을 짧은 윈도우로 나누고, 아래 세 신호를 결합해 점수를 매긴 뒤
상위 구간만 남긴다.

  1) 오디오 톤/크기 변화 — 웃음·함성·급격한 볼륨 상승
  2) 특정 키워드      — STT 텍스트에서 리액션 키워드 등장
  3) 채팅/댓글 반응    — 채팅 폭발(도배) 구간

키워드/채팅은 있으면 가점, 없으면 오디오만으로 동작한다.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field

import numpy as np

from .timeline import Segment, Timeline

DEFAULT_KEYWORDS = [
    "대박", "미쳤", "미친", "말도 안", "헐", "이게 되네", "역대급", "레전드",
    "지린다", "지렸", "소름", "개쩐", "오졌", "실화냐", "와 진짜", "미쳤다",
    "클립", "이거 클립", "다시 봐", "웃겨", "ㅋㅋㅋ",
]


@dataclass
class ChatEvent:
    t: float          # 원본 영상 기준 시각(초)
    weight: float = 1.0


@dataclass
class HighlightConfig:
    window: float = 6.0            # 점수 윈도우 크기(초)
    keep_ratio: float = 0.35       # 메인 구간 중 남길 비율(0~1)
    min_clip: float = 4.0          # 하이라이트 최소 길이(초)
    merge_gap: float = 8.0         # 이 간격 이내 하이라이트는 하나로 병합(초)
    pad: float = 2.0               # 하이라이트 앞뒤 여유(초)
    w_audio: float = 1.0
    w_keyword: float = 1.5
    w_chat: float = 1.2
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))


def _read_wav_mono(path: str):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        width = w.getsampwidth()
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if data.size:
        data /= float(np.iinfo(dtype).max)
    return data, sr


def _audio_scores(wav_path: str, windows: list[tuple[float, float]]) -> np.ndarray:
    """각 윈도우의 오디오 활력 점수 = (평균 에너지) + (에너지 변화폭)."""
    sig, sr = _read_wav_mono(wav_path)
    scores = np.zeros(len(windows), dtype=np.float32)
    for i, (s, e) in enumerate(windows):
        a = int(s * sr)
        b = min(len(sig), int(e * sr))
        if b <= a:
            continue
        seg = sig[a:b]
        rms = np.sqrt(np.mean(seg**2) + 1e-10)
        # 짧은 하위프레임 간 변동(웃음/함성은 변동이 큼)
        sub = max(1, int(0.1 * sr))
        nf = len(seg) // sub
        var = 0.0
        if nf > 1:
            frames = seg[: nf * sub].reshape(nf, sub)
            frame_rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-10)
            var = float(np.std(frame_rms))
        scores[i] = rms + var
    return scores


def _keyword_scores(
    windows: list[tuple[float, float]],
    transcript,
    keywords: list[str],
) -> np.ndarray:
    scores = np.zeros(len(windows), dtype=np.float32)
    if not transcript:
        return scores
    lowered = [(seg["start"], seg["end"], seg["text"]) for seg in transcript]
    for i, (s, e) in enumerate(windows):
        hits = 0
        for st, en, text in lowered:
            if en < s or st > e:
                continue
            for kw in keywords:
                if kw in text:
                    hits += 1
        scores[i] = hits
    return scores


def _chat_scores(
    windows: list[tuple[float, float]],
    chat: list[ChatEvent],
) -> np.ndarray:
    scores = np.zeros(len(windows), dtype=np.float32)
    if not chat:
        return scores
    for i, (s, e) in enumerate(windows):
        scores[i] = sum(c.weight for c in chat if s <= c.t < e)
    return scores


def _norm(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-8:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def select_highlights(
    wav_path: str,
    main: Timeline,
    total: float,
    cfg: HighlightConfig,
    *,
    transcript=None,
    chat: list[ChatEvent] | None = None,
) -> Timeline:
    """메인 구간에서 하이라이트만 남긴 Timeline을 반환."""
    # 메인 유지 구간을 window 크기로 잘게 나눔
    windows: list[tuple[float, float]] = []
    for seg in main:
        t = seg.start
        while t < seg.end - 1e-3:
            windows.append((t, min(seg.end, t + cfg.window)))
            t += cfg.window
    if not windows:
        return main

    a = _norm(_audio_scores(wav_path, windows)) * cfg.w_audio
    k = _norm(_keyword_scores(windows, transcript, cfg.keywords)) * cfg.w_keyword
    c = _norm(_chat_scores(windows, chat or [])) * cfg.w_chat
    total_score = a + k + c

    # 상위 keep_ratio 만큼의 윈도우 선택
    order = np.argsort(total_score)[::-1]
    target = cfg.keep_ratio * sum(w[1] - w[0] for w in windows)
    chosen: list[Segment] = []
    acc = 0.0
    for idx in order:
        if acc >= target and total_score[idx] <= 0:
            break
        if acc >= target:
            break
        s, e = windows[idx]
        chosen.append(Segment(s, e))
        acc += e - s

    highlights = Timeline(total, chosen)
    # 인접 하이라이트 병합 + 패딩 + 짧은 조각 제거
    merged = highlights.pad(cfg.merge_gap / 2, cfg.merge_gap / 2)  # 간격 병합용
    merged = Timeline(total, list(merged))  # pad가 이미 병합 수행
    merged = merged.intersect(list(main))    # 메인 밖으로 새지 않게
    merged = merged.pad(cfg.pad, cfg.pad).intersect(list(main))
    merged = merged.drop_short(cfg.min_clip)
    return merged
