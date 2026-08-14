import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from streamedit.timeline import Segment, Timeline  # noqa: E402


def test_subtract_middle():
    tl = Timeline(100.0)
    tl = tl.subtract([Segment(20, 30)])
    assert [(s.start, s.end) for s in tl] == [(0, 20), (30, 100)]
    assert abs(tl.kept_duration - 90.0) < 1e-6


def test_subtract_overlapping_and_edges():
    tl = Timeline(100.0).subtract([Segment(-10, 10), Segment(90, 200)])
    assert [(s.start, s.end) for s in tl] == [(10, 90)]


def test_intersect():
    tl = Timeline(100.0).subtract([Segment(40, 50)])  # [0,40],[50,100]
    tl = tl.intersect([Segment(30, 60)])
    assert [(s.start, s.end) for s in tl] == [(30, 40), (50, 60)]


def test_map_to_output_skips_cuts():
    tl = Timeline(100.0).subtract([Segment(20, 30)])  # cut 10s
    assert abs(tl.map_to_output(10) - 10) < 1e-6
    assert tl.map_to_output(25) is None          # 잘린 구간
    assert abs(tl.map_to_output(40) - 30) < 1e-6  # 40 - 10s컷 = 30


def test_map_span_split_across_cut():
    tl = Timeline(100.0).subtract([Segment(20, 30)])
    spans = tl.map_span_to_output(15, 35)
    # 15..20 -> 15..20,  30..35 -> 20..25
    assert len(spans) == 2
    assert abs(spans[0][0] - 15) < 1e-6 and abs(spans[0][1] - 20) < 1e-6
    assert abs(spans[1][0] - 20) < 1e-6 and abs(spans[1][1] - 25) < 1e-6


def test_pad_merges_adjacent():
    tl = Timeline(100.0, [Segment(10, 20), Segment(21, 30)])
    padded = tl.pad(1.0, 1.0)
    assert [(s.start, s.end) for s in padded] == [(9, 31)]


def test_drop_short():
    tl = Timeline(100.0, [Segment(0, 1), Segment(10, 30)])
    assert [(s.start, s.end) for s in tl.drop_short(5)] == [(10, 30)]
