
import os
import requests

def UploadVideo(server_url: str, video_path: str, company_name: str) -> str:
    url = f"{server_url.rstrip('/')}/upload"

    with open(video_path, "rb") as video:
        response = requests.post(
            url,
            files={
                "file": (
                    os.path.basename(video_path),
                    video,
                    "video/webm"
                )
            },
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
