
import os
import sqlite3
from pathlib import Path

from flask import Flask, request, jsonify, g, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
DATABASE = BASE_DIR / "videos.db"

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["DATABASE"] = DATABASE


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], timeout=5)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout = 5000")

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    UPLOAD_FOLDER.mkdir(exist_ok=True)

    with sqlite3.connect(DATABASE, timeout=5) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL,
                video_url TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


@app.route("/upload", methods=["POST"])
def upload_video():
    file = request.files.get("file")
    company_name = request.form.get("company_name", "").strip()

    if not file or not file.filename:
        return jsonify({"error": "No video file provided"}), 400

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400

    safe_name = secure_filename(company_name) or "video"
    filename = f"{safe_name}.webm"
    file_path = UPLOAD_FOLDER / filename

    file.save(file_path)

    video_url = f"{request.host_url.rstrip('/')}/media/{filename}"

    db = get_db()
    db.execute("""
        INSERT INTO videos (company_name, file_path, video_url)
        VALUES (?, ?, ?)
        ON CONFLICT(company_name) DO UPDATE SET
            updated_at = datetime('now')
    """, (company_name, str(file_path.resolve()), video_url))

    db.commit()

    return jsonify({
        "company_name": company_name,
        "video_url": video_url
    })


@app.route("/get_video_url", methods=["GET"])
def get_video_url():
    company_name = request.args.get("company_name", "").strip()

    db = get_db()
    video = db.execute(
        "SELECT video_url FROM videos WHERE company_name = ?",
        (company_name,)
    ).fetchone()

    if video is None:
        return jsonify({"error": "Video not found"}), 404

    return jsonify({
        "company_name": company_name,
        "video_url": video["video_url"]
    })


@app.route("/media/<filename>", methods=["GET"])
def serve_video(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    init_db()

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "8000"))

    app.run(host=host, port=port, threaded=True)
