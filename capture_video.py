
import csv
import argparse

from qscript import CaptureVideo_Magento


def PreviewVideo(video_url, view_seconds):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            page = browser.new_page()
            page.goto(video_url)

            if view_seconds > 0:
                page.wait_for_timeout(int(view_seconds * 1000))
            else:
                input("Press Enter to close the preview...")

        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server")
    parser.add_argument("--view-seconds", type=float, default=10)
    args = parser.parse_args()

    if args.view_seconds < 0:
        parser.error("--view-seconds cannot be negative")

    with open("input.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            company_name = row["company_name"]

            output_path = CaptureVideo_Magento(
                row["url"],
                company_name,
                row["language"],
                row["country"],
                row["postcode"],
                row["city"],
                row["street"],
                row["house_no"]
            )

            if output_path:
                print(f"Success: {output_path}")

                if args.server:
                    try:
                        from video_client import UploadVideo

                        video_url = UploadVideo(
                            args.server,
                            output_path,
                            company_name
                        )

                        print(f"Uploaded: {video_url}")

                        PreviewVideo(video_url, args.view_seconds)

                    except Exception as e:
                        print(f"Upload/preview failed for {company_name}: {e}")

            else:
                print(f"Failed: {company_name}")
