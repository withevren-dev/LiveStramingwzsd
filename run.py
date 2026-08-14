#!/usr/bin/env python3
"""어느 OS에서나 동일하게 쓰는 실행 진입점.

  python run.py edit "방송VOD.mp4" -o out/ --intro-ref opening.mp4 ...
  python run.py dump-config -o config.json

(PYTHONPATH 설정이 필요 없도록 src/ 를 자동으로 경로에 추가한다.)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from streamedit.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
