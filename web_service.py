
import os
import time
import uuid
import psycopg2
from pathlib import Path

from flask import Flask, request, jsonify, g, send_from_directory
from werkzeug.utils import secure_filename
from psycopg2 import OperationalError

UPLOAD_FOLDER = Path(__file__).resolve().parent / "uploads"

app = Flask(__name__)


def connect_db():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )


def get_db():
    if "db" not in g:
        g.db = connect_db()

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    UPLOAD_FOLDER.mkdir(exist_ok=True)

    for attempt in range(30):
        db = None

        try:
            db = connect_db()

            with db.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS videos (
                        id SERIAL PRIMARY KEY,
                        company_name TEXT NOT NULL UNIQUE,
                        file_path TEXT NOT NULL,
                        video_url TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS video_jobs (
                        id SERIAL PRIMARY KEY,
                        video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id),
                        processed_video_url TEXT,
                        status TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN (
                                'pending',
                                'processing',
                                'completed',
                                'failed'
                            )),
                        error TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """)

            db.commit()
            return

        except OperationalError:
            if attempt == 29:
                raise

            time.sleep(2)

        finally:
            if db is not None:
                db.close()


@app.route("/upload", methods=["POST"])
def upload_video():
    file = request.files.get("file")
    zoom_data = request.files.get("zoom_data")
    company_name = request.form.get("company_name", "").strip()

    if not file or not file.filename:
        return jsonify({"error": "No video file provided"}), 400

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400

    safe_name = secure_filename(company_name)

    if not safe_name:
        return jsonify({"error": "Invalid company name"}), 400

    filename = f"{safe_name}.webm"
    file_path = UPLOAD_FOLDER / filename
    zoom_data_path = Path(f"{file_path}.zoom.json")

    video_url = f"{request.host_url.rstrip('/')}/media/{filename}"

    db = get_db()

    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO videos (company_name, file_path, video_url)
            VALUES (%s, %s, %s)
            ON CONFLICT (company_name) DO UPDATE SET
                updated_at = NOW()
            RETURNING id
        """, (
            company_name,
            str(file_path.resolve()),
            video_url
        ))

        video_id = cursor.fetchone()[0]

        file.save(file_path)

        if zoom_data and zoom_data.filename:
            zoom_data.save(zoom_data_path)
            cursor.execute("""
                INSERT INTO video_jobs (video_id)
                VALUES (%s)
                ON CONFLICT (video_id) DO UPDATE SET
                    processed_video_url = NULL,
                    status = 'pending',
                    error = NULL,
                    updated_at = NOW()
                RETURNING id
            """, (video_id,))

            job_id = cursor.fetchone()[0]
        else:
            zoom_data_path.unlink(missing_ok=True)

            zoomed_video_path = file_path.with_name(
                f"{file_path.stem}_zoomed{file_path.suffix}"
            )
            zoomed_video_path.unlink(missing_ok=True)

            cursor.execute("""
                DELETE FROM video_jobs
                WHERE video_id = %s
            """, (video_id,))

            job_id = None


    db.commit()

    return jsonify({
        "company_name": company_name,
        "video_id": video_id,
        "job_id": job_id,
        "video_url": video_url,
        "status": "pending" if job_id is not None else "completed"
    }), 202


@app.route("/jobs/<int:job_id>", methods=["GET"])
def get_job_status(job_id):
    db = get_db()

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT
                video_jobs.id,
                videos.company_name,
                videos.video_url,
                video_jobs.status,
                video_jobs.processed_video_url,
                video_jobs.error,
                video_jobs.created_at,
                video_jobs.updated_at
            FROM video_jobs
            JOIN videos ON videos.id = video_jobs.video_id
            WHERE video_jobs.id = %s
        """, (job_id,))

        job = cursor.fetchone()

    if job is None:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job[0],
        "company_name": job[1],
        "video_url": job[2],
        "status": job[3],
        "processed_video_url": job[4],
        "error": job[5],
        "created_at": job[6].isoformat(),
        "updated_at": job[7].isoformat()
    })


@app.route("/get_video_url", methods=["GET"])
def get_video_url():
    company_name = request.args.get("company_name", "").strip()

    db = get_db()

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT
                videos.id,
                videos.video_url,
                video_jobs.id,
                video_jobs.status,
                video_jobs.processed_video_url
            FROM videos
            LEFT JOIN video_jobs ON video_jobs.video_id = videos.id
            WHERE videos.company_name = %s
            ORDER BY videos.created_at DESC
            LIMIT 1
        """, (company_name,))

        video = cursor.fetchone()

    if video is None:
        return jsonify({"error": "Video not found"}), 404

    return jsonify({
        "video_id": video[0],
        "video_url": video[1],
        "job_id": video[2],
        "status": video[3],
        "processed_video_url": video[4]
    })


@app.route("/media/<filename>", methods=["GET"])
def serve_video(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    init_db()

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "8000"))

    app.run(host=host, port=port, threaded=True)
