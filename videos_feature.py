import os
import base64
import time
import uuid
import requests
import jwt
from functools import wraps
from flask import request, jsonify, render_template, redirect, url_for, flash, session
from app import app, query, USE_POSTGRES, current_user, admin_required, premium_required

MUX_API_BASE = "https://api.mux.com/video/v1"
MAX_VIDEO_SECONDS = 600
MAX_ACTIVE_VIDEOS = 10


def _placeholder():
    return "%s" if USE_POSTGRES else "?"


def _mux_credentials():
    token_id = os.getenv("MUX_TOKEN_ID", "").strip()
    token_secret = os.getenv("MUX_TOKEN_SECRET", "").strip()
    if not token_id or not token_secret:
        raise RuntimeError("Mux API credentials are not configured in Render.")
    return token_id, token_secret


def _mux_request(method, path, payload=None):
    token_id, token_secret = _mux_credentials()
    response = requests.request(
        method,
        MUX_API_BASE + path,
        auth=(token_id, token_secret),
        json=payload,
        timeout=30
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("messages", [])
        except Exception:
            detail = []
        raise RuntimeError("Mux request failed: " + (", ".join(detail) or response.text[:300]))
    if response.status_code == 204 or not response.content:
        return {}
    return response.json().get("data", {})


def init_video_tables():
    conn = app.config.get("VIDEO_DB_CONNECTOR")
    from app import db
    conn = db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS study_videos (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    subject VARCHAR(100) NOT NULL,
                    description TEXT DEFAULT '',
                    creator_name VARCHAR(160) NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    mux_upload_id VARCHAR(120) UNIQUE,
                    mux_asset_id VARCHAR(120),
                    playback_id VARCHAR(120),
                    duration_seconds INTEGER DEFAULT 0,
                    status VARCHAR(30) NOT NULL DEFAULT 'uploading',
                    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS study_video_views (
                    id SERIAL PRIMARY KEY,
                    video_id INTEGER NOT NULL REFERENCES study_videos(id),
                    user_id INTEGER NOT NULL,
                    counted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(video_id, user_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS study_video_watch_sessions (
                    session_key VARCHAR(64) PRIMARY KEY,
                    video_id INTEGER NOT NULL REFERENCES study_videos(id),
                    user_id INTEGER NOT NULL,
                    watched_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
                    last_position DOUBLE PRECISION NOT NULL DEFAULT 0,
                    last_ping_epoch DOUBLE PRECISION
                )
            """)
            conn.commit()
            cur.close()
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS study_videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    creator_name TEXT NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    mux_upload_id TEXT UNIQUE,
                    mux_asset_id TEXT,
                    playback_id TEXT,
                    duration_seconds INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'uploading',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS study_video_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL REFERENCES study_videos(id),
                    user_id INTEGER NOT NULL,
                    counted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(video_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS study_video_watch_sessions (
                    session_key TEXT PRIMARY KEY,
                    video_id INTEGER NOT NULL REFERENCES study_videos(id),
                    user_id INTEGER NOT NULL,
                    watched_seconds REAL NOT NULL DEFAULT 0,
                    last_position REAL NOT NULL DEFAULT 0,
                    last_ping_epoch REAL
                );
            """)
            conn.commit()
    finally:
        conn.close()


init_video_tables()


@app.route("/admin/videos")
@admin_required
def admin_videos():
    videos = query("""
        SELECT v.*,
               (SELECT COUNT(*) FROM study_video_views w WHERE w.video_id = v.id) AS valid_views
        FROM study_videos v
        ORDER BY v.id DESC
        LIMIT 100
    """)
    active_count = query("""
        SELECT COUNT(*) AS total FROM study_videos
        WHERE is_deleted = FALSE AND status IN ('uploading','processing','ready')
    """, one=True)
    return render_template(
        "admin_videos.html",
        videos=videos,
        active_count=(active_count["total"] if active_count else 0),
        max_active=MAX_ACTIVE_VIDEOS
    )


@app.route("/admin/videos/create-upload", methods=["POST"])
@admin_required
def create_video_upload():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    description = request.form.get("description", "").strip()
    creator_name = request.form.get("creator_name", "").strip()
    if not title or not subject or not creator_name:
        return jsonify({"error": "Enter the video title, subject and creator name."}), 400

    active = query("""
        SELECT COUNT(*) AS total FROM study_videos
        WHERE is_deleted = FALSE AND status IN ('uploading','processing','ready')
    """, one=True)
    if active and int(active["total"]) >= MAX_ACTIVE_VIDEOS:
        return jsonify({"error": "There are already 10 active videos. Delete an old video before uploading another."}), 400

    try:
        origin = os.getenv("SITE_URL", request.host_url.rstrip("/")).rstrip("/")
        upload = _mux_request("POST", "/uploads", {
            "cors_origin": origin,
            "new_asset_settings": {
                "playback_policies": ["signed"],
                "video_quality": "basic"
            }
        })
        upload_id = upload.get("id")
        upload_url = upload.get("url")
        if not upload_id or not upload_url:
            raise RuntimeError("Mux did not return an upload URL.")

        p = _placeholder()
        query(
            f"""INSERT INTO study_videos
                (title, subject, description, creator_name, uploaded_by, mux_upload_id, status)
                VALUES ({p},{p},{p},{p},{p},{p},'uploading')""",
            (title, subject, description, creator_name, current_user()["id"], upload_id),
            commit=True
        )
        row = query("SELECT id FROM study_videos WHERE mux_upload_id = " + p, (upload_id,), one=True)
        return jsonify({"video_id": row["id"], "upload_url": upload_url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/videos/check/<int:video_id>")
@admin_required
def check_video_upload(video_id):
    p = _placeholder()
    video = query("SELECT * FROM study_videos WHERE id = " + p, (video_id,), one=True)
    if not video:
        return jsonify({"error": "Video record not found."}), 404
    if video["status"] == "ready":
        return jsonify({"status": "ready"})
    if not video["mux_upload_id"]:
        return jsonify({"error": "Mux upload ID is missing."}), 400

    try:
        upload = _mux_request("GET", "/uploads/" + video["mux_upload_id"])
        asset_id = upload.get("asset_id")
        if not asset_id:
            return jsonify({"status": "uploading"})
        asset = _mux_request("GET", "/assets/" + asset_id)
        asset_status = asset.get("status", "preparing")
        if asset_status == "errored":
            query("UPDATE study_videos SET status='failed' WHERE id=" + p, (video_id,), commit=True)
            return jsonify({"status": "failed", "error": "Mux could not process this video."})
        if asset_status != "ready":
            query("UPDATE study_videos SET status='processing', mux_asset_id=" + p + " WHERE id=" + p,
                  (asset_id, video_id), commit=True)
            return jsonify({"status": "processing"})

        duration = int(float(asset.get("duration") or 0))
        if duration <= 0 or duration > MAX_VIDEO_SECONDS:
            try:
                _mux_request("DELETE", "/assets/" + asset_id)
            except Exception:
                pass
            query("UPDATE study_videos SET status='rejected', mux_asset_id=" + p + " WHERE id=" + p,
                  (asset_id, video_id), commit=True)
            return jsonify({"status": "rejected", "error": "Videos must be 10 minutes or shorter."})

        playback_ids = asset.get("playback_ids") or []
        playback_id = next((item.get("id") for item in playback_ids if item.get("policy") == "signed"), None)
        if not playback_id:
            raise RuntimeError("Mux did not create a signed playback ID.")
        query(
            "UPDATE study_videos SET status='ready', mux_asset_id=" + p +
            ", playback_id=" + p + ", duration_seconds=" + p + " WHERE id=" + p,
            (asset_id, playback_id, duration, video_id),
            commit=True
        )
        return jsonify({"status": "ready"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/videos/delete/<int:video_id>", methods=["POST"])
@admin_required
def delete_study_video(video_id):
    p = _placeholder()
    video = query("SELECT * FROM study_videos WHERE id=" + p, (video_id,), one=True)
    if not video:
        flash("Video not found.", "danger")
        return redirect(url_for("admin_videos"))
    try:
        if video["mux_asset_id"]:
            _mux_request("DELETE", "/assets/" + video["mux_asset_id"])
        query(
            "UPDATE study_videos SET is_deleted=TRUE, status='deleted', playback_id=NULL, deleted_at=CURRENT_TIMESTAMP WHERE id=" + p,
            (video_id,), commit=True
        )
        flash("Video deleted from Mux. Its valid-view record has been kept for creator payment calculations.", "success")
    except Exception as exc:
        flash("Could not delete the video: " + str(exc), "danger")
    return redirect(url_for("admin_videos"))


def _make_playback_token(playback_id):
    key_id = os.getenv("MUX_SIGNING_KEY_ID", "").strip()
    private_key = os.getenv("MUX_SIGNING_PRIVATE_KEY", "").strip()
    if not key_id or not private_key:
        raise RuntimeError("Mux signing key is not configured in Render.")
    if not private_key.startswith("-----BEGIN"):
        try:
            private_key = base64.b64decode(private_key)
        except Exception as exc:
            raise RuntimeError("Mux signing private key must be the original base64 key from Mux.") from exc
    else:
        private_key = private_key.replace("\\n", "\n").encode("utf-8")
    payload = {
        "sub": playback_id,
        "aud": "v",
        "exp": int(time.time()) + 60 * 60
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": key_id})


@app.route("/videos")
@premium_required
def study_videos():
    videos = query("""
        SELECT v.*,
               (SELECT COUNT(*) FROM study_video_views w WHERE w.video_id = v.id) AS valid_views
        FROM study_videos v
        WHERE v.is_deleted = FALSE AND v.status = 'ready'
        ORDER BY v.id DESC
    """)
    return render_template("videos.html", videos=videos)


@app.route("/videos/<int:video_id>")
@premium_required
def study_video_player(video_id):
    p = _placeholder()
    video = query(
        "SELECT * FROM study_videos WHERE id=" + p + " AND is_deleted=FALSE AND status='ready'",
        (video_id,), one=True
    )
    if not video:
        flash("That video is no longer available.", "warning")
        return redirect(url_for("study_videos"))
    try:
        token = _make_playback_token(video["playback_id"])
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("study_videos"))
    already_viewed = query(
        "SELECT id FROM study_video_views WHERE video_id=" + p + " AND user_id=" + p,
        (video_id, current_user()["id"]), one=True
    )
    return render_template(
        "video_player.html",
        video=video,
        playback_token=token,
        already_viewed=bool(already_viewed)
    )


@app.route("/videos/<int:video_id>/watch/start", methods=["POST"])
@premium_required
def start_video_watch(video_id):
    p = _placeholder()
    video = query(
        "SELECT id FROM study_videos WHERE id=" + p + " AND is_deleted=FALSE AND status='ready'",
        (video_id,), one=True
    )
    if not video:
        return jsonify({"error": "Video is unavailable."}), 404
    key = str(uuid.uuid4())
    query(
        "INSERT INTO study_video_watch_sessions (session_key, video_id, user_id, watched_seconds, last_position, last_ping_epoch) VALUES (" +
        p + "," + p + "," + p + ",0,0,NULL)",
        (key, video_id, current_user()["id"]), commit=True
    )
    return jsonify({"session_key": key})


@app.route("/videos/<int:video_id>/watch/progress", methods=["POST"])
@premium_required
def video_watch_progress(video_id):
    data = request.get_json(silent=True) or {}
    key = str(data.get("session_key", ""))
    try:
        position = max(0.0, float(data.get("position", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid playback position."}), 400
    p = _placeholder()
    watch = query(
        "SELECT * FROM study_video_watch_sessions WHERE session_key=" + p + " AND video_id=" + p + " AND user_id=" + p,
        (key, video_id, current_user()["id"]), one=True
    )
    video = query(
        "SELECT duration_seconds FROM study_videos WHERE id=" + p + " AND is_deleted=FALSE AND status='ready'",
        (video_id,), one=True
    )
    if not watch or not video:
        return jsonify({"error": "Watch session not found."}), 404

    now = time.time()
    if data.get("reset"):
        watched = 0.0
    else:
        watched = float(watch["watched_seconds"] or 0)
        previous_ping = watch["last_ping_epoch"]
        previous_position = float(watch["last_position"] or 0)
        if previous_ping is None:
            watched = 0.0
        else:
            elapsed = now - float(previous_ping)
            media_elapsed = position - previous_position
            if 1 <= elapsed <= 8 and 0 < media_elapsed <= 9:
                watched += min(elapsed, media_elapsed)
            else:
                watched = 0.0

    query(
        "UPDATE study_video_watch_sessions SET watched_seconds=" + p +
        ", last_position=" + p + ", last_ping_epoch=" + p + " WHERE session_key=" + p,
        (watched, position, now, key), commit=True
    )

    counted = False
    threshold = float(video["duration_seconds"] or 0) * 0.5
    if threshold > 0 and watched >= threshold:
        query(
            "INSERT INTO study_video_views (video_id, user_id) VALUES (" + p + "," + p +
            ") ON CONFLICT(video_id, user_id) DO NOTHING",
            (video_id, current_user()["id"]), commit=True
        )
        counted = True
    return jsonify({"counted": counted, "watched_seconds": round(watched, 1), "required_seconds": threshold})
