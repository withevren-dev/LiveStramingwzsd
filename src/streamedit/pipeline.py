"""전체 파이프라인 오케스트레이션.

원본 -> (무음 제거) -> (인트로/아웃트로 제거) -> (하이라이트 선별)
     -> 최종 영상 렌더 + 최종 타임라인 정렬 한글 스크립트
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import fingerprint, silence
from .config import PipelineConfig, parse_chat_log
from .ffmpeg_utils import extract_audio, probe_duration, render_timeline
from .highlights import select_highlights
from .timeline import Segment, Timeline
from .transcribe import (
    remap_to_output,
    transcribe_original,
    write_script_txt,
    write_srt,
)


@dataclass
class PipelineResult:
    video_path: str
    srt_path: str
    script_path: str
    original_duration: float
    final_duration: float
    timeline: Timeline


def run(
    video: str,
    outdir: str,
    cfg: PipelineConfig,
    *,
    chat_log: str | None = None,
    log=print,
) -> PipelineResult:
    os.makedirs(outdir, exist_ok=True)
    work = os.path.join(outdir, "_work")
    os.makedirs(work, exist_ok=True)

    total = probe_duration(video)
    log(f"[0] 원본 길이: {total/3600:.2f}시간 ({total:.0f}s)")

    # 분석용 오디오 추출(무음/하이라이트/STT 공용)
    wav = os.path.join(work, "audio.wav")
    extract_audio(video, wav)

    timeline = Timeline(total)

    # 1) 무음 제거
    sil = silence.detect_silence(
        wav, noise_db=cfg.silence_noise_db, min_silence=cfg.silence_min
    )
    timeline = timeline.subtract(sil)
    log(f"[1] 무음 {len(sil)}구간 제거 → 유지 {timeline.kept_duration:.0f}s")

    # 2) 인트로/아웃트로 제거
    fixed = fingerprint.detect_fixed_clips(
        video, work,
        intro_ref=cfg.intro_ref, outro_ref=cfg.outro_ref, total=total,
        search_window=cfg.fixed_search_window, threshold=cfg.fixed_threshold,
    )
    if fixed:
        timeline = timeline.subtract(fixed)
    log(f"[2] 인트로/아웃트로 {len(fixed)}구간 제거 → 유지 {timeline.kept_duration:.0f}s")

    # 인트로/아웃트로를 뺀 '메인 영역' 정의(하이라이트 탐색 범위)
    main_bounds = _main_region(total, fixed)
    main = timeline.intersect(main_bounds)

    # STT는 하이라이트 키워드 가점에도 쓰이므로 먼저 원본 기준으로 1회 수행
    transcript = None
    if cfg.enable_transcript and cfg.enable_highlights and cfg.highlight.w_keyword > 0:
        log("[3a] 키워드 하이라이트용 STT 수행(원본 기준)...")
        transcript = transcribe_original(
            wav, model_size=cfg.whisper_model, language=cfg.language, device=cfg.device
        )

    # 3) 하이라이트 선별(메인 영역에 대해서만)
    if cfg.enable_highlights:
        chat = parse_chat_log(chat_log) if chat_log else []
        hl = select_highlights(
            wav, main, total, cfg.highlight, transcript=transcript, chat=chat
        )
        # 최종 유지 = (메인 영역의 하이라이트) ∪ (메인 밖 유지 구간은 이미 제거됨)
        timeline = hl
        log(f"[3] 하이라이트 선별 → 유지 {timeline.kept_duration:.0f}s "
            f"({len(timeline)}구간)")
    else:
        timeline = main

    # 컷 경계 여유 + 짧은 조각 제거
    timeline = timeline.pad(cfg.keep_pad_before, cfg.keep_pad_after)
    timeline = timeline.drop_short(cfg.min_keep)
    log(f"[3.5] 정리 후 최종 유지 {timeline.kept_duration:.0f}s ({len(timeline)}구간)")

    # 4) 최종 영상 렌더
    out_video = os.path.join(outdir, "edited.mp4")
    render_timeline(
        video, timeline, out_video,
        reencode=cfg.reencode, crf=cfg.crf, preset=cfg.preset,
    )
    log(f"[4] 최종 영상 렌더 완료: {out_video}")

    if not cfg.enable_transcript:
        log("[5] 스크립트 생성 건너뜀(--no-transcript)")
        return PipelineResult(
            video_path=out_video,
            srt_path="",
            script_path="",
            original_duration=total,
            final_duration=timeline.kept_duration,
            timeline=timeline,
        )

    # STT를 아직 안 했다면 지금 수행
    if transcript is None:
        log("[5a] 스크립트용 STT 수행(원본 기준)...")
        transcript = transcribe_original(
            wav, model_size=cfg.whisper_model, language=cfg.language, device=cfg.device
        )

    # 최종 타임라인으로 스크립트 재정렬
    utterances = remap_to_output(transcript, timeline)
    srt_path = os.path.join(outdir, "edited.srt")
    script_path = os.path.join(outdir, "edited_script.txt")
    write_srt(utterances, srt_path)
    write_script_txt(utterances, script_path)
    log(f"[5] 한글 스크립트 {len(utterances)}줄 → {script_path}")

    return PipelineResult(
        video_path=out_video,
        srt_path=srt_path,
        script_path=script_path,
        original_duration=total,
        final_duration=timeline.kept_duration,
        timeline=timeline,
    )


def _main_region(total: float, fixed_cuts: list[Segment]) -> list[Segment]:
    """인트로/아웃트로 컷을 제외한 가운데 영역."""
    intro_end = 0.0
    outro_start = total
    for c in fixed_cuts:
        if c.start <= 1.0:  # 앞쪽 = 인트로
            intro_end = max(intro_end, c.end)
        if c.end >= total - 1.0:  # 뒤쪽 = 아웃트로
            outro_start = min(outro_start, c.start)
    if outro_start <= intro_end:
        return [Segment(0.0, total)]
    return [Segment(intro_end, outro_start)]
