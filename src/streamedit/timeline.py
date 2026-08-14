"""원본 타임라인 위의 '유지 구간(keep segments)' 모델.

편집 과정은 전부 '원본 영상 시간축' 위에서 구간을 빼거나 남기는 연산으로
표현한다. 최종적으로 남은 구간들을 순서대로 이어붙이면 편집 영상이 되고,
원본 시각 -> 최종 시각 매핑으로 STT 타임스탬프를 재정렬한다.
"""

from __future__ import annotations

from dataclasses import dataclass


EPS = 1e-6


@dataclass(frozen=True)
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def __post_init__(self) -> None:
        if self.end < self.start - EPS:
            raise ValueError(f"segment end {self.end} < start {self.start}")


def _normalize(segments: list[Segment]) -> list[Segment]:
    """정렬 + 인접/겹치는 구간 병합, 길이 0 구간 제거."""
    clean = [s for s in segments if s.duration > EPS]
    clean.sort(key=lambda s: s.start)
    merged: list[Segment] = []
    for s in clean:
        if merged and s.start <= merged[-1].end + EPS:
            last = merged[-1]
            merged[-1] = Segment(last.start, max(last.end, s.end))
        else:
            merged.append(s)
    return merged


class Timeline:
    """원본 시간축 [0, total] 위에서 유지할 구간들의 집합."""

    def __init__(self, total: float, segments: list[Segment] | None = None):
        self.total = total
        if segments is None:
            segments = [Segment(0.0, total)]
        self.segments = _normalize(segments)

    # --- 조회 --------------------------------------------------------------
    @property
    def kept_duration(self) -> float:
        return sum(s.duration for s in self.segments)

    def __iter__(self):
        return iter(self.segments)

    def __len__(self) -> int:
        return len(self.segments)

    # --- 연산 --------------------------------------------------------------
    def subtract(self, cuts: list[Segment]) -> "Timeline":
        """cuts 구간을 유지 구간에서 제거한 새 Timeline을 반환."""
        cuts = _normalize(cuts)
        result: list[Segment] = []
        for seg in self.segments:
            pieces = [seg]
            for cut in cuts:
                if cut.end <= seg.start + EPS or cut.start >= seg.end - EPS:
                    continue
                next_pieces: list[Segment] = []
                for p in pieces:
                    if cut.start <= p.start and cut.end >= p.end:
                        continue  # 조각 전체가 잘림
                    if cut.end <= p.start or cut.start >= p.end:
                        next_pieces.append(p)
                        continue
                    if cut.start > p.start:
                        next_pieces.append(Segment(p.start, cut.start))
                    if cut.end < p.end:
                        next_pieces.append(Segment(cut.end, p.end))
                pieces = next_pieces
            result.extend(pieces)
        return Timeline(self.total, result)

    def intersect(self, keep: list[Segment]) -> "Timeline":
        """keep 구간과 교집합만 남긴 새 Timeline."""
        keep = _normalize(keep)
        result: list[Segment] = []
        for seg in self.segments:
            for k in keep:
                s = max(seg.start, k.start)
                e = min(seg.end, k.end)
                if e - s > EPS:
                    result.append(Segment(s, e))
        return Timeline(self.total, result)

    def pad(self, before: float, after: float) -> "Timeline":
        """각 유지 구간의 앞뒤로 여유(패딩)를 준다. 컷 경계가 말을 자르지 않게."""
        padded = [
            Segment(max(0.0, s.start - before), min(self.total, s.end + after))
            for s in self.segments
        ]
        return Timeline(self.total, padded)

    def drop_short(self, min_duration: float) -> "Timeline":
        """너무 짧은 유지 구간(깜빡이는 컷) 제거."""
        return Timeline(
            self.total, [s for s in self.segments if s.duration >= min_duration]
        )

    # --- 시각 매핑 ----------------------------------------------------------
    def map_to_output(self, t: float) -> float | None:
        """원본 시각 t를 최종(편집본) 시각으로 변환. 잘린 구간이면 None."""
        acc = 0.0
        for s in self.segments:
            if t < s.start - EPS:
                return None
            if t <= s.end + EPS:
                return acc + (t - s.start)
            acc += s.duration
        return None

    def map_span_to_output(self, start: float, end: float):
        """원본 [start,end]와 겹치는 각 유지 구간을 최종 시각 구간으로 변환.

        하나의 발화가 컷 경계에 걸쳐 있으면 여러 조각으로 나뉠 수 있다.
        (out_start, out_end) 튜플 리스트를 반환.
        """
        acc = 0.0
        out = []
        for s in self.segments:
            ov_s = max(start, s.start)
            ov_e = min(end, s.end)
            if ov_e - ov_s > EPS:
                out.append((acc + (ov_s - s.start), acc + (ov_e - s.start)))
            acc += s.duration
        return out
