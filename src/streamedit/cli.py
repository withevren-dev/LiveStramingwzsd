"""CLI 진입점.

예)
  python -m streamedit edit input.mp4 -o out/ \
      --intro-ref fixtures/intro.mp4 --outro-ref fixtures/outro.mp4 \
      --chat-log chat.csv --keep-ratio 0.35 --whisper-model medium
"""

from __future__ import annotations

import argparse
import sys

from .config import PipelineConfig
from .pipeline import run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="streamedit",
        description="장시간 방송 VOD 자동 편집(무음/오프닝·클로징 제거 + 하이라이트 + 한글 스크립트)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("edit", help="영상 편집 파이프라인 실행")
    e.add_argument("video", help="입력 영상 경로")
    e.add_argument("-o", "--outdir", default="out", help="출력 디렉터리")
    e.add_argument("--config", help="JSON 설정 파일 경로")

    # 무음
    e.add_argument("--silence-db", type=float, help="무음 임계값(dB, 기본 -35)")
    e.add_argument("--silence-min", type=float, help="최소 무음 길이(초, 기본 0.6)")
    # 인트로/아웃트로
    e.add_argument("--intro-ref", help="고정 오프닝 클립 경로")
    e.add_argument("--outro-ref", help="고정 클로징 클립 경로")
    e.add_argument("--fixed-threshold", type=float, help="지문 매칭 임계값(0~1, 기본 0.55)")
    # 하이라이트
    e.add_argument("--no-highlights", action="store_true", help="하이라이트 편집 끄기")
    e.add_argument("--keep-ratio", type=float, help="메인 중 남길 비율(0~1, 기본 0.35)")
    e.add_argument("--chat-log", help="채팅 로그(.csv/.jsonl)")
    # STT
    e.add_argument("--whisper-model", help="tiny/base/small/medium/large (기본 medium)")
    e.add_argument("--language", help="STT 언어(기본 ko)")
    e.add_argument("--device", help="cpu/cuda")
    e.add_argument("--no-transcript", action="store_true",
                   help="한글 스크립트(STT) 생성 건너뛰기")
    # 렌더
    e.add_argument("--no-reencode", action="store_true",
                   help="스트림 카피(빠름, 컷 정확도 낮음)")
    e.add_argument("--crf", type=int, help="x264 CRF(기본 20)")

    d = sub.add_parser("dump-config", help="기본 설정 JSON 출력")
    d.add_argument("-o", "--out", default="config.json")
    return p


def _apply_overrides(cfg: PipelineConfig, args) -> None:
    if args.silence_db is not None:
        cfg.silence_noise_db = args.silence_db
    if args.silence_min is not None:
        cfg.silence_min = args.silence_min
    if args.intro_ref:
        cfg.intro_ref = args.intro_ref
    if args.outro_ref:
        cfg.outro_ref = args.outro_ref
    if args.fixed_threshold is not None:
        cfg.fixed_threshold = args.fixed_threshold
    if args.no_highlights:
        cfg.enable_highlights = False
    if args.keep_ratio is not None:
        cfg.highlight.keep_ratio = args.keep_ratio
    if args.whisper_model:
        cfg.whisper_model = args.whisper_model
    if args.language:
        cfg.language = args.language
    if args.device:
        cfg.device = args.device
    if args.no_transcript:
        cfg.enable_transcript = False
    if args.no_reencode:
        cfg.reencode = False
    if args.crf is not None:
        cfg.crf = args.crf


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "dump-config":
        PipelineConfig().dump(args.out)
        print(f"기본 설정을 {args.out} 에 저장했습니다.")
        return 0

    if args.cmd == "edit":
        cfg = PipelineConfig.load(args.config) if args.config else PipelineConfig()
        _apply_overrides(cfg, args)
        result = run(args.video, args.outdir, cfg, chat_log=args.chat_log)
        ratio = (result.final_duration / result.original_duration * 100
                 if result.original_duration else 0)
        print("\n=== 완료 ===")
        print(f"원본: {result.original_duration/3600:.2f}h → "
              f"편집본: {result.final_duration/60:.1f}min ({ratio:.1f}%)")
        print(f"영상 : {result.video_path}")
        if result.srt_path:
            print(f"자막 : {result.srt_path}")
            print(f"대본 : {result.script_path}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
