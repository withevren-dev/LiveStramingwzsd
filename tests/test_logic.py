import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from streamedit.config import parse_chat_log  # noqa: E402
from streamedit.timeline import Segment, Timeline  # noqa: E402
from streamedit.transcribe import remap_to_output, write_script_txt  # noqa: E402


def test_parse_chat_csv(tmp_path):
    p = tmp_path / "chat.csv"
    p.write_text("time,count\n00:00:05,3\n10.5,1\n01:02:03,2\n", encoding="utf-8")
    ev = parse_chat_log(str(p))
    assert [round(e.t, 1) for e in ev] == [5.0, 10.5, 3723.0]
    assert ev[0].weight == 3.0


def test_parse_chat_jsonl(tmp_path):
    p = tmp_path / "chat.jsonl"
    p.write_text('{"t": "00:01:00", "weight": 5}\n{"t": 12}\n', encoding="utf-8")
    ev = parse_chat_log(str(p))
    assert [round(e.t, 1) for e in ev] == [60.0, 12.0]
    assert ev[0].weight == 5.0


def test_remap_drops_cut_utterances():
    # 원본 100s에서 20~30s를 잘라냄
    tl = Timeline(100.0).subtract([Segment(20, 30)])
    transcript = [
        {"start": 5, "end": 8, "text": "앞부분"},      # 유지 → 5~8
        {"start": 22, "end": 28, "text": "잘린부분"},   # 컷 안 → 버려짐
        {"start": 40, "end": 44, "text": "뒷부분"},     # 유지 → 30~34
    ]
    out = remap_to_output(transcript, tl)
    texts = [u.text for u in out]
    assert texts == ["앞부분", "뒷부분"]
    assert abs(out[1].start - 30.0) < 1e-6  # 40 - 10s컷


def test_script_txt_format(tmp_path):
    tl = Timeline(100.0)
    out = remap_to_output([{"start": 65, "end": 68, "text": "안녕하세요"}], tl)
    f = tmp_path / "s.txt"
    write_script_txt(out, str(f))
    assert f.read_text(encoding="utf-8").strip() == "[00:01:05] 안녕하세요"
