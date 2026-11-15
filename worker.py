
import os
import sys
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

from web_service import connect_db, init_db

POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))

BASE_DIR = Path(__file__).resolve().parent
APPLY_ZOOM_SCRIPT = BASE_DIR / "apply_zoom.py"


def claim_job():
    db = connect_db()

    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    video_jobs.id,
                    video_jobs.video_id,
                    videos.file_path,
                    videos.video_url
                FROM video_jobs
                JOIN videos ON videos.id = video_jobs.video_id
                WHERE video_jobs.status = 'pending'
                ORDER BY video_jobs.created_at
                LIMIT 1
                FOR UPDATE OF video_jobs SKIP LOCKED
            """)

            job = cursor.fetchone()

            if job is None:
                db.commit()
                return None

            job_id, video_id, file_path, video_url = job

            cursor.execute("""
                UPDATE video_jobs
                SET status = 'processing',
                    error = NULL,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING updated_at
            """, (job_id,))

            claimed_at = cursor.fetchone()[0]

        db.commit()

        return {
            "id": job_id,
            "video_id": video_id,
            "file_path": Path(file_path),
            "video_url": video_url,
            "claimed_at": claimed_at
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def finish_job(job, temp_output, final_output):
    db = connect_db()

    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT status, updated_at
                FROM video_jobs
                WHERE id = %s
                FOR UPDATE
            """, (job["id"],))

            current = cursor.fetchone()

            if (
                current is None
                or current[0] != "processing"
                or current[1] != job["claimed_at"]
            ):
                db.commit()
                return False

            os.replace(temp_output, final_output)

            processed_url = (
                job["video_url"].rsplit("/", 1)[0]
                + "/"
                + final_output.name
            )

            cursor.execute("""
                UPDATE video_jobs
                SET status = 'completed',
                    processed_video_url = %s,
                    error = NULL,
                    updated_at = NOW()
                WHERE id = %s
            """, (processed_url, job["id"]))

        db.commit()
        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def fail_job(job, error):
    db = connect_db()

    try:
        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE video_jobs
                SET status = 'failed',
                    error = %s,
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'processing'
                  AND updated_at = %s
            """, (
                error[-4000:],
                job["id"],
                job["claimed_at"]
            ))

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def process_job(job):
    video_path = job["file_path"]
    zoom_path = Path(f"{video_path}.zoom.json")

    work_dir = None

    try:
        if not video_path.is_file():
            raise FileNotFoundError(f"Video not found: {video_path}")

        if not zoom_path.is_file():
            raise FileNotFoundError(f"Zoom data not found: {zoom_path}")

        work_dir = Path(tempfile.mkdtemp(
            prefix=f".job_{job['id']}_",
            dir=video_path.parent
        ))

        snapshot_video = work_dir / video_path.name
        snapshot_zoom = Path(f"{snapshot_video}.zoom.json")

        shutil.copy2(video_path, snapshot_video)
        shutil.copy2(zoom_path, snapshot_zoom)

        temp_output = work_dir / f"{video_path.stem}_zoomed.webm"

        final_output = video_path.with_name(
            f"{video_path.stem}_zoomed.webm"
        )

        result = subprocess.run(
            [
                sys.executable,
                str(APPLY_ZOOM_SCRIPT),
                "--video",
                str(snapshot_video),
                "--output",
                str(temp_output)
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr or result.stdout or "FFmpeg processing failed"
            )

        if not temp_output.is_file():
            raise RuntimeError("Processed video was not created")

        if finish_job(job, temp_output, final_output):
            print(f"Job {job['id']} completed", flush=True)
        else:
            print(f"Job {job['id']} was superseded by a newer upload", flush=True)

    except Exception as error:
        try:
            fail_job(job, str(error))
        except Exception as db_error:
            print(f"Could not update failed job: {db_error}", flush=True)

        print(f"Job {job['id']} failed: {error}", flush=True)

    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)


def main():
    init_db()

    print("Worker started", flush=True)

    while True:
        try:
            job = claim_job()

            if job is None:
                time.sleep(POLL_INTERVAL)
                continue

            print(f"Processing job {job['id']}", flush=True)
            process_job(job)

        except Exception as error:
            print(f"Worker error: {error}", flush=True)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
