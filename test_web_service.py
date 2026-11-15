
import json
import pytest

import apply_zoom


def make_events():
    return [
        {"t": 1.0, "x": 640, "y": 360, "type": "in"},
        {"t": 3.0, "x": 640, "y": 360, "type": "out"}
    ]


def make_sidecar(events):
    return {
        "viewport": {
            "width": 1280,
            "height": 720
        },
        "fps": 20,
        "zoom_factor": 2.0,
        "ramp_sec": 0.5,
        "events": events
    }


def test_ramp_frame_calculation():
    events = make_events()

    pairs = apply_zoom.pair_zoom_events(
        events,
        fps=20,
        ramp_frames=10
    )

    assert pairs == [
        {
            "start": 20,
            "x": 640,
            "y": 360,
            "end": 60
        }
    ]


def test_zoom_filter_contains_smooth_ramp():
    video_filter = apply_zoom.build_zoom_filter(
        width=1280,
        height=720,
        fps=20,
        total_frames=200,
        events=make_events(),
        zoom_factor=2.0,
        ramp_sec=0.5
    )

    assert "on-20" in video_filter
    assert "on-60" in video_filter
    assert "3-2*" in video_filter
    assert "zoompan=" in video_filter


def test_coordinate_clamping():
    crop_x, crop_y = apply_zoom.clamp_crop(
        x=0,
        y=0,
        width=1280,
        height=720,
        zoom=2
    )

    assert crop_x == 0
    assert crop_y == 0

    crop_x, crop_y = apply_zoom.clamp_crop(
        x=1280,
        y=720,
        width=1280,
        height=720,
        zoom=2
    )

    assert crop_x == 640
    assert crop_y == 360


def test_multiple_zoom_pairs():
    events = [
        {"t": 1.0, "x": 300, "y": 200, "type": "in"},
        {"t": 3.0, "x": 300, "y": 200, "type": "out"},
        {"t": 4.0, "x": 900, "y": 500, "type": "in"},
        {"t": 6.0, "x": 900, "y": 500, "type": "out"}
    ]

    pairs = apply_zoom.pair_zoom_events(
        events,
        fps=20,
        ramp_frames=10
    )

    assert len(pairs) == 2

    assert pairs[0] == {
        "start": 20,
        "x": 300,
        "y": 200,
        "end": 60
    }

    assert pairs[1] == {
        "start": 80,
        "x": 900,
        "y": 500,
        "end": 120
    }

    video_filter = apply_zoom.build_zoom_filter(
        width=1280,
        height=720,
        fps=20,
        total_frames=200,
        events=events,
        zoom_factor=2.0,
        ramp_sec=0.5
    )

    assert "on-20" in video_filter
    assert "on-60" in video_filter
    assert "on-80" in video_filter
    assert "on-120" in video_filter


def test_open_ended_zoom():
    events = [
        {"t": 2.0, "x": 640, "y": 360, "type": "in"}
    ]

    pairs = apply_zoom.pair_zoom_events(
        events,
        fps=20,
        ramp_frames=10
    )

    assert pairs == [
        {
            "start": 40,
            "x": 640,
            "y": 360
        }
    ]

    video_filter = apply_zoom.build_zoom_filter(
        width=1280,
        height=720,
        fps=20,
        total_frames=200,
        events=events,
        zoom_factor=2.0,
        ramp_sec=0.5
    )

    assert r"gte(on\,40)" in video_filter
    assert "on-40" in video_filter


def test_load_zoom_data(tmp_path):
    sidecar_path = tmp_path / "recording.webm.zoom.json"

    sidecar_path.write_text(
        json.dumps(make_sidecar(make_events())),
        encoding="utf-8"
    )

    data = apply_zoom.load_zoom_data(sidecar_path)

    assert data["width"] == 1280
    assert data["height"] == 720
    assert data["fps"] == 20
    assert data["zoom_factor"] == 2.0
    assert data["ramp_sec"] == 0.5
    assert data["events"] == make_events()


def test_legacy_sidecar_without_event_types(tmp_path):
    events = [
        {"t": 1.0, "x": 400, "y": 300},
        {"t": 3.0, "x": 400, "y": 300},
        {"t": 4.0, "x": 800, "y": 500},
        {"t": 6.0, "x": 800, "y": 500}
    ]

    sidecar_path = tmp_path / "legacy.zoom.json"

    sidecar_path.write_text(
        json.dumps(make_sidecar(events)),
        encoding="utf-8"
    )

    data = apply_zoom.load_zoom_data(sidecar_path)

    assert [event["type"] for event in data["events"]] == [
        "in", "out", "in", "out"
    ]


def test_invalid_event_order_raises_error(tmp_path):
    events = [
        {"t": 3.0, "x": 640, "y": 360, "type": "in"},
        {"t": 2.0, "x": 640, "y": 360, "type": "out"}
    ]

    sidecar_path = tmp_path / "invalid.zoom.json"

    sidecar_path.write_text(
        json.dumps(make_sidecar(events)),
        encoding="utf-8"
    )

    with pytest.raises(ValueError):
        apply_zoom.load_zoom_data(sidecar_path)


def test_zoom_out_without_zoom_in_raises_error():
    events = [
        {"t": 2.0, "x": 640, "y": 360, "type": "out"}
    ]

    with pytest.raises(ValueError):
        apply_zoom.pair_zoom_events(
            events,
            fps=20,
            ramp_frames=10
        )


def test_overlapping_zoom_pairs_raise_error():
    events = [
        {"t": 1.0, "x": 300, "y": 200, "type": "in"},
        {"t": 3.0, "x": 300, "y": 200, "type": "out"},
        {"t": 3.2, "x": 900, "y": 500, "type": "in"},
        {"t": 5.0, "x": 900, "y": 500, "type": "out"}
    ]

    with pytest.raises(ValueError):
        apply_zoom.build_zoom_filter(
            width=1280,
            height=720,
            fps=20,
            total_frames=200,
            events=events,
            zoom_factor=2.0,
            ramp_sec=0.5
        )


def test_no_events_copies_video_unchanged(tmp_path, monkeypatch):
    video_path = tmp_path / "recording.webm"
    output_path = tmp_path / "recording_zoomed.webm"
    sidecar_path = tmp_path / "recording.webm.zoom.json"

    original_content = b"original video content"
    video_path.write_bytes(original_content)

    sidecar_path.write_text(
        json.dumps(make_sidecar([])),
        encoding="utf-8"
    )

    def unexpected_ffmpeg(*args, **kwargs):
        pytest.fail("FFmpeg should not run when there are no zoom events")

    monkeypatch.setattr(
        apply_zoom.subprocess,
        "run",
        unexpected_ffmpeg
    )

    result = apply_zoom.apply_zoom(
        video_path=video_path,
        output_path=output_path
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes() == original_content


def test_missing_sidecar_copies_video_unchanged(tmp_path, monkeypatch):
    video_path = tmp_path / "recording.webm"
    output_path = tmp_path / "recording_zoomed.webm"

    original_content = b"original video content"
    video_path.write_bytes(original_content)

    def unexpected_ffmpeg(*args, **kwargs):
        pytest.fail("FFmpeg should not run when the sidecar is missing")

    monkeypatch.setattr(
        apply_zoom.subprocess,
        "run",
        unexpected_ffmpeg
    )

    apply_zoom.apply_zoom(
        video_path=video_path,
        output_path=output_path
    )

    assert output_path.read_bytes() == original_content
