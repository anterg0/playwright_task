
import argparse
import json
import shutil
import subprocess
from pathlib import Path


def load_zoom_data(sidecar_path):
    with open(sidecar_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    viewport = data["viewport"]

    width = int(viewport["width"])
    height = int(viewport["height"])
    fps = float(data["fps"])
    zoom_factor = float(data.get("zoom_factor", 2.0))
    ramp_sec = float(data.get("ramp_sec", 0.5))

    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("Invalid viewport dimensions or FPS")

    if zoom_factor < 1 or ramp_sec < 0:
        raise ValueError("Invalid zoom factor or ramp duration")

    events = []
    previous_time = -1

    for index, event in enumerate(data.get("events", [])):
        timestamp = float(event["t"])
        x = float(event["x"])
        y = float(event["y"])

        if timestamp < 0 or timestamp < previous_time:
            raise ValueError("Zoom events must have non-negative, ordered timestamps")

        previous_time = timestamp

        event_type = event.get("type")

        if event_type is None:
            event_type = "in" if index % 2 == 0 else "out"

        if event_type not in ("in", "out"):
            raise ValueError(f"Invalid zoom event type: {event_type}")

        events.append({
            "t": timestamp,
            "x": x,
            "y": y,
            "type": event_type
        })

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "zoom_factor": zoom_factor,
        "ramp_sec": ramp_sec,
        "events": events
    }


def clamp_crop(x, y, width, height, zoom):
    crop_width = width / zoom
    crop_height = height / zoom

    crop_x = max(0, min(x - crop_width / 2, width - crop_width))
    crop_y = max(0, min(y - crop_height / 2, height - crop_height))

    return crop_x, crop_y


def pair_zoom_events(events, fps, ramp_frames):
    pairs = []
    active_event = None

    for event in events:
        frame = round(event["t"] * fps)

        if event["type"] == "in":
            if active_event is not None:
                raise ValueError("A zoom-in event occurred before the previous zoom ended")

            active_event = {
                "start": frame,
                "x": event["x"],
                "y": event["y"]
            }

        else:
            if active_event is None:
                raise ValueError("Zoom-out event without a matching zoom-in event")

            if frame < active_event["start"] + ramp_frames:
                raise ValueError("Zoom-out occurs before the zoom-in transition finishes")

            active_event["end"] = frame
            pairs.append(active_event)
            active_event = None

    if active_event is not None:
        pairs.append(active_event)

    return pairs


def ffmpeg_expression(expression):
    return expression.replace(",", r"\,")


def build_zoom_filter(
    width,
    height,
    fps,
    total_frames,
    events,
    zoom_factor=2.0,
    ramp_sec=0.5
):
    ramp_frames = max(1, round(ramp_sec * fps))

    pairs = pair_zoom_events(events, fps, ramp_frames)

    for index, pair in enumerate(pairs):
        if index > 0:
            previous = pairs[index - 1]

            if "end" not in previous:
                raise ValueError("An open-ended zoom cannot be followed by another zoom")

            if pair["start"] < previous["end"] + ramp_frames:
                raise ValueError("Zoom transitions overlap")

    zoom_expression = "1"

    for pair in reversed(pairs):
        start = pair["start"]
        x = max(0, min(pair["x"], width))
        y = max(0, min(pair["y"], height))

        if "end" in pair:
            end = pair["end"]

            zoom_out_progress = (
                f"min(max((on-{end})/{ramp_frames},0),1)"
            )

            zoom_out_ease = (
                f"({zoom_out_progress}*{zoom_out_progress}"
                f"*(3-2*{zoom_out_progress}))"
            )

            zoom_out = (
                f"({zoom_factor}-({zoom_factor}-1)*{zoom_out_ease})"
            )

            hold_end = end

            zoom_in_and_hold = (
                f"if(lt(on,{start + ramp_frames}),"
                f"1+({zoom_factor}-1)*"
                f"min(max((on-{start})/{ramp_frames},0),1)*"
                f"(3-2*min(max((on-{start})/{ramp_frames},0),1)),"
                f"{zoom_factor})"
            )

            interval_expression = (
                f"if(between(on,{start},{hold_end + ramp_frames}),"
                f"if(gte(on,{end}),{zoom_out},{zoom_in_and_hold}),"
                f"{zoom_expression})"
            )

        else:
            progress = f"min(max((on-{start})/{ramp_frames},0),1)"
            ease = f"({progress}*{progress}*(3-2*{progress}))"

            zoom_in = f"(1+({zoom_factor}-1)*{ease})"

            interval_expression = (
                f"if(gte(on,{start}),{zoom_in},{zoom_expression})"
            )

        zoom_expression = interval_expression

    focus_x = "0"
    focus_y = "0"

    for pair in reversed(pairs):
        start = pair["start"]
        x = max(0, min(pair["x"], width))
        y = max(0, min(pair["y"], height))

        focus_x = f"if(gte(on,{start}),{x},{focus_x})"
        focus_y = f"if(gte(on,{start}),{y},{focus_y})"

    zoom_expression = ffmpeg_expression(zoom_expression)

    x_expression = ffmpeg_expression(
        f"min(max(({focus_x})-iw/(2*zoom),0),iw-iw/zoom)"
    )

    y_expression = ffmpeg_expression(
        f"min(max(({focus_y})-ih/(2*zoom),0),ih-ih/zoom)"
    )

    return (
        f"zoompan="
        f"z='{zoom_expression}':"
        f"x='{x_expression}':"
        f"y='{y_expression}':"
        f"d=1:"
        f"s={width}x{height}:"
        f"fps={fps}"
    )


def get_video_duration(video_path, ffprobe="ffprobe"):
    command = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )

    return float(result.stdout.strip())


def apply_zoom(
    video_path,
    ffmpeg="ffmpeg",
    ffprobe="ffprobe",
    output_path=None,
    dry_run=False
):
    video_path = Path(video_path)
    sidecar_path = Path(str(video_path) + ".zoom.json")

    if output_path is None:
        output_path = video_path.with_name(
            video_path.stem + "_zoomed" + video_path.suffix
        )
    else:
        output_path = Path(output_path)

    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if not sidecar_path.is_file():
        if dry_run:
            print(f"No sidecar found. Would copy {video_path} to {output_path}")
            return output_path

        shutil.copy2(video_path, output_path)
        print(f"No zoom events found. Copied video to {output_path}")
        return output_path

    data = load_zoom_data(sidecar_path)

    if not data["events"]:
        if dry_run:
            print(f"No zoom events. Would copy {video_path} to {output_path}")
            return output_path

        shutil.copy2(video_path, output_path)
        print(f"No zoom events found. Copied video to {output_path}")
        return output_path

    duration = get_video_duration(video_path, ffprobe)
    total_frames = round(duration * data["fps"])

    video_filter = build_zoom_filter(
        width=data["width"],
        height=data["height"],
        fps=data["fps"],
        total_frames=total_frames,
        events=data["events"],
        zoom_factor=data["zoom_factor"],
        ramp_sec=data["ramp_sec"]
    )

    command = [
        ffmpeg,
        "-y",
        "-i", str(video_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-vf", video_filter,
        "-c:v", "libvpx-vp9",
        "-crf", "30",
        "-b:v", "0",
        "-c:a", "libopus",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]

    if dry_run:
        print(subprocess.list2cmdline(command))
        return output_path

    subprocess.run(command, check=True)

    print(f"Processed video saved to: {output_path}")

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--video", required=True)
    parser.add_argument("--output")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    apply_zoom(
        video_path=args.video,
        output_path=args.output,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        dry_run=args.dry_run
    )
