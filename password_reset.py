import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import flash, redirect, render_template, request, url_for

import app as app_module
import payment_fix

from app import app, USE_POSTGRES, generate_password_hash, limiter, query, db

RESET_MINUTES = 30


def ensure_password_reset_table():
    conn = db()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token_hash VARCHAR(64) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def send_reset_email(email, reset_link):
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    mail_from = os.getenv("MAIL_FROM", username).strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    use_ssl = os.getenv("SMTP_USE_SSL", "false").strip().lower() == "true"

    if not host or not username or not password or not mail_from:
        app.logger.error(
            "Password reset email is not configured. Set SMTP_HOST, "
            "SMTP_USERNAME, SMTP_PASSWORD and MAIL_FROM."
        )
        return False

    message = EmailMessage()
    message["Subject"] = "Reset your StudyNaija password"
    message["From"] = mail_from
    message["To"] = email
    message.set_content(
        "Hello,\n\n"
        "We received a request to reset your StudyNaija password.\n\n"
        f"Use this link to choose a new password:\n{reset_link}\n\n"
        f"This link expires in {RESET_MINUTES} minutes and can only be used once.\n\n"
        "If you did not request this, you can safely ignore this email.\n\n"
        "StudyNaija"
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        return True
    except Exception:
        app.logger.exception("Failed to send password reset email")
        return False


ensure_password_reset_table()


@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        generic_message = (
            "If an account with that email exists, a password reset link has been sent. "
            "Check your inbox and spam folder."
        )

        if not email:
            flash(generic_message, "info")
            return redirect(url_for("forgot_password"))

        user_sql = (
            "SELECT id, email FROM users WHERE LOWER(email) = LOWER(%s)"
            if USE_POSTGRES
            else
            "SELECT id, email FROM users WHERE LOWER(email) = LOWER(?)"
        )
        user = query(user_sql, (email,), one=True)

        if not user:
            flash(generic_message, "info")
            return redirect(url_for("forgot_password"))

        invalidate_sql = (
            "UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP "
            "WHERE user_id = %s AND used_at IS NULL"
            if USE_POSTGRES
            else
            "UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND used_at IS NULL"
        )
        query(invalidate_sql, (user["id"],), commit=True)

        raw_token = secrets.token_urlsafe(48)
        digest = token_digest(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_MINUTES)

        insert_sql = (
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, %s)"
            if USE_POSTGRES
            else
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
            "VALUES (?, ?, ?)"
        )
        query(insert_sql, (user["id"], digest, expires_at.isoformat()), commit=True)

        reset_link = url_for("reset_password", token=raw_token, _external=True)
        send_reset_email(user["email"], reset_link)

        flash(generic_message, "info")
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token):
    digest = token_digest(token)

    token_sql = (
        "SELECT id, user_id, expires_at, used_at "
        "FROM password_reset_tokens WHERE token_hash = %s"
        if USE_POSTGRES
        else
        "SELECT id, user_id, expires_at, used_at "
        "FROM password_reset_tokens WHERE token_hash = ?"
    )
    reset_record = query(token_sql, (digest,), one=True)

    if not reset_record or reset_record["used_at"]:
        return render_template("reset_password.html", valid=False)

    expires_value = reset_record["expires_at"]
    if isinstance(expires_value, datetime):
        expires_at = expires_value
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = datetime.fromisoformat(str(expires_value).replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) >= expires_at:
        return render_template("reset_password.html", valid=False)

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Your new password must be at least 6 characters long.", "danger")
            return render_template("reset_password.html", valid=True)

        if password != confirm_password:
            flash("The passwords do not match.", "danger")
            return render_template("reset_password.html", valid=True)

        password_hash = generate_password_hash(password)

        update_user_sql = (
            "UPDATE users SET password = %s WHERE id = %s"
            if USE_POSTGRES
            else
            "UPDATE users SET password = ? WHERE id = ?"
        )
        query(update_user_sql, (password_hash, reset_record["user_id"]), commit=True)

        mark_used_sql = (
            "UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE id = %s"
            if USE_POSTGRES
            else
            "UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE id = ?"
        )
        query(mark_used_sql, (reset_record["id"],), commit=True)

        flash(
            "Your password has been reset successfully. You can now log in with your new password.",
            "success"
        )
        return redirect(url_for("login"))

    return render_template("reset_password.html", valid=True)
