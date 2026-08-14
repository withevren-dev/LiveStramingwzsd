# streamedit — 장시간 방송 VOD 자동 편집

3~5시간짜리 방송 다시보기를 넣으면 자동으로:

1. **무음 구간 삭제** — 말/소리가 없는 부분을 잘라냄
2. **오프닝/클로징(인트로·아웃트로) 삭제** — 매번 쓰는 고정 클립을 지문 매칭으로 찾아 제거
3. **하이라이트 편집** — 메인(게임 플레이) 구간에서 오디오 반응·키워드·채팅 폭발을 근거로 재미있는 부분만 남김
4. **한글 스크립트 생성** — 로컬 Whisper로 STT 후, **최종 편집본 타임라인에 맞춰 정렬된** 자막(`.srt`)과 대본(`.txt`)을 따로 출력

편집은 전부 원본 시간축 위에서 "유지할 구간"을 계산한 뒤 이어붙이는 방식이라, 잘린 부분과 겹치는 대사는 스크립트에서도 자동으로 빠지고 시각도 최종본 기준으로 재계산됩니다.

> **참고:** 영상 파일을 30MB로 잘라서 줄 필요 없습니다. 이 도구는 원본 영상 파일 **경로**만 받아서 로컬에서 통째로 처리합니다.

## 설치

```bash
# 1) ffmpeg (필수)
#   Ubuntu/Debian: sudo apt-get install ffmpeg
#   macOS:         brew install ffmpeg
#   Windows:       https://ffmpeg.org/download.html

# 2) 파이썬 의존성
pip install -r requirements.txt
#   openai-whisper 는 최초 실행 시 모델을 자동 다운로드합니다.
#   GPU가 없으면 STT가 오래 걸립니다(권장: --device cuda 또는 작은 모델).
```

## 사용법

```bash
# 기본: 무음 제거 + 인트로/아웃트로 제거 + 하이라이트 + 한글 스크립트
python run.py edit "방송VOD.mp4" -o out/ \
    --intro-ref fixtures/opening.mp4 \
    --outro-ref fixtures/closing.mp4 \
    --chat-log chat.csv \
    --keep-ratio 0.35 \
    --whisper-model medium
```

> `python run.py ...` 는 윈도우·맥·리눅스에서 동일하게 동작합니다.
> (내부적으로 `python -m streamedit` 와 같지만 별도 경로 설정이 필요 없습니다.)

출력물(`out/`):

| 파일 | 내용 |
|------|------|
| `edited.mp4` | 최종 편집 영상 |
| `edited.srt` | 최종 타임라인 자막 |
| `edited_script.txt` | `[HH:MM:SS] 대사` 형식 한글 대본 |

### 자주 쓰는 옵션

```bash
# 스크립트 없이 영상만 빠르게 뽑기(STT 생략)
... edit VOD.mp4 -o out/ --no-transcript

# 하이라이트 편집 끄기(무음 + 인트로/아웃트로만 제거)
... edit VOD.mp4 -o out/ --no-highlights

# 더 많이 남기기(하이라이트 관대하게)
... edit VOD.mp4 -o out/ --keep-ratio 0.6

# 무음 판정을 더 민감하게(조용한 마이크)
... edit VOD.mp4 -o out/ --silence-db -40 --silence-min 0.8
```

### 설정 파일

세밀한 조정은 JSON 설정으로:

```bash
python run.py dump-config -o config.json   # 기본값 출력
# config.json 편집 후
python run.py edit VOD.mp4 -o out/ --config config.json
```

## 각 단계 상세

### 1. 무음 제거
ffmpeg `silencedetect`로 `--silence-db`(dB) 이하가 `--silence-min`초 이상 지속되는 구간을 잘라냅니다. 컷 경계가 말을 자르지 않도록 각 유지 구간 앞뒤에 여유(`keep_pad_before/after`)를 둡니다.

### 2. 오프닝/클로징 제거
매번 동일한 오프닝/클로징 클립을 `--intro-ref` / `--outro-ref`로 등록하면, VOD의 **앞·뒤 `fixed_search_window`초** 범위에서 오디오 로그-에너지 엔벨로프의 정규화 상호상관으로 위치를 찾아 제거합니다. 매칭 임계값은 `--fixed-threshold`(0~1). 클립을 안 주면 이 단계는 건너뜁니다.

### 3. 하이라이트 편집
메인 구간을 `window`초 단위로 나눠 아래 세 신호를 정규화·가중합해 점수를 매기고, 상위 `keep_ratio` 비율만 남깁니다.

- **오디오 톤/크기 변화** (`w_audio`) — 웃음·함성·급격한 볼륨 상승
- **키워드** (`w_keyword`) — STT 텍스트에 "대박/미쳤/레전드…" 등 리액션 키워드(설정에서 수정 가능)
- **채팅 반응** (`w_chat`) — `--chat-log` 폭발 구간

선택된 구간은 `merge_gap` 이내면 병합하고, `pad`만큼 여유를 준 뒤 `min_clip`보다 짧은 조각은 버립니다.

**채팅 로그 형식** (`--chat-log`):
- `.csv`: `time`(초 또는 `HH:MM:SS`) 컬럼 + 선택적 `count`/`weight`
- `.jsonl`: 한 줄에 `{"t": "00:12:34", "weight": 3}`

### 4. 한글 스크립트
STT는 **원본 오디오 기준으로 1회** 수행하고, 각 발화를 최종 편집본 타임라인으로 재매핑합니다. 컷과 겹치는 발화는 제거되고, 경계에 걸친 발화는 남은 조각의 시각으로 정렬됩니다.

## 테스트

```bash
python -m pytest tests/ -q
```

## 처리 시간·팁

- STT가 가장 오래 걸립니다. GPU 없이 3~5시간 영상은 `medium` 모델로 수 시간이 걸릴 수 있습니다. 빠르게 확인하려면 `--whisper-model small` 또는 `--no-transcript`로 영상 먼저 뽑고 스크립트는 나중에.
- 렌더는 기본 재인코딩(프레임 정확)입니다. 훨씬 빠른 스트림 카피는 `--no-reencode`(단, 컷 경계가 키프레임으로 스냅됨).
