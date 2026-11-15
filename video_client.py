import os
import requests

def UploadVideo(server_url: str, video_path: str, company_name: str) -> str:
    url = f"{server_url.rstrip('/')}/upload"
    zoom_path = f"{video_path}.zoom.json"

    with open(video_path, "rb") as video:
        files = {
            "file": (
                os.path.basename(video_path),
                video,
                "video/webm"
            )
        }

        if os.path.isfile(zoom_path):
            with open(zoom_path, "rb") as zoom_data:
                files["zoom_data"] = (
                    os.path.basename(zoom_path),
                    zoom_data,
                    "application/json"
                )

                response = requests.post(
                    url,
                    files=files,
                    data={"company_name": company_name},
                    timeout=120
                )
        else:
            response = requests.post(
                url,
                files=files,
                data={"company_name": company_name},
                timeout=120
            )

    response.raise_for_status()
    return response.json()["video_url"]


def GetVideoURL(server_url: str, company_name: str) -> str:
    url = f"{server_url.rstrip('/')}/get_video_url"

    response = requests.get(
        url,
        params={"company_name": company_name},
        timeout=30
    )

    response.raise_for_status()
    return response.json()["video_url"]