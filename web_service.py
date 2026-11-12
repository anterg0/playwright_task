
import os
import time
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

    file.save(file_path)

    video_url = f"{request.host_url.rstrip('/')}/media/{filename}"

    db = get_db()

    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO videos (company_name, file_path, video_url)
            VALUES (%s, %s, %s)
            ON CONFLICT (company_name) DO UPDATE SET
                updated_at = NOW()
        """, (company_name, os.path.abspath(file_path), video_url))

    db.commit()

    return jsonify({
        "company_name": company_name,
        "video_url": video_url
    })


@app.route("/get_video_url", methods=["GET"])
def get_video_url():
    company_name = request.args.get("company_name", "").strip()

    db = get_db()

    with db.cursor() as cursor:
        cursor.execute(
            "SELECT video_url FROM videos WHERE company_name = %s",
            (company_name,)
        )

        video = cursor.fetchone()

    if video is None:
        return jsonify({"error": "Video not found"}), 404

    return jsonify({
        "company_name": company_name,
        "video_url": video[0]
    })


@app.route("/media/<filename>", methods=["GET"])
def serve_video(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    init_db()

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "8000"))

    app.run(host=host, port=port, threaded=True)
