"""파이프라인 설정 + 채팅 로그 파서."""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field

from .highlights import ChatEvent, HighlightConfig


@dataclass
class PipelineConfig:
    # 1단계: 무음
    silence_noise_db: float = -35.0
    silence_min: float = 0.6
    # 2단계: 인트로/아웃트로
    intro_ref: str | None = None
    outro_ref: str | None = None
    fixed_search_window: float = 300.0
    fixed_threshold: float = 0.55
    # 3단계: 하이라이트
    highlight: HighlightConfig = field(default_factory=HighlightConfig)
    enable_highlights: bool = True
    # 컷 경계 여유
    keep_pad_before: float = 0.15
    keep_pad_after: float = 0.30
    min_keep: float = 0.4
    # 4단계: STT
    whisper_model: str = "medium"
    language: str = "ko"
    device: str | None = None
    enable_transcript: bool = True
    # 렌더링
    reencode: bool = True
    crf: int = 20
    preset: str = "medium"

    @classmethod
    def load(cls, path: str) -> "PipelineConfig":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        hl = data.pop("highlight", None)
        cfg = cls(**data)
        if hl:
            cfg.highlight = HighlightConfig(**hl)
        return cfg

    def dump(self, path: str) -> None:
        d = asdict(self)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)


def parse_chat_log(path: str) -> list[ChatEvent]:
    """채팅 로그를 ChatEvent 리스트로 파싱.

    지원 포맷:
      - .csv : 헤더에 time(초 또는 HH:MM:SS) 컬럼, 선택적으로 weight/count
      - .jsonl : 각 줄 {"t": 초 또는 "HH:MM:SS", "weight": 옵션}
    한 줄이 한 메시지면 weight 생략(=1.0). count 컬럼이 있으면 그 값을 weight로.
    """
    if not path or not os.path.exists(path):
        return []
    ext = os.path.splitext(path)[1].lower()
    events: list[ChatEvent] = []
    if ext == ".csv":
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = _parse_time(row.get("time") or row.get("t") or "")
                if t is None:
                    continue
                w = row.get("weight") or row.get("count") or "1"
                events.append(ChatEvent(t, float(w)))
    elif ext in (".jsonl", ".ndjson"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                t = _parse_time(str(obj.get("t") or obj.get("time") or ""))
                if t is None:
                    continue
                events.append(ChatEvent(t, float(obj.get("weight", 1.0))))
    else:
        raise ValueError(f"지원하지 않는 채팅 로그 형식: {ext}")
    return events


def _parse_time(v: str):
    v = v.strip()
    if not v:
        return None
    if ":" in v:
        parts = [float(p) for p in v.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        h, m, s = parts[-3], parts[-2], parts[-1]
        return h * 3600 + m * 60 + s
    try:
        return float(v)
    except ValueError:
        return None
