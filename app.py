import os
import sqlite3
import json
import random
import requests
import time
import csv
import io
from functools import wraps
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PLAN_AMOUNT = 500000
PAYSTACK_CURRENCY = "NGN"
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor


def db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)

    conn = sqlite3.connect("studynaija.db")
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=(), one=False, commit=False):
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(sql, params)

            if commit:
                conn.commit()
                result = None
            else:
                result = cur.fetchone() if one else cur.fetchall()

            cur.close()

        else:
            cur = conn.execute(sql, params)

            if commit:
                conn.commit()
                result = None
            else:
                result = cur.fetchone() if one else cur.fetchall()

        return result

    finally:
        conn.close()


def init_db():
    if USE_POSTGRES:

        sql = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            email VARCHAR(180) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            class_level VARCHAR(20) DEFAULT 'SS2',
            role VARCHAR(20) DEFAULT 'student',
            points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            subject VARCHAR(100) NOT NULL,
            class_level VARCHAR(20) NOT NULL,
            term VARCHAR(30) DEFAULT 'First Term',
            topic VARCHAR(200) DEFAULT '',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS quizzes (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            subject VARCHAR(100) NOT NULL,
            class_level VARCHAR(20) NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer VARCHAR(1) NOT NULL,
            explanation TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS question_bank (
            id SERIAL PRIMARY KEY,
            exam VARCHAR(20) NOT NULL,
            year INTEGER NOT NULL,
            subject VARCHAR(100) NOT NULL,
            class_level VARCHAR(20) NOT NULL,
            topic VARCHAR(200) DEFAULT '',
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer VARCHAR(1) NOT NULL,
            explanation TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS exam_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            exam VARCHAR(20) NOT NULL,
            subject VARCHAR(100) NOT NULL,
            class_level VARCHAR(20) NOT NULL,
            total_questions INTEGER NOT NULL,
            duration_seconds INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            submitted_at TIMESTAMP,
            score INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exam_session_questions (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            question_order INTEGER NOT NULL,
            selected_answer VARCHAR(1),
            is_correct BOOLEAN DEFAULT FALSE
        );

        CREATE TABLE IF NOT EXISTS exam_session_questions (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            question_order INTEGER NOT NULL,
            selected_answer VARCHAR(1),
            is_correct BOOLEAN DEFAULT FALSE
        );

        CREATE TABLE IF NOT EXISTS badges (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            badge_key VARCHAR(50) NOT NULL,
            badge_name VARCHAR(100) NOT NULL,
            badge_icon VARCHAR(20) NOT NULL,
            description TEXT NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, badge_key)
        );

        CREATE TABLE IF NOT EXISTS study_activity (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            study_date DATE NOT NULL,
            activities_completed INTEGER NOT NULL DEFAULT 1,
            xp_earned INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, study_date)
        );

        CREATE TABLE IF NOT EXISTS daily_challenges (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT NOT NULL,
            challenge_type VARCHAR(50) NOT NULL,
            target INTEGER NOT NULL DEFAULT 1,
            xp_reward INTEGER NOT NULL DEFAULT 10,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_challenge_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            challenge_date DATE NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            xp_claimed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, challenge_id, challenge_date)
        );

        CREATE TABLE IF NOT EXISTS daily_challenge_bonus (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            bonus_date DATE NOT NULL,
            xp_reward INTEGER NOT NULL DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, bonus_date)
        );

        CREATE TABLE IF NOT EXISTS tutor_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subject VARCHAR(100) NOT NULL DEFAULT 'General',
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        """

    else:

        sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            class_level TEXT DEFAULT 'SS2',
            role TEXT DEFAULT 'student',
            points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            class_level TEXT NOT NULL,
            term TEXT DEFAULT 'First Term',
            topic TEXT DEFAULT '',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            class_level TEXT NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS question_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam TEXT NOT NULL,
            year INTEGER NOT NULL,
            subject TEXT NOT NULL,
            class_level TEXT NOT NULL,
            topic TEXT DEFAULT '',
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS exam_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exam TEXT NOT NULL,
            subject TEXT NOT NULL,
            class_level TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            duration_seconds INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            submitted_at TIMESTAMP,
            score INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exam_session_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            question_order INTEGER NOT NULL,
            selected_answer TEXT,
            is_correct INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exam_session_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            question_order INTEGER NOT NULL,
            selected_answer TEXT,
            is_correct INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            badge_key TEXT NOT NULL,
            badge_name TEXT NOT NULL,
            badge_icon TEXT NOT NULL,
            description TEXT NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, badge_key)
        );

        CREATE TABLE IF NOT EXISTS study_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            study_date DATE NOT NULL,
            activities_completed INTEGER NOT NULL DEFAULT 1,
            xp_earned INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, study_date)
        );

        CREATE TABLE IF NOT EXISTS daily_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            challenge_type TEXT NOT NULL,
            target INTEGER NOT NULL DEFAULT 1,
            xp_reward INTEGER NOT NULL DEFAULT 10,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_challenge_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            challenge_date DATE NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            xp_claimed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, challenge_id, challenge_date)
        );

        CREATE TABLE IF NOT EXISTS daily_challenge_bonus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bonus_date DATE NOT NULL,
            xp_reward INTEGER NOT NULL DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, bonus_date)
        );

        CREATE TABLE IF NOT EXISTS tutor_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL DEFAULT 'General',
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        """

    conn = db()

    try:

        if USE_POSTGRES:

            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()

        else:

            conn.executescript(sql)
            conn.commit()

    finally:
        conn.close()

    admin_email = os.getenv(
        "ADMIN_EMAIL",
        "admin@studynaija.com"
    )

    admin_password = os.getenv(
        "ADMIN_PASSWORD",
        "Samtee15"
    )

    existing_sql = (
        "SELECT id FROM users WHERE email = %s"
        if USE_POSTGRES
        else
        "SELECT id FROM users WHERE email = ?"
    )

    existing = query(
        existing_sql,
        (admin_email,),
        one=True
    )

    if not existing:

        insert_sql = """
        INSERT INTO users
        (name,email,password,class_level,role)
        VALUES (%s,%s,%s,%s,%s)
        """ if USE_POSTGRES else """
        INSERT INTO users
        (name,email,password,class_level,role)
        VALUES (?,?,?,?,?)
        """

        query(
            insert_sql,
            (
                "StudyNaija Admin",
                admin_email,
                generate_password_hash(admin_password),
                "SS2",
                "admin"
            ),
            commit=True
        )


init_db()

def upgrade_payments_table():

    conn = db()

    try:

        if USE_POSTGRES:

            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    reference VARCHAR(120) UNIQUE NOT NULL,
                    amount INTEGER NOT NULL,
                    currency VARCHAR(10) NOT NULL DEFAULT 'NGN',
                    status VARCHAR(30) NOT NULL DEFAULT 'pending',
                    paid_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            cur.close()

        else:

            conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reference TEXT UNIQUE NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'NGN',
                    status TEXT NOT NULL DEFAULT 'pending',
                    paid_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            conn.commit()

    finally:

        conn.close()


upgrade_payments_table()

def upgrade_users_plan_column():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()

            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS plan
                VARCHAR(20) NOT NULL DEFAULT 'free'
            """)

            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS premium_expires_at
                TIMESTAMP
            """)

            conn.commit()
            cur.close()

        else:
            columns = conn.execute(
                "PRAGMA table_info(users)"
            ).fetchall()

            column_names = [
                column[1] for column in columns
            ]

            if "plan" not in column_names:
                conn.execute("""
                    ALTER TABLE users
                    ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'
                """)

            if "premium_expires_at" not in column_names:
                conn.execute("""
                    ALTER TABLE users
                    ADD COLUMN premium_expires_at TIMESTAMP
                """)

            conn.commit()

    finally:
        conn.close()


upgrade_users_plan_column()


def init_ai_quiz_tables():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_quiz_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    subject VARCHAR(100) NOT NULL,
                    topic VARCHAR(200) NOT NULL,
                    class_level VARCHAR(20) NOT NULL,
                    difficulty VARCHAR(20) NOT NULL,
                    total_questions INTEGER NOT NULL,
                    score INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_quiz_questions (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER NOT NULL
                        REFERENCES ai_quiz_sessions(id) ON DELETE CASCADE,
                    question TEXT NOT NULL,
                    option_a TEXT NOT NULL,
                    option_b TEXT NOT NULL,
                    option_c TEXT NOT NULL,
                    option_d TEXT NOT NULL,
                    correct_answer VARCHAR(1) NOT NULL,
                    explanation TEXT DEFAULT ''
                )
            """)

            conn.commit()
            cur.close()

        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_quiz_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    class_level TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    score INTEGER DEFAULT 0,
                    completed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_quiz_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    option_a TEXT NOT NULL,
                    option_b TEXT NOT NULL,
                    option_c TEXT NOT NULL,
                    option_d TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    explanation TEXT DEFAULT '',
                    FOREIGN KEY (session_id) REFERENCES ai_quiz_sessions(id) ON DELETE CASCADE
                )
            """)

            conn.commit()

    finally:
        conn.close()


init_ai_quiz_tables()


def upgrade_user_columns():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS last_login TIMESTAMP
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS total_quizzes INTEGER NOT NULL DEFAULT 0
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS total_exams INTEGER NOT NULL DEFAULT 0
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS total_questions_answered INTEGER NOT NULL DEFAULT 0
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS total_correct_answers INTEGER NOT NULL DEFAULT 0
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS current_streak INTEGER NOT NULL DEFAULT 0
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS longest_streak INTEGER NOT NULL DEFAULT 0
            """)
            conn.commit()
            cur.close()
        else:
            columns = conn.execute("PRAGMA table_info(users)").fetchall()
            column_names = [column[1] for column in columns]

            additions = {
                "last_login": "TIMESTAMP",
                "total_quizzes": "INTEGER NOT NULL DEFAULT 0",
                "total_exams": "INTEGER NOT NULL DEFAULT 0",
                "total_questions_answered": "INTEGER NOT NULL DEFAULT 0",
                "total_correct_answers": "INTEGER NOT NULL DEFAULT 0",
                "current_streak": "INTEGER NOT NULL DEFAULT 0",
                "longest_streak": "INTEGER NOT NULL DEFAULT 0",
            }

            for name, definition in additions.items():
                if name not in column_names:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

            conn.commit()

    finally:
        conn.close()


upgrade_user_columns()


def upgrade_notes_table():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS term VARCHAR(30) DEFAULT 'First Term'")
            cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS topic VARCHAR(200) DEFAULT ''")
            conn.commit()
            cur.close()
        else:
            columns = conn.execute("PRAGMA table_info(notes)").fetchall()
            column_names = [column[1] for column in columns]

            if "term" not in column_names:
                conn.execute("ALTER TABLE notes ADD COLUMN term TEXT DEFAULT 'First Term'")

            if "topic" not in column_names:
                conn.execute("ALTER TABLE notes ADD COLUMN topic TEXT DEFAULT ''")

            conn.commit()
    finally:
        conn.close()


upgrade_notes_table()


def upgrade_exam_question_fk():
    return


def upgrade_user_premium_columns():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR(20) NOT NULL DEFAULT 'free'")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_expires_at TIMESTAMP")
            conn.commit()
            cur.close()
        else:
            columns = conn.execute("PRAGMA table_info(users)").fetchall()
            names = [column[1] for column in columns]
            if "plan" not in names:
                conn.execute("ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
            if "premium_expires_at" not in names:
                conn.execute("ALTER TABLE users ADD COLUMN premium_expires_at TIMESTAMP")
            conn.commit()
    finally:
        conn.close()


upgrade_user_premium_columns()


def ensure_exam_tables():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS exam_results (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    exam VARCHAR(20) NOT NULL,
                    subject VARCHAR(100) NOT NULL,
                    class_level VARCHAR(20) NOT NULL,
                    score INTEGER NOT NULL,
                    total_questions INTEGER NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cur.close()
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exam_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    exam TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    class_level TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    total_questions INTEGER NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
    finally:
        conn.close()


ensure_exam_tables()


def current_user():
    if "user_id" not in session:
        return None

    sql = (
        "SELECT * FROM users WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM users WHERE id = ?"
    )

    return query(
        sql,
        (session["user_id"],),
        one=True
    )


@app.context_processor
def inject_user():
    return {
        "current_user": current_user()
    }


def login_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return route(*args, **kwargs)

    return wrapper


def admin_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user or user["role"] != "admin":
            flash("Admin access required.")
            return redirect(url_for("dashboard"))

        return route(*args, **kwargs)

    return wrapper


def premium_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            return redirect(url_for("login"))

        if user["role"] == "admin":
            return route(*args, **kwargs)

        plan = user["plan"] if "plan" in user.keys() else "free"
        expires_at = user["premium_expires_at"] if "premium_expires_at" in user.keys() else None

        if plan != "premium":
            flash("Premium membership required.")
            return redirect(url_for("premium"))

        if expires_at:
            from datetime import datetime
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at)
                except Exception:
                    expires_at = None
            if expires_at and expires_at < datetime.utcnow():
                flash("Your Premium membership has expired.")
                return redirect(url_for("premium"))

        return route(*args, **kwargs)

    return wrapper


def ensure_study_activity(user_id, xp=0):
    from datetime import date
    today = date.today()

    if USE_POSTGRES:
        query("""
            INSERT INTO study_activity
            (user_id, study_date, activities_completed, xp_earned)
            VALUES (%s, %s, 1, %s)
            ON CONFLICT (user_id, study_date)
            DO UPDATE SET
                activities_completed = study_activity.activities_completed + 1,
                xp_earned = study_activity.xp_earned + EXCLUDED.xp_earned
        """, (user_id, today, xp), commit=True)
    else:
        existing = query("""
            SELECT id FROM study_activity
            WHERE user_id = ? AND study_date = ?
        """, (user_id, today), one=True)

        if existing:
            query("""
                UPDATE study_activity
                SET activities_completed = activities_completed + 1,
                    xp_earned = xp_earned + ?
                WHERE id = ?
            """, (xp, existing["id"]), commit=True)
        else:
            query("""
                INSERT INTO study_activity
                (user_id, study_date, activities_completed, xp_earned)
                VALUES (?, ?, 1, ?)
            """, (user_id, today, xp), commit=True)


def add_xp(user_id, amount):
    query(
        "UPDATE users SET points = points + %s WHERE id = %s"
        if USE_POSTGRES
        else
        "UPDATE users SET points = points + ? WHERE id = ?",
        (amount, user_id),
        commit=True
    )

    ensure_study_activity(user_id, amount)


def record_quiz_activity(user_id, correct, total):
    query(
        """
        UPDATE users
        SET total_quizzes = total_quizzes + 1,
            total_questions_answered = total_questions_answered + %s,
            total_correct_answers = total_correct_answers + %s
        WHERE id = %s
        """ if USE_POSTGRES else """
        UPDATE users
        SET total_quizzes = total_quizzes + 1,
            total_questions_answered = total_questions_answered + ?,
            total_correct_answers = total_correct_answers + ?
        WHERE id = ?
        """,
        (total, correct, user_id),
        commit=True
    )


def record_exam_activity(user_id, correct, total):
    query(
        """
        UPDATE users
        SET total_exams = total_exams + 1,
            total_questions_answered = total_questions_answered + %s,
            total_correct_answers = total_correct_answers + %s
        WHERE id = %s
        """ if USE_POSTGRES else """
        UPDATE users
        SET total_exams = total_exams + 1,
            total_questions_answered = total_questions_answered + ?,
            total_correct_answers = total_correct_answers + ?
        WHERE id = ?
        """,
        (total, correct, user_id),
        commit=True
    )


def update_streak(user_id):
    from datetime import date, timedelta

    today = date.today()

    rows = query(
        """
        SELECT study_date
        FROM study_activity
        WHERE user_id = %s
        ORDER BY study_date DESC
        LIMIT 60
        """ if USE_POSTGRES else """
        SELECT study_date
        FROM study_activity
        WHERE user_id = ?
        ORDER BY study_date DESC
        LIMIT 60
        """,
        (user_id,)
    )

    dates = []

    for row in rows:
        value = row["study_date"]
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except Exception:
                continue
        dates.append(value)

    if not dates:
        return

    current_streak = 0
    cursor = today

    for value in dates:
        if value == cursor:
            current_streak += 1
            cursor -= timedelta(days=1)
        elif value < cursor:
            break

    previous = query(
        "SELECT longest_streak FROM users WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT longest_streak FROM users WHERE id = ?",
        (user_id,),
        one=True
    )

    longest = previous["longest_streak"] if previous else 0
    longest = max(longest, current_streak)

    query(
        """
        UPDATE users
        SET current_streak = %s,
            longest_streak = %s
        WHERE id = %s
        """ if USE_POSTGRES else """
        UPDATE users
        SET current_streak = ?,
            longest_streak = ?
        WHERE id = ?
        """,
        (current_streak, longest, user_id),
        commit=True
    )


def award_badge(user_id, badge_key, badge_name, badge_icon, description):
    if USE_POSTGRES:
        query("""
            INSERT INTO badges
            (user_id, badge_key, badge_name, badge_icon, description)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (user_id, badge_key) DO NOTHING
        """, (user_id, badge_key, badge_name, badge_icon, description), commit=True)
    else:
        existing = query("""
            SELECT id FROM badges
            WHERE user_id = ? AND badge_key = ?
        """, (user_id, badge_key), one=True)
        if not existing:
            query("""
                INSERT INTO badges
                (user_id, badge_key, badge_name, badge_icon, description)
                VALUES (?,?,?,?,?)
            """, (user_id, badge_key, badge_name, badge_icon, description), commit=True)


def check_and_award_badges(user_id):
    user = query(
        "SELECT * FROM users WHERE id = %s" if USE_POSTGRES else "SELECT * FROM users WHERE id = ?",
        (user_id,),
        one=True
    )

    if not user:
        return

    if user["points"] >= 100:
        award_badge(user_id, "xp100", "100 XP", "⭐", "Earned 100 XP.")

    if user["points"] >= 500:
        award_badge(user_id, "xp500", "500 XP", "🏆", "Earned 500 XP.")

    if user["total_quizzes"] >= 10:
        award_badge(user_id, "quiz10", "Quiz Master", "🧠", "Completed 10 quizzes.")

    if user["total_exams"] >= 5:
        award_badge(user_id, "exam5", "Exam Ready", "📚", "Completed 5 exams.")

    if user["current_streak"] >= 7:
        award_badge(user_id, "streak7", "7 Day Streak", "🔥", "Studied for 7 consecutive days.")


def get_daily_challenges():
    rows = query("""
        SELECT * FROM daily_challenges
        WHERE active = 1
        ORDER BY id ASC
    """)

    if rows:
        return rows

    defaults = [
        ("Quick Quiz", "Answer 5 quiz questions today.", "quiz_questions", 5, 20),
        ("Study Notes", "Open 2 lesson notes today.", "notes_opened", 2, 15),
        ("Daily Exam", "Complete 1 exam today.", "exam_completed", 1, 25),
    ]

    for title, description, challenge_type, target, reward in defaults:
        if USE_POSTGRES:
            query("""
                INSERT INTO daily_challenges
                (title, description, challenge_type, target, xp_reward)
                VALUES (%s,%s,%s,%s,%s)
            """, (title, description, challenge_type, target, reward), commit=True)
        else:
            query("""
                INSERT INTO daily_challenges
                (title, description, challenge_type, target, xp_reward)
                VALUES (?,?,?,?,?)
            """, (title, description, challenge_type, target, reward), commit=True)

    return query("""
        SELECT * FROM daily_challenges
        WHERE active = 1
        ORDER BY id ASC
    """)


def update_challenge_progress(user_id, challenge_type, amount=1):
    from datetime import date
    today = date.today()

    challenges = query(
        """
        SELECT * FROM daily_challenges
        WHERE active = 1 AND challenge_type = %s
        """ if USE_POSTGRES else """
        SELECT * FROM daily_challenges
        WHERE active = 1 AND challenge_type = ?
        """,
        (challenge_type,)
    )

    for challenge in challenges:
        existing = query(
            """
            SELECT * FROM daily_challenge_progress
            WHERE user_id = %s AND challenge_id = %s AND challenge_date = %s
            """ if USE_POSTGRES else """
            SELECT * FROM daily_challenge_progress
            WHERE user_id = ? AND challenge_id = ? AND challenge_date = ?
            """,
            (user_id, challenge["id"], today),
            one=True
        )

        if existing:
            new_progress = min(
                challenge["target"],
                existing["progress"] + amount
            )

            completed = 1 if new_progress >= challenge["target"] else existing["completed"]

            query(
                """
                UPDATE daily_challenge_progress
                SET progress = %s,
                    completed = %s
                WHERE id = %s
                """ if USE_POSTGRES else """
                UPDATE daily_challenge_progress
                SET progress = ?,
                    completed = ?
                WHERE id = ?
                """,
                (new_progress, completed, existing["id"]),
                commit=True
            )
        else:
            new_progress = min(amount, challenge["target"])
            completed = 1 if new_progress >= challenge["target"] else 0

            if USE_POSTGRES:
                query("""
                    INSERT INTO daily_challenge_progress
                    (user_id, challenge_id, challenge_date, progress, completed)
                    VALUES (%s,%s,%s,%s,%s)
                """, (user_id, challenge["id"], today, new_progress, completed), commit=True)
            else:
                query("""
                    INSERT INTO daily_challenge_progress
                    (user_id, challenge_id, challenge_date, progress, completed)
                    VALUES (?,?,?,?,?)
                """, (user_id, challenge["id"], today, new_progress, completed), commit=True)


def demo_tutor(question, subject, class_level):
    q = question.lower()

    if "newton" in q:
        return (
            "Newton's laws explain motion. First law: an object remains at rest "
            "or in uniform motion unless acted on by an external force. Second "
            "law: F = ma. Third law: for every action there is an equal and "
            "opposite reaction."
        )

    if "photosynthesis" in q:
        return (
            "Photosynthesis is the process by which green plants make food using "
            "sunlight, carbon dioxide and water. It takes place mainly in the "
            "chlorophyll-containing chloroplasts."
        )

    if "ohm" in q:
        return (
            "Ohm's law states that current through a conductor is directly "
            "proportional to potential difference, provided temperature and "
            "other physical conditions remain constant. The formula is V = IR."
        )

    if "quadratic" in q:
        return (
            "For ax² + bx + c = 0, the quadratic formula is x = "
            "(-b ± √(b² - 4ac)) / 2a."
        )

    return (
        f"This is a demo StudyNaija Tutor response for {subject} at {class_level}. "
        "Connect the AI API to receive full AI-generated explanations."
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        class_level = request.form.get("class_level", "SS2")

        if not name or not email or len(password) < 6:
            flash("Please provide a valid name, email and password of at least 6 characters.")
            return redirect(url_for("register"))

        existing = query(
            "SELECT id FROM users WHERE email = %s" if USE_POSTGRES else "SELECT id FROM users WHERE email = ?",
            (email,),
            one=True
        )

        if existing:
            flash("An account with that email already exists.")
            return redirect(url_for("login"))

        insert_sql = """
            INSERT INTO users (name,email,password,class_level,role)
            VALUES (%s,%s,%s,%s,%s)
        """ if USE_POSTGRES else """
            INSERT INTO users (name,email,password,class_level,role)
            VALUES (?,?,?,?,?)
        """

        query(
            insert_sql,
            (
                name,
                email,
                generate_password_hash(password),
                class_level,
                "student"
            ),
            commit=True
        )

        flash("Account created successfully. Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = query(
            "SELECT * FROM users WHERE email = %s" if USE_POSTGRES else "SELECT * FROM users WHERE email = ?",
            (email,),
            one=True
        )

        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]

        if USE_POSTGRES:
            query(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                (user["id"],),
                commit=True
            )
        else:
            query(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (user["id"],),
                commit=True
            )

        if user["role"] == "admin":
            return redirect(url_for("admin"))

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    update_streak(user["id"])
    check_and_award_badges(user["id"])
    user = current_user()

    return render_template(
        "dashboard.html",
        user=user
    )


@app.route("/profile")
@login_required
def profile():
    user = current_user()
    badges = query(
        "SELECT * FROM badges WHERE user_id = %s ORDER BY earned_at DESC"
        if USE_POSTGRES
        else
        "SELECT * FROM badges WHERE user_id = ? ORDER BY earned_at DESC",
        (user["id"],)
    )

    return render_template(
        "profile.html",
        user=user,
        badges=badges
    )


@app.route("/notes")
@login_required
def notes():
    user = current_user()
    subject = request.args.get("subject", "").strip()
    term = request.args.get("term", "").strip()
    search = request.args.get("search", "").strip()

    if USE_POSTGRES:
        sql = """
            SELECT * FROM notes
            WHERE class_level = %s
        """
    else:
        sql = """
            SELECT * FROM notes
            WHERE class_level = ?
        """

    params = [user["class_level"]]

    if subject:
        sql += " AND subject = " + ("%s" if USE_POSTGRES else "?")
        params.append(subject)

    if term:
        sql += " AND term = " + ("%s" if USE_POSTGRES else "?")
        params.append(term)

    if search:
        if USE_POSTGRES:
            sql += " AND (title ILIKE %s OR subject ILIKE %s OR topic ILIKE %s)"
        else:
            sql += " AND (title LIKE ? OR subject LIKE ? OR topic LIKE ?)"

        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    sql += " ORDER BY subject, term, title"

    rows = query(sql, tuple(params))

    return render_template(
        "notes.html",
        notes=rows,
        subject=subject,
        term=term,
        search=search
    )


@app.route("/notes/<int:note_id>")
@login_required
def note_detail(note_id):
    user = current_user()

    row = query(
        """
        SELECT * FROM notes
        WHERE id = %s AND class_level = %s
        """ if USE_POSTGRES else """
        SELECT * FROM notes
        WHERE id = ? AND class_level = ?
        """,
        (note_id, user["class_level"]),
        one=True
    )

    if not row:
        flash("Note not found.")
        return redirect(url_for("notes"))

    ensure_study_activity(user["id"], 0)
    update_challenge_progress(user["id"], "notes_opened", 1)

    return render_template(
        "note_detail.html",
        note=row
    )


@app.route("/quiz")
@login_required
def quiz():
    user = current_user()
    subject = request.args.get("subject", "").strip()

    if USE_POSTGRES:
        sql = """
            SELECT * FROM quizzes
            WHERE class_level = %s
        """
    else:
        sql = """
            SELECT * FROM quizzes
            WHERE class_level = ?
        """

    params = [user["class_level"]]

    if subject:
        sql += " AND subject = " + ("%s" if USE_POSTGRES else "?")
        params.append(subject)

    sql += " ORDER BY id DESC"

    rows = query(sql, tuple(params))

    return render_template(
        "quiz.html",
        quizzes=rows,
        subject=subject
    )


@app.route("/quiz/<int:quiz_id>", methods=["GET", "POST"])
@login_required
def take_quiz(quiz_id):
    user = current_user()

    quiz_row = query(
        "SELECT * FROM quizzes WHERE id = %s AND class_level = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM quizzes WHERE id = ? AND class_level = ?",
        (quiz_id, user["class_level"]),
        one=True
    )

    if not quiz_row:
        flash("Quiz not found.")
        return redirect(url_for("quiz"))

    if request.method == "POST":
        answer = request.form.get("answer", "").upper()
        correct = answer == quiz_row["answer"].upper()

        record_quiz_activity(user["id"], 1 if correct else 0, 1)

        if correct:
            add_xp(user["id"], 10)
            flash("Correct! You earned 10 XP.")
        else:
            flash(
                f"Not quite. The correct answer is {quiz_row['answer']}. "
                f"{quiz_row['explanation']}"
            )

        update_challenge_progress(user["id"], "quiz_questions", 1)
        update_streak(user["id"])
        check_and_award_badges(user["id"])

        return redirect(url_for("quiz"))

    return render_template(
        "take_quiz.html",
        quiz=quiz_row
    )


@app.route("/challenges")
@login_required
def challenges():
    user = current_user()
    rows = query("""
        SELECT name, points, class_level
        FROM users
        WHERE role = 'student'
        ORDER BY points DESC, name ASC
        LIMIT 50
    """)

    daily = get_daily_challenges()
    from datetime import date
    today = date.today()

    progress = query(
        """
        SELECT p.*, c.title, c.description, c.target, c.xp_reward
        FROM daily_challenge_progress p
        JOIN daily_challenges c ON c.id = p.challenge_id
        WHERE p.user_id = %s AND p.challenge_date = %s
        ORDER BY p.id ASC
        """ if USE_POSTGRES else """
        SELECT p.*, c.title, c.description, c.target, c.xp_reward
        FROM daily_challenge_progress p
        JOIN daily_challenges c ON c.id = p.challenge_id
        WHERE p.user_id = ? AND p.challenge_date = ?
        ORDER BY p.id ASC
        """,
        (user["id"], today)
    )

    return render_template(
        "challenges.html",
        leaderboard=rows,
        daily=daily,
        progress=progress
    )


@app.route("/challenges/claim/<int:challenge_id>", methods=["POST"])
@login_required
def claim_challenge(challenge_id):
    from datetime import date
    user = current_user()
    today = date.today()

    row = query(
        """
        SELECT p.*, c.xp_reward, c.target
        FROM daily_challenge_progress p
        JOIN daily_challenges c ON c.id = p.challenge_id
        WHERE p.user_id = %s
          AND p.challenge_id = %s
          AND p.challenge_date = %s
        """ if USE_POSTGRES else """
        SELECT p.*, c.xp_reward, c.target
        FROM daily_challenge_progress p
        JOIN daily_challenges c ON c.id = p.challenge_id
        WHERE p.user_id = ?
          AND p.challenge_id = ?
          AND p.challenge_date = ?
        """,
        (user["id"], challenge_id, today),
        one=True
    )

    if not row or not row["completed"] or row["xp_claimed"]:
        flash("This challenge is not ready to claim.")
        return redirect(url_for("challenges"))

    query(
        """
        UPDATE daily_challenge_progress
        SET xp_claimed = 1
        WHERE id = %s
        """ if USE_POSTGRES else """
        UPDATE daily_challenge_progress
        SET xp_claimed = 1
        WHERE id = ?
        """,
        (row["id"],),
        commit=True
    )

    add_xp(user["id"], row["xp_reward"])
    flash(f"Challenge complete! You earned {row['xp_reward']} XP.")

    update_streak(user["id"])
    check_and_award_badges(user["id"])

    return redirect(url_for("challenges"))


@app.route("/challenge-history")
@login_required
def challenge_history():
    user = current_user()

    rows = query(
        """
        SELECT p.*, c.title, c.description, c.xp_reward
        FROM daily_challenge_progress p
        JOIN daily_challenges c ON c.id = p.challenge_id
        WHERE p.user_id = %s
        ORDER BY p.challenge_date DESC, p.id DESC
        """ if USE_POSTGRES else """
        SELECT p.*, c.title, c.description, c.xp_reward
        FROM daily_challenge_progress p
        JOIN daily_challenges c ON c.id = p.challenge_id
        WHERE p.user_id = ?
        ORDER BY p.challenge_date DESC, p.id DESC
        """,
        (user["id"],)
    )

    return render_template(
        "challenge_history.html",
        rows=rows
    )


@app.route("/exam-history")
@login_required
def exam_history():
    user = current_user()

    rows = query(
        """
        SELECT * FROM exam_results
        WHERE user_id = %s
        ORDER BY submitted_at DESC
        """ if USE_POSTGRES else """
        SELECT * FROM exam_results
        WHERE user_id = ?
        ORDER BY submitted_at DESC
        """,
        (user["id"],)
    )

    return render_template(
        "exam_history.html",
        rows=rows
    )


@app.route("/tutor", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per minute")
def tutor():
    user = current_user()
    answer = None
    question = ""
    subject = request.form.get("subject", "General")

    if request.method == "POST":
        question = request.form.get("question", "").strip()

        if question:
            if openai_client:
                try:
                    response = openai_client.responses.create(
                        model="gpt-5-mini",
                        input=[
                            {
                                "role": "system",
                                "content": (
                                    "You are StudyNaija Tutor. Explain clearly for a Nigerian secondary school student. "
                                    "Use simple language, step-by-step explanations, examples and exam tips when useful."
                                )
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Student class: {user['class_level']}\n"
                                    f"Subject: {subject}\n"
                                    f"Question: {question}"
                                )
                            }
                        ]
                    )

                    answer = response.output_text
                except Exception:
                    answer = demo_tutor(question, subject, user["class_level"])
            else:
                answer = demo_tutor(question, subject, user["class_level"])

            if answer:
                if USE_POSTGRES:
                    query("""
                        INSERT INTO tutor_history
                        (user_id, subject, question, answer)
                        VALUES (%s,%s,%s,%s)
                    """, (user["id"], subject, question, answer), commit=True)
                else:
                    query("""
                        INSERT INTO tutor_history
                        (user_id, subject, question, answer)
                        VALUES (?,?,?,?)
                    """, (user["id"], subject, question, answer), commit=True)

                add_xp(user["id"], 5)
                update_streak(user["id"])
                check_and_award_badges(user["id"])

    history = query(
        """
        SELECT * FROM tutor_history
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 20
        """ if USE_POSTGRES else """
        SELECT * FROM tutor_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (user["id"],)
    )

    return render_template(
        "tutor.html",
        answer=answer,
        question=question,
        subject=subject,
        history=history
    )


@app.route("/premium")
@login_required
def premium():
    user = current_user()
    return render_template("premium.html", user=user)


@app.route("/paystack/callback")
@login_required
def paystack_callback():
    reference = request.args.get("reference", "").strip()

    if not reference:
        flash("Payment reference missing.")
        return redirect(url_for("premium"))

    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={
                "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json"
            },
            timeout=15
        )
        data = response.json()

        if not data.get("status"):
            flash("Payment verification failed.")
            return redirect(url_for("premium"))

        transaction = data.get("data", {})

        if transaction.get("status") != "success":
            flash("Payment was not successful.")
            return redirect(url_for("premium"))

        user = current_user()
        amount = int(transaction.get("amount", 0))
        currency = transaction.get("currency", "NGN")

        if amount < PAYSTACK_PLAN_AMOUNT or currency != PAYSTACK_CURRENCY:
            flash("Payment amount is invalid.")
            return redirect(url_for("premium"))

        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(days=30)

        if USE_POSTGRES:
            query("""
                INSERT INTO payments
                (user_id, reference, amount, currency, status, paid_at)
                VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (reference) DO NOTHING
            """, (user["id"], reference, amount, currency, "success"), commit=True)

            query("""
                UPDATE users
                SET plan = 'premium', premium_expires_at = %s
                WHERE id = %s
            """, (expires, user["id"]), commit=True)
        else:
            query("""
                INSERT OR IGNORE INTO payments
                (user_id, reference, amount, currency, status, paid_at)
                VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
            """, (user["id"], reference, amount, currency, "success"), commit=True)

            query("""
                UPDATE users
                SET plan = 'premium', premium_expires_at = ?
                WHERE id = ?
            """, (expires, user["id"]), commit=True)

        flash("Payment successful. Premium activated for 30 days.")
        return redirect(url_for("premium"))

    except Exception:
        flash("Payment verification error.")
        return redirect(url_for("premium"))


@app.route("/admin")
@admin_required
def admin():
    students = query("""
        SELECT id, name, email, class_level, role, points, plan,
               premium_expires_at, created_at
        FROM users
        ORDER BY created_at DESC
    """)

    notes_rows = query("""
        SELECT * FROM notes
        ORDER BY id DESC
        LIMIT 100
    """)

    quizzes = query("""
        SELECT * FROM quizzes
        ORDER BY id DESC
        LIMIT 100
    """)

    questions = query("""
        SELECT * FROM question_bank
        ORDER BY id DESC
        LIMIT 100
    """)

    return render_template(
        "admin.html",
        students=students,
        notes=notes_rows,
        quizzes=quizzes,
        questions=questions
    )


@app.route("/admin/note/add", methods=["GET", "POST"])
@admin_required
def admin_add_note():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        class_level = request.form.get("class_level", "SS2").strip()
        term = request.form.get("term", "First Term").strip()
        topic = request.form.get("topic", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not subject or not content:
            flash("Title, subject and content are required.")
            return redirect(url_for("admin_add_note"))

        if USE_POSTGRES:
            query("""
                INSERT INTO notes
                (title, subject, class_level, term, topic, content)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (title, subject, class_level, term, topic, content), commit=True)
        else:
            query("""
                INSERT INTO notes
                (title, subject, class_level, term, topic, content)
                VALUES (?,?,?,?,?,?)
            """, (title, subject, class_level, term, topic, content), commit=True)

        flash("Lesson note added successfully.")
        return redirect(url_for("admin"))

    return render_template("admin_add_note.html")


@app.route("/admin/note/delete/<int:note_id>", methods=["POST"])
@admin_required
def admin_delete_note(note_id):
    query(
        "DELETE FROM notes WHERE id = %s" if USE_POSTGRES else "DELETE FROM notes WHERE id = ?",
        (note_id,),
        commit=True
    )
    flash("Lesson note deleted.")
    return redirect(url_for("admin"))


@app.route("/admin/quiz/add", methods=["GET", "POST"])
@admin_required
def admin_add_quiz():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        class_level = request.form.get("class_level", "SS2").strip()
        question = request.form.get("question", "").strip()
        option_a = request.form.get("option_a", "").strip()
        option_b = request.form.get("option_b", "").strip()
        option_c = request.form.get("option_c", "").strip()
        option_d = request.form.get("option_d", "").strip()
        answer = request.form.get("answer", "").strip().upper()
        explanation = request.form.get("explanation", "").strip()

        if not title or not subject or not question:
            flash("Title, subject and question are required.")
            return redirect(url_for("admin_add_quiz"))

        if answer not in {"A", "B", "C", "D"}:
            flash("Answer must be A, B, C or D.")
            return redirect(url_for("admin_add_quiz"))

        if USE_POSTGRES:
            query("""
                INSERT INTO quizzes
                (title, subject, class_level, question, option_a, option_b,
                 option_c, option_d, answer, explanation)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                title, subject, class_level, question,
                option_a, option_b, option_c, option_d,
                answer, explanation
            ), commit=True)
        else:
            query("""
                INSERT INTO quizzes
                (title, subject, class_level, question, option_a, option_b,
                 option_c, option_d, answer, explanation)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                title, subject, class_level, question,
                option_a, option_b, option_c, option_d,
                answer, explanation
            ), commit=True)

        flash("Quiz added successfully.")
        return redirect(url_for("admin"))

    return render_template("admin_add_quiz.html")


@app.route("/admin/quiz/delete/<int:quiz_id>", methods=["POST"])
@admin_required
def admin_delete_quiz(quiz_id):
    query(
        "DELETE FROM quizzes WHERE id = %s" if USE_POSTGRES else "DELETE FROM quizzes WHERE id = ?",
        (quiz_id,),
        commit=True
    )
    flash("Quiz deleted.")
    return redirect(url_for("admin"))


@app.route("/admin/question/add", methods=["GET", "POST"])
@admin_required
def admin_add_question():
    if request.method == "POST":
        exam = request.form.get("exam", "WAEC").strip().upper()
        year = request.form.get("year", "").strip()
        subject = request.form.get("subject", "").strip()
        class_level = request.form.get("class_level", "SS2").strip()
        topic = request.form.get("topic", "").strip()
        question = request.form.get("question", "").strip()
        option_a = request.form.get("option_a", "").strip()
        option_b = request.form.get("option_b", "").strip()
        option_c = request.form.get("option_c", "").strip()
        option_d = request.form.get("option_d", "").strip()
        answer = request.form.get("answer", "").strip().upper()
        explanation = request.form.get("explanation", "").strip()

        try:
            year_int = int(year)
        except Exception:
            year_int = 0

        if not subject or not question or year_int < 1900:
            flash("Year, subject and question are required.")
            return redirect(url_for("admin_add_question"))

        if answer not in {"A", "B", "C", "D"}:
            flash("Answer must be A, B, C or D.")
            return redirect(url_for("admin_add_question"))

        if USE_POSTGRES:
            query("""
                INSERT INTO question_bank
                (exam, year, subject, class_level, topic, question,
                 option_a, option_b, option_c, option_d, answer, explanation)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                exam, year_int, subject, class_level, topic, question,
                option_a, option_b, option_c, option_d, answer, explanation
            ), commit=True)
        else:
            query("""
                INSERT INTO question_bank
                (exam, year, subject, class_level, topic, question,
                 option_a, option_b, option_c, option_d, answer, explanation)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                exam, year_int, subject, class_level, topic, question,
                option_a, option_b, option_c, option_d, answer, explanation
            ), commit=True)

        flash("Exam question added successfully.")
        return redirect(url_for("admin"))

    return render_template("admin_add_question.html")


@app.route("/admin/question/delete/<int:question_id>", methods=["POST"])
@admin_required
def admin_delete_question(question_id):
    query(
        "DELETE FROM question_bank WHERE id = %s" if USE_POSTGRES else "DELETE FROM question_bank WHERE id = ?",
        (question_id,),
        commit=True
    )
    flash("Exam question deleted.")
    return redirect(url_for("admin"))


@app.route("/admin/student/delete/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_student(user_id):
    user = current_user()

    if user["id"] == user_id:
        flash("You cannot delete your own admin account.")
        return redirect(url_for("admin"))

    target = query(
        "SELECT role FROM users WHERE id = %s" if USE_POSTGRES else "SELECT role FROM users WHERE id = ?",
        (user_id,),
        one=True
    )

    if not target:
        flash("Student not found.")
        return redirect(url_for("admin"))

    if target["role"] == "admin":
        flash("Admin accounts cannot be deleted here.")
        return redirect(url_for("admin"))

    query(
        "DELETE FROM users WHERE id = %s" if USE_POSTGRES else "DELETE FROM users WHERE id = ?",
        (user_id,),
        commit=True
    )

    flash("Student account deleted.")
    return redirect(url_for("admin"))


@app.route("/admin/challenge/add", methods=["GET", "POST"])
@admin_required
def admin_add_challenge():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        challenge_type = request.form.get("challenge_type", "").strip()
        target = request.form.get("target", "1").strip()
        xp_reward = request.form.get("xp_reward", "10").strip()

        try:
            target_int = max(1, int(target))
            reward_int = max(1, int(xp_reward))
        except Exception:
            flash("Target and XP reward must be valid numbers.")
            return redirect(url_for("admin_add_challenge"))

        if not title or not description or not challenge_type:
            flash("Title, description and challenge type are required.")
            return redirect(url_for("admin_add_challenge"))

        if USE_POSTGRES:
            query("""
                INSERT INTO daily_challenges
                (title, description, challenge_type, target, xp_reward)
                VALUES (%s,%s,%s,%s,%s)
            """, (title, description, challenge_type, target_int, reward_int), commit=True)
        else:
            query("""
                INSERT INTO daily_challenges
                (title, description, challenge_type, target, xp_reward)
                VALUES (?,?,?,?,?)
            """, (title, description, challenge_type, target_int, reward_int), commit=True)

        flash("Daily challenge added.")
        return redirect(url_for("admin"))

    return render_template("admin_add_challenge.html")


if __name__ == "__main__":
    app.run(debug=True)
