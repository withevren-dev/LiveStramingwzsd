"""음성인식(STT) + 한글 스크립트 생성 (4단계).

로컬 Whisper로 한국어 자막을 만든다. STT는 '원본 오디오' 기준으로 돌리고,
각 발화 구간을 최종 편집본 Timeline으로 재매핑해 최종 타임라인에 정렬한다.
(원본 기준으로 한 번만 돌리면 되고, 컷 경계에 걸친 발화도 조각내 정확히 반영된다.)
"""

from __future__ import annotations

from dataclasses import dataclass

from .timeline import Timeline


@dataclass
class Utterance:
    start: float   # 최종 편집본 기준 시각(초)
    end: float
    text: str


def transcribe_original(
    audio_path: str,
    *,
    model_size: str = "medium",
    language: str = "ko",
    device: str | None = None,
):
    """원본 오디오를 Whisper로 STT. [{start,end,text}, ...] 반환(원본 시간축)."""
    try:
        import whisper  # openai-whisper
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "openai-whisper 가 필요합니다: pip install openai-whisper"
        ) from exc

    load_kwargs = {}
    if device:
        load_kwargs["device"] = device
    model = whisper.load_model(model_size, **load_kwargs)
    result = model.transcribe(audio_path, language=language, verbose=False)
    return [
        {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()}
        for s in result.get("segments", [])
    ]


def remap_to_output(transcript, timeline: Timeline) -> list[Utterance]:
    """원본 시간축 발화들을 최종 편집본 타임라인으로 재매핑.

    컷된 구간과 겹치는 발화는 버려지고, 경계에 걸친 발화는 남은 조각만 반영된다.
    """
    out: list[Utterance] = []
    for seg in transcript:
        spans = timeline.map_span_to_output(seg["start"], seg["end"])
        if not spans:
            continue
        # 여러 조각으로 나뉘면 가장 긴 조각 하나에 텍스트를 싣는다(자막 중복 방지).
        best = max(spans, key=lambda p: p[1] - p[0])
        out.append(Utterance(best[0], best[1], seg["text"]))
    out.sort(key=lambda u: u.start)
    return out


def _fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(utterances: list[Utterance], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, u in enumerate(utterances, 1):
            f.write(f"{i}\n")
            f.write(f"{_fmt_ts(u.start)} --> {_fmt_ts(u.end)}\n")
            f.write(f"{u.text}\n\n")


def write_script_txt(utterances: list[Utterance], path: str) -> None:
    """[HH:MM:SS] 대사 형태의 읽기용 한글 스크립트."""
    with open(path, "w", encoding="utf-8") as f:
        for u in utterances:
            ts = _fmt_ts(u.start).split(",")[0]
            f.write(f"[{ts}] {u.text}\n")
