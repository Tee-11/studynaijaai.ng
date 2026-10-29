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
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")
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
                    answer VARCHAR(1) NOT NULL,
                    explanation TEXT DEFAULT '',
                    question_order INTEGER NOT NULL,
                    selected_answer VARCHAR(1),
                    is_correct BOOLEAN DEFAULT FALSE
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
                    FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE
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
                    answer TEXT NOT NULL,
                    explanation TEXT DEFAULT '',
                    question_order INTEGER NOT NULL,
                    selected_answer TEXT,
                    is_correct INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id)
                        REFERENCES ai_quiz_sessions(id) ON DELETE CASCADE
                )
            """)

            conn.commit()

    finally:
        conn.close()


init_ai_quiz_tables()


def upgrade_notes_table():
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()

            cur.execute("""
                ALTER TABLE notes
                ADD COLUMN IF NOT EXISTS term VARCHAR(30)
                DEFAULT 'First Term'
            """)

            cur.execute("""
                ALTER TABLE notes
                ADD COLUMN IF NOT EXISTS topic VARCHAR(200)
                DEFAULT ''
            """)

            conn.commit()
            cur.close()

        else:
            columns = conn.execute(
                "PRAGMA table_info(notes)"
            ).fetchall()

            column_names = [column[1] for column in columns]

            if "term" not in column_names:
                conn.execute("""
                    ALTER TABLE notes
                    ADD COLUMN term TEXT DEFAULT 'First Term'
                """)

            if "topic" not in column_names:
                conn.execute("""
                    ALTER TABLE notes
                    ADD COLUMN topic TEXT DEFAULT ''
                """)

            conn.commit()

    finally:
        conn.close()


upgrade_notes_table()

def current_user():

    if "user_id" not in session:
        return None

    sql = (
        "SELECT * FROM users WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM users WHERE id = ?"
    )

    user = query(
        sql,
        (session["user_id"],),
        one=True
    )

    if not user:
        return None

    if (
        user["plan"] == "premium"
        and user["premium_expires_at"]
    ):

        import datetime

        expires_at = user["premium_expires_at"]

        if isinstance(expires_at, str):
            expires_at = datetime.datetime.fromisoformat(
                expires_at
            )

        if datetime.datetime.now() >= expires_at:

            query(
                """
                UPDATE users
                SET plan = ?, premium_expires_at = NULL
                WHERE id = ?
                """,
                (
                    "free",
                    user["id"]
                ),
                commit=True
            )

            user = query(
                sql,
                (session["user_id"],),
                one=True
            )

    return user

def get_level_info(xp):
    xp = int(xp or 0)

    levels = [
        (1, "Beginner", 0),
        (2, "Learner", 100),
        (3, "Scholar", 250),
        (4, "Achiever", 500),
        (5, "Expert", 1000),
        (6, "Master", 2000),
        (7, "Legend", 4000)
    ]

    current_level = levels[0]

    for level in levels:
        if xp >= level[2]:
            current_level = level
        else:
            break

    level_number = current_level[0]
    level_name = current_level[1]
    level_start = current_level[2]

    if level_number < len(levels):

        next_level = levels[level_number]
        next_level_xp = next_level[2]

    else:

        next_level = None
        next_level_xp = None

    if next_level_xp is not None:

        progress_xp = xp - level_start
        required_xp = next_level_xp - level_start

        progress_percent = round(
            (progress_xp / required_xp) * 100
        )

        progress_percent = max(
            0,
            min(100, progress_percent)
        )

    else:

        progress_xp = 0
        required_xp = 0
        progress_percent = 100

    return {
        "level": level_number,
        "name": level_name,
        "xp": xp,
        "level_start": level_start,
        "next_xp": next_level_xp,
        "progress_xp": progress_xp,
        "required_xp": required_xp,
        "progress_percent": progress_percent
    }

def award_badge(user_id, badge_key, badge_name, badge_icon, description):
    if USE_POSTGRES:
        sql = """
            INSERT INTO badges
            (user_id, badge_key, badge_name, badge_icon, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, badge_key) DO NOTHING
        """
    else:
        sql = """
            INSERT OR IGNORE INTO badges
            (user_id, badge_key, badge_name, badge_icon, description)
            VALUES (?, ?, ?, ?, ?)
        """

    query(
        sql,
        (
            user_id,
            badge_key,
            badge_name,
            badge_icon,
            description
        ),
        commit=True
    )

def record_study_activity(user_id):
    import datetime
    from zoneinfo import ZoneInfo

    today = datetime.datetime.now(
        ZoneInfo("Africa/Lagos")
    ).date()

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor(
                cursor_factory=RealDictCursor
            )

            cur.execute(
                """
                SELECT id
                FROM study_activity
                WHERE user_id = %s
                AND study_date = %s
                """,
                (user_id, today)
            )

            today_record = cur.fetchone()

        else:
            today_record = conn.execute(
                """
                SELECT id
                FROM study_activity
                WHERE user_id = ?
                AND study_date = ?
                """,
                (user_id, today)
            ).fetchone()

        if today_record:

            update_activity_sql = (
                """
                UPDATE study_activity
                SET activities_completed =
                    activities_completed + 1
                WHERE user_id = %s
                AND study_date = %s
                """
                if USE_POSTGRES
                else
                """
                UPDATE study_activity
                SET activities_completed =
                    activities_completed + 1
                WHERE user_id = ?
                AND study_date = ?
                """
            )

            values = (user_id, today)

            if USE_POSTGRES:
                cur.execute(
                    update_activity_sql,
                    values
                )
            else:
                conn.execute(
                    update_activity_sql,
                    values
                )

            conn.commit()

            return 0

        insert_activity_sql = (
            """
            INSERT INTO study_activity
            (
                user_id,
                study_date,
                activities_completed,
                xp_earned
            )
            VALUES (%s, %s, %s, %s)
            """
            if USE_POSTGRES
            else
            """
            INSERT INTO study_activity
            (
                user_id,
                study_date,
                activities_completed,
                xp_earned
            )
            VALUES (?, ?, ?, ?)
            """
        )

        values = (
            user_id,
            today,
            1,
            10
        )

        if USE_POSTGRES:
            cur.execute(
                insert_activity_sql,
                values
            )

            cur.execute(
                """
                UPDATE users
                SET points = points + %s
                WHERE id = %s
                """,
                (10, user_id)
            )

        else:
            conn.execute(
                insert_activity_sql,
                values
            )

            conn.execute(
                """
                UPDATE users
                SET points = points + ?
                WHERE id = ?
                """,
                (10, user_id)
            )

        conn.commit()

        return 10

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def create_default_daily_challenges():
    challenges = [
        (
            "Study a Note",
            "Read at least 1 study note today.",
            "note",
            1,
            10
        ),
        (
            "Answer a Quiz",
            "Complete at least 1 quiz today.",
            "quiz",
            1,
            15
        ),
        (
            "Take an Exam",
            "Complete at least 1 exam today.",
            "exam",
            1,
            25
        ),
        (
            "Study Today",
            "Complete any study activity today.",
            "study",
            1,
            10
        )
    ]

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()

            for challenge in challenges:
                title = challenge[0]

                cur.execute(
                    """
                    SELECT id
                    FROM daily_challenges
                    WHERE title = %s
                    """,
                    (title,)
                )

                existing = cur.fetchone()

                if not existing:
                    cur.execute(
                        """
                        INSERT INTO daily_challenges
                        (
                            title,
                            description,
                            challenge_type,
                            target,
                            xp_reward,
                            active
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            challenge[0],
                            challenge[1],
                            challenge[2],
                            challenge[3],
                            challenge[4],
                            1
                        )
                    )

        else:
            for challenge in challenges:
                title = challenge[0]

                existing = conn.execute(
                    """
                    SELECT id
                    FROM daily_challenges
                    WHERE title = ?
                    """,
                    (title,)
                ).fetchone()

                if not existing:
                    conn.execute(
                        """
                        INSERT INTO daily_challenges
                        (
                            title,
                            description,
                            challenge_type,
                            target,
                            xp_reward,
                            active
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            challenge[0],
                            challenge[1],
                            challenge[2],
                            challenge[3],
                            challenge[4],
                            1
                        )
                    )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

create_default_daily_challenges()

def update_daily_challenges(user_id, activity_type):
    import datetime
    from zoneinfo import ZoneInfo

    today = datetime.datetime.now(
        ZoneInfo("Africa/Lagos")
    ).date()

    challenge_types = [activity_type, "study"]

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor(
                cursor_factory=RealDictCursor
            )

            cur.execute(
                """
                SELECT *
                FROM daily_challenges
                WHERE active = 1
                """
            )

            challenges = cur.fetchall()

        else:
            challenges = conn.execute(
                """
                SELECT *
                FROM daily_challenges
                WHERE active = 1
                """
            ).fetchall()

        for challenge in challenges:

            if challenge["challenge_type"] not in challenge_types:
                continue

            if USE_POSTGRES:
                cur.execute(
                    """
                    SELECT *
                    FROM daily_challenge_progress
                    WHERE user_id = %s
                    AND challenge_id = %s
                    AND challenge_date = %s
                    """,
                    (
                        user_id,
                        challenge["id"],
                        today
                    )
                )

                progress_row = cur.fetchone()

            else:
                progress_row = conn.execute(
                    """
                    SELECT *
                    FROM daily_challenge_progress
                    WHERE user_id = ?
                    AND challenge_id = ?
                    AND challenge_date = ?
                    """,
                    (
                        user_id,
                        challenge["id"],
                        today
                    )
                ).fetchone()

            if progress_row:

                if progress_row["completed"]:
                    continue

                new_progress = min(
                    progress_row["progress"] + 1,
                    challenge["target"]
                )

                completed = (
                    1
                    if new_progress >= challenge["target"]
                    else 0
                )

                if USE_POSTGRES:
                    cur.execute(
                        """
                        UPDATE daily_challenge_progress
                        SET progress = %s,
                            completed = %s
                        WHERE id = %s
                        """,
                        (
                            new_progress,
                            completed,
                            progress_row["id"]
                        )
                    )

                else:
                    conn.execute(
                        """
                        UPDATE daily_challenge_progress
                        SET progress = ?,
                            completed = ?
                        WHERE id = ?
                        """,
                        (
                            new_progress,
                            completed,
                            progress_row["id"]
                        )
                    )

            else:

                completed = (
                    1
                    if 1 >= challenge["target"]
                    else 0
                )

                if USE_POSTGRES:
                    cur.execute(
                        """
                        INSERT INTO daily_challenge_progress
                        (
                            user_id,
                            challenge_id,
                            challenge_date,
                            progress,
                            completed,
                            xp_claimed
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            user_id,
                            challenge["id"],
                            today,
                            1,
                            completed,
                            0
                        )
                    )

                else:
                    conn.execute(
                        """
                        INSERT INTO daily_challenge_progress
                        (
                            user_id,
                            challenge_id,
                            challenge_date,
                            progress,
                            completed,
                            xp_claimed
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            challenge["id"],
                            today,
                            1,
                            completed,
                            0
                        )
                    )

            if completed:

                if USE_POSTGRES:
                    cur.execute(
                        """
                        SELECT xp_claimed
                        FROM daily_challenge_progress
                        WHERE user_id = %s
                        AND challenge_id = %s
                        AND challenge_date = %s
                        """,
                        (
                            user_id,
                            challenge["id"],
                            today
                        )
                    )

                    claimed_row = cur.fetchone()

                else:
                    claimed_row = conn.execute(
                        """
                        SELECT xp_claimed
                        FROM daily_challenge_progress
                        WHERE user_id = ?
                        AND challenge_id = ?
                        AND challenge_date = ?
                        """,
                        (
                            user_id,
                            challenge["id"],
                            today
                        )
                    ).fetchone()

                if not claimed_row["xp_claimed"]:

                    if USE_POSTGRES:
                        cur.execute(
                            """
                            UPDATE users
                            SET points = points + %s
                            WHERE id = %s
                            """,
                            (
                                challenge["xp_reward"],
                                user_id
                            )
                        )

                        cur.execute(
                            """
                            UPDATE daily_challenge_progress
                            SET xp_claimed = 1
                            WHERE user_id = %s
                            AND challenge_id = %s
                            AND challenge_date = %s
                            """,
                            (
                                user_id,
                                challenge["id"],
                                today
                            )
                        )

                    else:
                        conn.execute(
                            """
                            UPDATE users
                            SET points = points + ?
                            WHERE id = ?
                            """,
                            (
                                challenge["xp_reward"],
                                user_id
                            )
                        )

                        conn.execute(
                            """
                            UPDATE daily_challenge_progress
                            SET xp_claimed = 1
                            WHERE user_id = ?
                            AND challenge_id = ?
                            AND challenge_date = ?
                            """,
                            (
                                user_id,
                                challenge["id"],
                                today
                            )
                        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def award_daily_challenge_bonus(user_id):
    import datetime
    from zoneinfo import ZoneInfo

    today = datetime.datetime.now(
        ZoneInfo("Africa/Lagos")
    ).date()

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor(
                cursor_factory=RealDictCursor
            )

            cur.execute(
                """
                SELECT id
                FROM daily_challenge_bonus
                WHERE user_id = %s
                AND bonus_date = %s
                """,
                (user_id, today)
            )

            bonus_exists = cur.fetchone()

        else:
            bonus_exists = conn.execute(
                """
                SELECT id
                FROM daily_challenge_bonus
                WHERE user_id = ?
                AND bonus_date = ?
                """,
                (user_id, today)
            ).fetchone()

        if bonus_exists:
            conn.close()
            return False

        if USE_POSTGRES:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM daily_challenges
                WHERE active = 1
                """
            )

            total_row = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) AS completed
                FROM daily_challenge_progress dcp
                JOIN daily_challenges dc
                ON dc.id = dcp.challenge_id
                WHERE dcp.user_id = %s
                AND dcp.challenge_date = %s
                AND dcp.completed = 1
                AND dc.active = 1
                """,
                (user_id, today)
            )

            completed_row = cur.fetchone()

        else:
            total_row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM daily_challenges
                WHERE active = 1
                """
            ).fetchone()

            completed_row = conn.execute(
                """
                SELECT COUNT(*) AS completed
                FROM daily_challenge_progress dcp
                JOIN daily_challenges dc
                ON dc.id = dcp.challenge_id
                WHERE dcp.user_id = ?
                AND dcp.challenge_date = ?
                AND dcp.completed = 1
                AND dc.active = 1
                """,
                (user_id, today)
            ).fetchone()

        total_challenges = total_row["total"]
        completed_challenges = completed_row["completed"]

        if total_challenges == 0:
            conn.close()
            return False

        if completed_challenges < total_challenges:
            conn.close()
            return False

        bonus_xp = 50

        if USE_POSTGRES:

            cur.execute(
                """
                UPDATE users
                SET points = points + %s
                WHERE id = %s
                """,
                (bonus_xp, user_id)
            )

            cur.execute(
                """
                INSERT INTO daily_challenge_bonus
                (
                    user_id,
                    bonus_date,
                    xp_reward
                )
                VALUES (%s, %s, %s)
                """,
                (
                    user_id,
                    today,
                    bonus_xp
                )
            )

        else:

            conn.execute(
                """
                UPDATE users
                SET points = points + ?
                WHERE id = ?
                """,
                (bonus_xp, user_id)
            )

            conn.execute(
                """
                INSERT INTO daily_challenge_bonus
                (
                    user_id,
                    bonus_date,
                    xp_reward
                )
                VALUES (?, ?, ?)
                """,
                (
                    user_id,
                    today,
                    bonus_xp
                )
            )

        conn.commit()

        return True

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def get_study_streaks(user_id):
    import datetime
    from zoneinfo import ZoneInfo

    today = datetime.datetime.now(
        ZoneInfo("Africa/Lagos")
    ).date()

    yesterday = today - datetime.timedelta(days=1)

    dates_sql = (
        """
        SELECT study_date
        FROM study_activity
        WHERE user_id = %s
        ORDER BY study_date DESC
        """
        if USE_POSTGRES
        else
        """
        SELECT study_date
        FROM study_activity
        WHERE user_id = ?
        ORDER BY study_date DESC
        """
    )

    rows = query(
        dates_sql,
        (user_id,)
    )

    study_dates = set()

    for row in rows:
        study_date = row["study_date"]

        if isinstance(
            study_date,
            datetime.datetime
        ):
            study_date = study_date.date()

        elif isinstance(study_date, str):
            study_date = datetime.date.fromisoformat(
                study_date
            )

        study_dates.add(study_date)

    # Calculate the current streak.
    if today in study_dates:
        streak_date = today
    elif yesterday in study_dates:
        streak_date = yesterday
    else:
        streak_date = None

    current_streak = 0

    while (
        streak_date is not None
        and streak_date in study_dates
    ):
        current_streak += 1

        streak_date -= datetime.timedelta(days=1)

    # Calculate the longest streak.
    longest_streak = 0
    running_streak = 0
    previous_date = None

    for study_date in sorted(study_dates):

        if (
            previous_date is not None
            and study_date
            == previous_date
            + datetime.timedelta(days=1)
        ):
            running_streak += 1

        else:
            running_streak = 1

        longest_streak = max(
            longest_streak,
            running_streak
        )

        previous_date = study_date

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak
    }

@app.context_processor
def inject_user():

    user = current_user()

    if user:

        level_info = get_level_info(
            user["points"]
        )

    else:

        level_info = None

    return {
        "current_user": user,
        "level_info": level_info
    }


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:

            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        user = current_user()

        if not user or user["role"] != "admin":

            flash(
                "Administrator access required.",
                "danger"
            )

            return redirect(
                url_for("home")
            )

        return view(*args, **kwargs)

    return wrapped

def premium_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        user = current_user()

        if not user:
            flash(
                "Please log in to continue.",
                "warning"
            )
            return redirect(url_for("login"))

        if user["role"] != "admin" and user["plan"] != "premium":
            flash(
                "This feature requires StudyNaija Premium. Visit the Premium page to learn more.",
                "warning"
            )
            return redirect(url_for("premium"))

        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def home():
    return render_template("index.html")


@app.route(
    "/register",
    methods=["GET", "POST"]
)
@limiter.limit("5 per hour")
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        class_level = request.form.get(
            "class_level",
            "SS2"
        )

        if (
            not name
            or not email
            or len(password) < 6
        ):

            flash(
                "Enter your name, a valid email and a password of at least 6 characters.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        exists_sql = (
            "SELECT id FROM users WHERE email = %s"
            if USE_POSTGRES
            else
            "SELECT id FROM users WHERE email = ?"
        )

        if query(
            exists_sql,
            (email,),
            one=True
        ):

            flash(
                "That email is already registered.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

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
                name,
                email,
                generate_password_hash(password),
                class_level,
                "student"
            ),
            commit=True
        )

        flash(
            "Account created. You can now log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


@app.route(
    "/login",
    methods=["GET", "POST"]
)
@limiter.limit("10 per minute")
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        sql = (
            "SELECT * FROM users WHERE email = %s"
            if USE_POSTGRES
            else
            "SELECT * FROM users WHERE email = ?"
        )

        user = query(
            sql,
            (email,),
            one=True
        )

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]

            flash(
                "Welcome back!",
                "success"
            )

            if user["role"] == "admin":
                return redirect(url_for("admin"))
                
            return redirect(
                url_for("dashboard")
            )

        flash(
            "Incorrect email or password.",
            "danger"
        )

    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()

    badges_sql = (
        """
        SELECT *
        FROM badges
        WHERE user_id = %s
        ORDER BY earned_at DESC
        """
        if USE_POSTGRES else
        """
        SELECT *
        FROM badges
        WHERE user_id = ?
        ORDER BY earned_at DESC
        """
    )

    earned_badges = query(
        badges_sql,
        (user["id"],)
    )

    streaks = get_study_streaks(
        user["id"]
    )

    daily_bonus_sql = (
        """
        SELECT xp_reward
        FROM daily_challenge_bonus
        WHERE user_id = %s
        AND bonus_date = CURRENT_DATE
        """
        if USE_POSTGRES
        else
        """
        SELECT xp_reward
        FROM daily_challenge_bonus
        WHERE user_id = ?
        AND bonus_date = DATE('now', 'localtime')
        """
    )

    daily_bonus = query(
        daily_bonus_sql,
        (user["id"],),
        one=True
    )

    calendar_sql = (
        """
        SELECT study_date, activities_completed
        FROM study_activity
        WHERE user_id = %s
        ORDER BY study_date DESC
        LIMIT 35
        """
        if USE_POSTGRES else
        """
        SELECT study_date, activities_completed
        FROM study_activity
        WHERE user_id = ?
        ORDER BY study_date DESC
        LIMIT 35
        """
    )

    activity_rows = query(
        calendar_sql,
        (user["id"],)
    )

    study_dates = []

    for row in activity_rows:
        study_date = row["study_date"]

        if hasattr(study_date, "isoformat"):
            study_date = study_date.isoformat()

        study_dates.append({
            "date": str(study_date),
            "activities": row["activities_completed"]
        })

    daily_challenges_sql = (
        """
        SELECT
            dc.id,
            dc.title,
            dc.description,
            dc.challenge_type,
            dc.target,
            dc.xp_reward,
            COALESCE(dcp.progress, 0) AS progress,
            COALESCE(dcp.completed, 0) AS completed,
            COALESCE(dcp.xp_claimed, 0) AS xp_claimed
        FROM daily_challenges dc
        LEFT JOIN daily_challenge_progress dcp
            ON dc.id = dcp.challenge_id
            AND dcp.user_id = %s
            AND dcp.challenge_date = CURRENT_DATE
        WHERE dc.active = 1
        ORDER BY dc.id
        """
        if USE_POSTGRES
        else
        """
        SELECT
            dc.id,
            dc.title,
            dc.description,
            dc.challenge_type,
            dc.target,
            dc.xp_reward,
            COALESCE(dcp.progress, 0) AS progress,
            COALESCE(dcp.completed, 0) AS completed,
            COALESCE(dcp.xp_claimed, 0) AS xp_claimed
        FROM daily_challenges dc
        LEFT JOIN daily_challenge_progress dcp
            ON dc.id = dcp.challenge_id
            AND dcp.user_id = ?
            AND dcp.challenge_date = DATE('now', 'localtime')
        WHERE dc.active = 1
        ORDER BY dc.id
        """
    )

    daily_challenges = query(
        daily_challenges_sql,
        (user["id"],)
    )

    return render_template(
        "dashboard.html",
        earned_badges=earned_badges,
        streaks=streaks,
        study_dates=study_dates,
        daily_challenges=daily_challenges,
        daily_bonus=daily_bonus
    )


@app.route("/notes")
@login_required
def notes():

    subject = request.args.get(
        "subject",
        ""
    ).strip()

    term = request.args.get(
        "term",
        ""
    ).strip()

    search = request.args.get(
        "search",
        ""
    ).strip()

    user = current_user()

    params = [
        user["class_level"]
    ]

    sql = (
        "SELECT * FROM notes WHERE class_level = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM notes WHERE class_level = ?"
    )


    if subject:

        sql += (
            " AND subject = %s"
            if USE_POSTGRES
            else
            " AND subject = ?"
        )

        params.append(subject)


    if term:

        sql += (
            " AND term = %s"
            if USE_POSTGRES
            else
            " AND term = ?"
        )

        params.append(term)


    if search:

        search_pattern = f"%{search}%"

        if USE_POSTGRES:

            sql += """
                AND (
                    title ILIKE %s
                    OR subject ILIKE %s
                    OR topic ILIKE %s
                )
            """

        else:

            sql += """
                AND (
                    title LIKE ?
                    OR subject LIKE ?
                    OR topic LIKE ?
                )
            """

        params.extend([
            search_pattern,
            search_pattern,
            search_pattern
        ])


    sql += """
        ORDER BY subject ASC, term ASC, title ASC
    """


    rows = query(
        sql,
        tuple(params)
    )


    subject_sql = """
        SELECT DISTINCT subject
        FROM notes
        WHERE class_level = %s
        ORDER BY subject
    """ if USE_POSTGRES else """
        SELECT DISTINCT subject
        FROM notes
        WHERE class_level = ?
        ORDER BY subject
    """


    subject_rows = query(
        subject_sql,
        (user["class_level"],)
    )


    subjects = [
        row["subject"]
        for row in subject_rows
    ]


    return render_template(
        "notes.html",
        notes=rows,
        subjects=subjects,
        subject=subject,
        term=term,
        search=search
    )


@app.route("/notes/<int:note_id>")
@login_required
def note_detail(note_id):

    sql = (
        "SELECT * FROM notes WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM notes WHERE id = ?"
    )

    note = query(
        sql,
        (note_id,),
        one=True
    )

    if not note:

        flash(
            "Note not found.",
            "danger"
        )

        return redirect(
            url_for("notes")
        )

    user = current_user()

    record_study_activity(
        user["id"]
    )

    update_daily_challenges(
        user["id"],
        "note"
    )

    award_daily_challenge_bonus(user["id"])

    return render_template(
        "note_detail.html",
        note=note
    )



@app.route("/quiz")
@login_required
def quiz():

    subject = request.args.get(
        "subject",
        ""
    ).strip()

    user = current_user()

    params = [
        user["class_level"]
    ]

    sql = (
        "SELECT * FROM quizzes WHERE class_level = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM quizzes WHERE class_level = ?"
    )

    if subject:

        sql += (
            " AND subject = %s"
            if USE_POSTGRES
            else
            " AND subject = ?"
        )

        params.append(subject)

    sql += " ORDER BY id DESC"

    rows = query(
        sql,
        tuple(params)
    )

    return render_template(
        "quiz.html",
        quizzes=rows
    )


@app.route(
    "/quiz/<int:quiz_id>",
    methods=["GET", "POST"]
)
@login_required
def take_quiz(quiz_id):

    sql = (
        "SELECT * FROM quizzes WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM quizzes WHERE id = ?"
    )

    quiz_item = query(
        sql,
        (quiz_id,),
        one=True
    )

    if not quiz_item:

        flash(
            "Question not found.",
            "danger"
        )

        return redirect(
            url_for("quiz")
        )

    if request.method == "POST":

        selected = request.form.get(
            "answer",
            ""
        ).strip().upper()

        correct = (
            selected
            == quiz_item["answer"].upper()
        )

        user = current_user()

        if correct:

            update = (
                """
                UPDATE users
                SET points = points + 10
                WHERE id = %s
                """
                if USE_POSTGRES
                else
                """
                UPDATE users
                SET points = points + 10
                WHERE id = ?
                """
            )

            query(
                update,
                (user["id"],),
                commit=True
            )

        record_study_activity(
            user["id"]
        )

        update_daily_challenges(
            user["id"],
            "quiz"
        )
        award_daily_challenge_bonus(user["id"])

        return render_template(
            "quiz_result.html",
            quiz=quiz_item,
            selected=selected,
            correct=correct
        )
    return render_template(
        "take_quiz.html",
        quiz=quiz_item
    )

def generate_ai_quiz_questions(subject, topic, class_level, difficulty, count):
    if not OPENAI_API_KEY or openai_client is None:
        return None

    try:
        response = openai_client.responses.create(
            model="gpt-5-mini",
            instructions=(
                "You are StudyNaija, an educational quiz generator "
                "for Nigerian secondary-school students. "
                "Create accurate multiple-choice questions suitable "
                "for the student's class level and selected difficulty. "
                "Return only valid JSON: an object containing a "
                "'questions' array. Each question must contain these "
                "keys: question, option_a, option_b, option_c, option_d, "
                "answer, explanation. The answer must be A, B, C, or D. "
                "Make sure the correct answer matches the options. "
                "Do not repeat questions."
            ),
            input=(
                f"Subject: {subject}\n"
                f"Topic: {topic}\n"
                f"Class level: {class_level}\n"
                f"Difficulty: {difficulty}\n"
                f"Number of questions: {count}\n\n"
                "Generate the requested questions."
            )
        )

        data = json.loads(response.output_text)
        questions = data.get("questions", [])

        valid_questions = []

        for item in questions:
            answer = str(item.get("answer", "")).strip().upper()

            question_text = str(
                item.get("question", "")
            ).strip()

            options = [
                str(item.get("option_a", "")).strip(),
                str(item.get("option_b", "")).strip(),
                str(item.get("option_c", "")).strip(),
                str(item.get("option_d", "")).strip()
            ]

            if (
                question_text
                and all(options)
                and answer in ["A", "B", "C", "D"]
            ):
                valid_questions.append({
                    "question": question_text,
                    "option_a": options[0],
                    "option_b": options[1],
                    "option_c": options[2],
                    "option_d": options[3],
                    "answer": answer,
                    "explanation": str(
                        item.get("explanation", "")
                    ).strip()
                })

        if len(valid_questions) >= count:
            return valid_questions[:count]

        return None

    except Exception as e:
        print(f"AI quiz generation error: {e}")
        return None


@app.route("/ai-quiz/create", methods=["POST"])
@limiter.limit("5 per hour")
@login_required
def create_ai_quiz():
    user = current_user()

    subject = request.form.get(
        "subject", ""
    ).strip()

    topic = request.form.get(
        "topic", ""
    ).strip()

    difficulty = request.form.get(
        "difficulty", "Medium"
    ).strip().title()

    try:
        count = int(request.form.get("count", "10"))
    except (ValueError, TypeError):
        count = 10

    if not subject or not topic:
        flash(
            "Please enter both a subject and a topic.",
            "danger"
        )
        return redirect(url_for("quiz"))

    if difficulty not in ["Easy", "Medium", "Hard"]:
        difficulty = "Medium"

    count = max(5, min(count, 20))

    questions = generate_ai_quiz_questions(
        subject,
        topic,
        user["class_level"],
        difficulty,
        count
    )

    if not questions:
        sql = (
            """
            SELECT *
            FROM question_bank
            WHERE LOWER(subject) = LOWER(%s)
              AND LOWER(class_level) = LOWER(%s)
              AND LOWER(topic) LIKE LOWER(%s)
            ORDER BY id DESC
            """
            if USE_POSTGRES
            else
            """
            SELECT *
            FROM question_bank
            WHERE LOWER(subject) = LOWER(?)
              AND LOWER(class_level) = LOWER(?)
              AND LOWER(topic) LIKE LOWER(?)
            ORDER BY id DESC
            """
        )

        bank_questions = query(
            sql,
            (
                subject,
                user["class_level"],
                f"%{topic}%"
            )
        )

        if len(bank_questions) < count:
            flash(
                "There are not enough matching questions in your "
                "question bank, and AI generation is unavailable. "
                "Add more questions or check your AI API configuration.",
                "warning"
            )
            return redirect(url_for("quiz"))

        questions = [
            {
                "question": item["question"],
                "option_a": item["option_a"],
                "option_b": item["option_b"],
                "option_c": item["option_c"],
                "option_d": item["option_d"],
                "answer": item["answer"].upper(),
                "explanation": item["explanation"] or ""
            }
            for item in random.sample(
                list(bank_questions),
                count
            )
        ]

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO ai_quiz_sessions
                (
                    user_id, subject, topic, class_level,
                    difficulty, total_questions
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user["id"],
                    subject,
                    topic,
                    user["class_level"],
                    difficulty,
                    len(questions)
                )
            )

            session_id = cur.fetchone()[0]

            for index, item in enumerate(questions, start=1):
                cur.execute(
                    """
                    INSERT INTO ai_quiz_questions
                    (
                        session_id, question, option_a, option_b,
                        option_c, option_d, answer, explanation,
                        question_order
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        item["question"],
                        item["option_a"],
                        item["option_b"],
                        item["option_c"],
                        item["option_d"],
                        item["answer"],
                        item["explanation"],
                        index
                    )
                )

            conn.commit()
            cur.close()

        else:
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO ai_quiz_sessions
                (
                    user_id, subject, topic, class_level,
                    difficulty, total_questions
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    subject,
                    topic,
                    user["class_level"],
                    difficulty,
                    len(questions)
                )
            )

            session_id = cur.lastrowid

            for index, item in enumerate(questions, start=1):
                cur.execute(
                    """
                    INSERT INTO ai_quiz_questions
                    (
                        session_id, question, option_a, option_b,
                        option_c, option_d, answer, explanation,
                        question_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        item["question"],
                        item["option_a"],
                        item["option_b"],
                        item["option_c"],
                        item["option_d"],
                        item["answer"],
                        item["explanation"],
                        index
                    )
                )

            conn.commit()
            cur.close()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    flash(
        "Your AI quiz has been created successfully!",
        "success"
    )

    return redirect(f"/ai-quiz/{session_id}")

@app.route("/ai-quiz/<int:session_id>")
@login_required
def take_ai_quiz(session_id):
    user = current_user()

    quiz_session = query(
        """
        SELECT *
        FROM ai_quiz_sessions
        WHERE id = %s AND user_id = %s
        """ if USE_POSTGRES else """
        SELECT *
        FROM ai_quiz_sessions
        WHERE id = ? AND user_id = ?
        """,
        (session_id, user["id"]),
        one=True
    )

    if not quiz_session:
        flash("Quiz not found.", "danger")
        return redirect(url_for("quiz"))

    if quiz_session["completed"]:
        return redirect(
            url_for("view_ai_quiz_result", session_id=session_id)
        )

    questions = query(
        """
        SELECT id, question, option_a, option_b,
               option_c, option_d, question_order
        FROM ai_quiz_questions
        WHERE session_id = %s
        ORDER BY question_order
        """ if USE_POSTGRES else """
        SELECT id, question, option_a, option_b,
               option_c, option_d, question_order
        FROM ai_quiz_questions
        WHERE session_id = ?
        ORDER BY question_order
        """,
        (session_id,)
    )

    return render_template(
        "ai_quiz.html",
        quiz_session=quiz_session,
        questions=questions
    )

@app.route("/ai-quiz/<int:session_id>/submit", methods=["POST"])
@login_required
def submit_ai_quiz(session_id):
    user = current_user()

    conn = db()

    try:
        cur = conn.cursor()

        if USE_POSTGRES:
            cur.execute(
                """
                SELECT *
                FROM ai_quiz_sessions
                WHERE id = %s AND user_id = %s
                """,
                (session_id, user["id"])
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM ai_quiz_sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, user["id"])
            )

        quiz_session = cur.fetchone()

        if not quiz_session:
            flash("Quiz not found.", "danger")
            return redirect(url_for("quiz"))

        if quiz_session["completed"]:
            return redirect(
                url_for("view_ai_quiz_result", session_id=session_id)
            )

        if USE_POSTGRES:
            cur.execute(
                """
                SELECT *
                FROM ai_quiz_questions
                WHERE session_id = %s
                ORDER BY question_order
                """,
                (session_id,)
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM ai_quiz_questions
                WHERE session_id = ?
                ORDER BY question_order
                """,
                (session_id,)
            )

        questions = cur.fetchall()
        score = 0

        for question in questions:
            question_id = question["id"]
            selected_answer = request.form.get(
                f"answer_{question_id}", ""
            ).strip().upper()

            if selected_answer not in ["A", "B", "C", "D"]:
                selected_answer = ""

            is_correct = (
                selected_answer == question["answer"].strip().upper()
            )

            if is_correct:
                score += 10

            if USE_POSTGRES:
                cur.execute(
                    """
                    UPDATE ai_quiz_questions
                    SET selected_answer = %s, is_correct = %s
                    WHERE id = %s AND session_id = %s
                    """,
                    (selected_answer, is_correct, question_id, session_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE ai_quiz_questions
                    SET selected_answer = ?, is_correct = ?
                    WHERE id = ? AND session_id = ?
                    """,
                    (selected_answer, int(is_correct), question_id, session_id)
                )

        if USE_POSTGRES:
            cur.execute(
                """
                UPDATE ai_quiz_sessions
                SET score = %s, completed = TRUE
                WHERE id = %s AND user_id = %s
                """,
                (score, session_id, user["id"])
            )

            cur.execute(
                """
                UPDATE users
                SET points = COALESCE(points, 0) + %s
                WHERE id = %s
                """,
                (score, user["id"])
            )
        else:
            cur.execute(
                """
                UPDATE ai_quiz_sessions
                SET score = ?, completed = 1
                WHERE id = ? AND user_id = ?
                """,
                (score, session_id, user["id"])
            )

            cur.execute(
                """
                UPDATE users
                SET points = COALESCE(points, 0) + ?
                WHERE id = ?
                """,
                (score, user["id"])
            )

        conn.commit()

        flash(
            f"Quiz submitted! You earned {score} points.",
            "success"
        )

        return redirect(
            url_for("view_ai_quiz_result", session_id=session_id)
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


@app.route("/ai-quiz/<int:session_id>/result")
@login_required
def view_ai_quiz_result(session_id):
    user = current_user()

    quiz_session = query(
        """
        SELECT *
        FROM ai_quiz_sessions
        WHERE id = %s AND user_id = %s
        """ if USE_POSTGRES else """
        SELECT *
        FROM ai_quiz_sessions
        WHERE id = ? AND user_id = ?
        """,
        (session_id, user["id"]),
        one=True
    )

    if not quiz_session:
        flash("Quiz not found.", "danger")
        return redirect(url_for("quiz"))

    if not quiz_session["completed"]:
        flash("Please complete the quiz first.", "warning")
        return redirect(
            url_for("take_ai_quiz", session_id=session_id)
        )

    questions = query(
        """
        SELECT *
        FROM ai_quiz_questions
        WHERE session_id = %s
        ORDER BY question_order
        """ if USE_POSTGRES else """
        SELECT *
        FROM ai_quiz_questions
        WHERE session_id = ?
        ORDER BY question_order
        """,
        (session_id,)
    )

    total_questions = quiz_session["total_questions"]
    score = quiz_session["score"]

    percentage = (
        round((score / (total_questions * 10)) * 100)
        if total_questions else 0
    )

    return render_template(
        "ai_quiz_result.html",
        quiz_session=quiz_session,
        questions=questions,
        total_questions=total_questions,
        score=score,
        percentage=percentage
    )

@app.route("/ai-quiz/history")
@login_required
def ai_quiz_history():
    user = current_user()

    quizzes = query(
        """
        SELECT *
        FROM ai_quiz_sessions
        WHERE user_id = %s
        ORDER BY created_at DESC
        """ if USE_POSTGRES else """
        SELECT *
        FROM ai_quiz_sessions
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user["id"],)
    )

    return render_template(
        "ai_quiz_history.html",
        quizzes=quizzes
    )

@app.route("/ai-quiz/stats")
@login_required
def ai_quiz_stats():
    user = current_user()

    summary = query(
        """
        SELECT
            COUNT(*) AS total_quizzes,
            COALESCE(SUM(CASE WHEN completed = TRUE THEN 1 ELSE 0 END), 0) AS completed_quizzes,
            COALESCE(SUM(score), 0) AS total_score
        FROM ai_quiz_sessions
        WHERE user_id = %s
        """ if USE_POSTGRES else """
        SELECT
            COUNT(*) AS total_quizzes,
            COALESCE(SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END), 0) AS completed_quizzes,
            COALESCE(SUM(score), 0) AS total_score
        FROM ai_quiz_sessions
        WHERE user_id = ?
        """,
        (user["id"],),
        one=True
    )

    average_score = query(
        """
        SELECT
            COALESCE(
                AVG(
                    CASE
                        WHEN total_questions > 0 AND completed = TRUE
                        THEN (score * 100.0) / (total_questions * 10)
                    END
                ),
                0
            ) AS average_score
        FROM ai_quiz_sessions
        WHERE user_id = %s
        """ if USE_POSTGRES else """
        SELECT
            COALESCE(
                AVG(
                    CASE
                        WHEN total_questions > 0 AND completed = 1
                        THEN (score * 100.0) / (total_questions * 10)
                    END
                ),
                0
            ) AS average_score
        FROM ai_quiz_sessions
        WHERE user_id = ?
        """,
        (user["id"],),
        one=True
    )

    best_score = query(
        """
        SELECT
            COALESCE(
                MAX(
                    CASE
                        WHEN total_questions > 0 AND completed = TRUE
                        THEN (score * 100.0) / (total_questions * 10)
                    END
                ),
                0
            ) AS best_score
        FROM ai_quiz_sessions
        WHERE user_id = %s
        """ if USE_POSTGRES else """
        SELECT
            COALESCE(
                MAX(
                    CASE
                        WHEN total_questions > 0 AND completed = 1
                        THEN (score * 100.0) / (total_questions * 10)
                    END
                ),
                0
            ) AS best_score
        FROM ai_quiz_sessions
        WHERE user_id = ?
        """,
        (user["id"],),
        one=True
    )

    favourite_subject = query(
        """
        SELECT subject, COUNT(*) AS quiz_count
        FROM ai_quiz_sessions
        WHERE user_id = %s AND completed = TRUE
        GROUP BY subject
        ORDER BY quiz_count DESC
        LIMIT 1
        """ if USE_POSTGRES else """
        SELECT subject, COUNT(*) AS quiz_count
        FROM ai_quiz_sessions
        WHERE user_id = ? AND completed = 1
        GROUP BY subject
        ORDER BY quiz_count DESC
        LIMIT 1
        """,
        (user["id"],),
        one=True
    )

    recent_quizzes = query(
        """
        SELECT subject, topic, score, total_questions, created_at
        FROM ai_quiz_sessions
        WHERE user_id = %s AND completed = TRUE
        ORDER BY created_at DESC
        LIMIT 5
        """ if USE_POSTGRES else """
        SELECT subject, topic, score, total_questions, created_at
        FROM ai_quiz_sessions
        WHERE user_id = ? AND completed = 1
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (user["id"],)
    )

    return render_template(
        "ai_quiz_stats.html",
        summary=summary,
        average_score=round(float(average_score["average_score"] or 0)),
        best_score=round(float(best_score["best_score"] or 0)),
        favourite_subject=favourite_subject,
        recent_quizzes=recent_quizzes
    )





@app.route("/challenges")
@login_required
def challenges():

    sql = """
    SELECT name, class_level, points
    FROM users
    WHERE role = 'student'
    ORDER BY points DESC, name ASC
    LIMIT 50
    """

    leaders = query(sql)

    return render_template(
        "challenges.html",
        leaders=leaders
    )

def demo_tutor(question, subject, class_level):
    q = question.lower()

    if "newton" in q and ("law" in q or "motion" in q):
        return (
            "NEWTON'S LAWS OF MOTION\n\n"
            "Newton's laws explain how forces affect the movement "
            "of objects.\n\n"
            "First Law: An object remains at rest or continues moving "
            "at constant velocity in a straight line unless an "
            "unbalanced external force acts on it.\n\n"
            "Second Law: The rate of change of momentum is proportional "
            "to the applied force. For constant mass, F = ma, where "
            "F is force, m is mass, and a is acceleration.\n\n"
            "Third Law: For every action, there is an equal and "
            "opposite reaction.\n\n"
            "Example: If a 2 kg object accelerates at 3 m/s², "
            "the force is F = ma = 2 × 3 = 6 N."
        )

    if "photosynthesis" in q:
        return (
            "PHOTOSYNTHESIS\n\n"
            "Photosynthesis is the process by which green plants "
            "use light energy to manufacture food.\n\n"
            "The raw materials are water and carbon dioxide. "
            "Chlorophyll absorbs light energy, and glucose and "
            "oxygen are produced.\n\n"
            "Word equation:\n"
            "Carbon dioxide + Water → Glucose + Oxygen\n\n"
            "Importance: Photosynthesis provides food for plants "
            "and releases oxygen into the atmosphere."
        )

    if "ohm" in q and "law" in q:
        return (
            "OHM'S LAW\n\n"
            "Ohm's law states that the current flowing through a "
            "conductor is directly proportional to the potential "
            "difference across it, provided physical conditions "
            "such as temperature remain constant.\n\n"
            "Formula: V = IR\n\n"
            "V = voltage in volts\n"
            "I = current in amperes\n"
            "R = resistance in ohms\n\n"
            "Example: If V = 12 V and R = 4 ohms:\n"
            "I = V/R = 12/4 = 3 A."
        )

    if "quadratic" in q:
        return (
            "QUADRATIC EQUATIONS\n\n"
            "A quadratic equation has the form:\n"
            "ax² + bx + c = 0, where a is not zero.\n\n"
            "The quadratic formula is:\n"
            "x = (-b ± √(b² - 4ac)) / 2a\n\n"
            "Steps:\n"
            "1. Identify a, b and c.\n"
            "2. Calculate b² - 4ac.\n"
            "3. Substitute the values into the formula.\n"
            "4. Calculate both possible answers."
        )

    if "kepler" in q and ("law" in q or "planet" in q):
        return (
            "KEPLER'S LAWS OF PLANETARY MOTION\n\n"
            "First Law: Planets move in elliptical orbits, with "
            "the Sun at one focus.\n\n"
            "Second Law: A line joining a planet to the Sun sweeps "
            "out equal areas in equal intervals of time.\n\n"
            "Third Law: The square of a planet's orbital period "
            "is proportional to the cube of the semi-major axis "
            "of its orbit.\n\n"
            "Formula: T² ∝ a³.\n\n"
            "These laws describe how planets move around the Sun."
        )

    if "electromagnetic induction" in q:
        return (
            "ELECTROMAGNETIC INDUCTION\n\n"
            "Electromagnetic induction is the production of an "
            "electromotive force (emf) when the magnetic flux "
            "linking a conductor or coil changes.\n\n"
            "It can occur when a magnet moves relative to a coil "
            "or when the magnetic field through the coil changes.\n\n"
            "Faraday's law states that the induced emf depends "
            "on the rate of change of magnetic flux linkage.\n\n"
            "Applications include electric generators and "
            "transformers."
        )

    return (
        "Welcome to StudyNaija Demo Tutor!\n\n"
        f"Subject: {subject}\n"
        f"Class: {class_level}\n\n"
        "I can currently provide built-in explanations for:\n"
        "- Newton's laws of motion\n"
        "- Photosynthesis\n"
        "- Ohm's law\n"
        "- Quadratic equations\n"
        "- Kepler's laws of planetary motion\n"
        "- Electromagnetic induction\n\n"
        "Try asking about one of these topics. More topics can "
        "be added to the StudyNaija learning bank."
    )

def format_demo_learning_mode(answer, question, subject, learning_mode):
    """Add study guidance when the live AI service is unavailable."""

    if learning_mode == "simplify":
        return (
            "Simple explanation:\n\n"
            + answer
            + "\n\nTip: Focus on the main idea first, then learn the details."
        )

    if learning_mode == "example":
        return (
            answer
            + "\n\nWorked-example guidance:\n"
            "1. Identify what the question is asking.\n"
            "2. Write down the relevant definition, rule, or formula.\n"
            "3. Apply it carefully and show each step.\n"
            "4. Check that your final answer makes sense.\n\n"
            "The demo tutor has a limited topic bank. A live AI connection "
            "is needed for a topic-specific worked example beyond that bank."
        )

    if learning_mode == "practice":
        return (
            answer
            + "\n\nPractice questions:\n"
            f"1. Define or explain the main idea in {subject.lower()} "
            "raised by your question.\n"
            "2. Give one real-life example or application.\n"
            "3. State one important rule, formula, feature, or fact "
            "related to the topic.\n\n"
            "Try answering these in your own words. The demo tutor cannot "
            "reliably mark topic-specific answers; a live AI connection "
            "is needed for tailored practice."
        )

    if learning_mode == "exam":
        return (
            answer
            + "\n\nExam preparation checklist:\n"
            "1. Learn the key definitions and principles.\n"
            "2. Practise explaining the topic without looking at your notes.\n"
            "3. For calculations, show your formula, substitution, "
            "working, and unit.\n"
            "4. Recheck the wording of the question before answering.\n\n"
            "A live AI connection is needed for tailored exam-style "
            "questions and marking schemes."
        )

    return answer


def ai_tutor(question, subject, class_level, learning_mode="explain"):
    mode_instructions = {
        "explain": (
            "Explain the topic step by step. Include a worked example "
            "or formula when useful."
        ),
        "example": (
            "Teach the topic using a fully worked example. Show each "
            "step and explain why it is taken."
        ),
        "practice": (
            "Teach briefly, then give 3 to 5 relevant practice questions. "
            "Put the answers or marking guide in a separate section "
            "after the questions."
        ),
        "simplify": (
            "Explain the topic in very simple language, define difficult "
            "words, and use a familiar everyday analogy where helpful."
        ),
        "exam": (
            "Prepare the student for a Nigerian secondary-school exam. "
            "Give key points, exam-style questions, and a concise "
            "marking guide."
        ),
    }

    mode_instruction = mode_instructions.get(
        learning_mode,
        mode_instructions["explain"]
    )

    if not OPENAI_API_KEY or openai_client is None:
        print("AI Tutor: API not configured. Using demo tutor.")

        answer = demo_tutor(
            question,
            subject,
            class_level
        )

        return format_demo_learning_mode(
            answer,
            question,
            subject,
            learning_mode
        )

    try:
        response = openai_client.responses.create(
            model="gpt-5-mini",
            instructions=(
                "You are StudyNaija AI Tutor, an educational tutor "
                "for Nigerian secondary-school students. "
                f"The student is in {class_level}. "
                f"The subject is {subject}. "
                "Explain concepts accurately at the student's level. "
                "Use age-appropriate language, clear formatting, "
                "and correct formulas. Help the student understand "
                "rather than merely memorise. "
                f"Selected learning mode: {learning_mode}. "
                f"{mode_instruction}"
            ),
            input=question
        )

        answer = response.output_text.strip()

        if answer:
            return answer

        raise ValueError("The AI returned an empty answer.")

    except Exception as e:
        print(f"AI Tutor error: {e}")
        print("AI Tutor: Switching to demo mode.")

        answer = demo_tutor(
            question,
            subject,
            class_level
        )

        return format_demo_learning_mode(
            answer,
            question,
            subject,
            learning_mode
        )


@app.route("/challenge-history")
@login_required
def challenge_history():

    user = current_user()

    history_sql = (
        """
        SELECT
            dc.title,
            dc.challenge_type,
            dc.xp_reward,
            dc.target,
            dcp.progress,
            dcp.completed,
            dcp.xp_claimed,
            dcp.challenge_date
        FROM daily_challenge_progress dcp
        JOIN daily_challenges dc
            ON dc.id = dcp.challenge_id
        WHERE dcp.user_id = %s
        ORDER BY dcp.challenge_date DESC, dc.id
        """
        if USE_POSTGRES
        else
        """
        SELECT
            dc.title,
            dc.challenge_type,
            dc.xp_reward,
            dc.target,
            dcp.progress,
            dcp.completed,
            dcp.xp_claimed,
            dcp.challenge_date
        FROM daily_challenge_progress dcp
        JOIN daily_challenges dc
            ON dc.id = dcp.challenge_id
        WHERE dcp.user_id = ?
        ORDER BY dcp.challenge_date DESC, dc.id
        """
    )

    challenge_history = query(
        history_sql,
        (user["id"],)
    )

    bonus_sql = (
        """
        SELECT
            bonus_date,
            xp_reward
        FROM daily_challenge_bonus
        WHERE user_id = %s
        ORDER BY bonus_date DESC
        """
        if USE_POSTGRES
        else
        """
        SELECT
            bonus_date,
            xp_reward
        FROM daily_challenge_bonus
        WHERE user_id = ?
        ORDER BY bonus_date DESC
        """
    )

    challenge_bonuses = query(
        bonus_sql,
        (user["id"],)
    )

    return render_template(
        "challenge_history.html",
        challenge_history=challenge_history,
        challenge_bonuses=challenge_bonuses
    )

@app.route(
    "/tutor",
    methods=["GET", "POST"]
)
@limiter.limit("30 per hour")
@login_required
def tutor():
    user = current_user()
    answer = None
    question = ""
    subject = request.form.get("subject", "General").strip() or "General"
    learning_mode = request.form.get("learning_mode", "explain").strip()

    if request.method == "POST":
        question = request.form.get("question", "").strip()

        if question:
            history_sql = (
                "SELECT question, answer FROM tutor_history "
                "WHERE user_id = %s ORDER BY id DESC LIMIT 8"
                if USE_POSTGRES
                else
                "SELECT question, answer FROM tutor_history "
                "WHERE user_id = ? ORDER BY id DESC LIMIT 8"
            )

            previous_turns = query(history_sql, (user["id"],))
            previous_turns = list(reversed(previous_turns))

            if previous_turns and OPENAI_API_KEY and openai_client is not None:
                context = "\n\n".join(
                    f"Student: {turn['question']}\nTutor: {turn['answer']}"
                    for turn in previous_turns
                )

                contextual_question = (
                    "Continue this student's tutoring conversation. Use the previous "
                    "messages when relevant, and answer the latest question directly.\n\n"
                    f"Previous conversation:\n{context}\n\n"
                    f"Latest question: {question}"
                )
            else:
                contextual_question = question

            answer = ai_tutor(
                contextual_question,
                subject,
                user["class_level"],
                learning_mode
            )

            insert_sql = (
                "INSERT INTO tutor_history (user_id, subject, question, answer) "
                "VALUES (%s, %s, %s, %s)"
                if USE_POSTGRES
                else
                "INSERT INTO tutor_history (user_id, subject, question, answer) "
                "VALUES (?, ?, ?, ?)"
            )

            query(
                insert_sql,
                (user["id"], subject, question, answer),
                commit=True
            )

    history_sql = (
        "SELECT id, subject, question, answer, created_at "
        "FROM tutor_history WHERE user_id = %s ORDER BY id DESC LIMIT 30"
        if USE_POSTGRES
        else
        "SELECT id, subject, question, answer, created_at "
        "FROM tutor_history WHERE user_id = ? ORDER BY id DESC LIMIT 30"
    )

    history = query(history_sql, (user["id"],))

    return render_template(
        "tutor.html",
        answer=answer,
        question=question,
        subject=subject,
        learning_mode=learning_mode,
        history=history
    )

@app.route("/premium/pay", methods=["POST"])
@login_required
def initialize_premium_payment():

    user = current_user()

    if user["plan"] == "premium":
        flash("You already have Premium access.", "info")
        return redirect(url_for("premium"))

    if not PAYSTACK_SECRET_KEY:
        flash("Payment system is not configured yet.", "danger")
        return redirect(url_for("premium"))

    reference = f"STUDYNAIJA-{user['id']}-{int(time.time())}"

    payment_data = {
        "email": user["email"],
        "amount": PAYSTACK_PLAN_AMOUNT,
        "currency": PAYSTACK_CURRENCY,
        "reference": reference,
        "callback_url": url_for(
            "payment_callback",
            _external=True
        )
    }

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:

        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payment_data,
            headers=headers,
            timeout=15
        )

        result = response.json()

    except requests.RequestException:

        flash(
            "Unable to connect to the payment service. Please try again.",
            "danger"
        )
        return redirect(url_for("premium"))

    if not result.get("status"):
        flash(
            "Payment could not be initialized. Please try again.",
            "danger"
        )
        return redirect(url_for("premium"))

    query(
        """
        INSERT INTO payments
        (user_id, reference, amount, currency, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            reference,
            PAYSTACK_PLAN_AMOUNT,
            PAYSTACK_CURRENCY,
            "pending"
        ),
        commit=True
    )

    authorization_url = result["data"]["authorization_url"]

    return redirect(authorization_url)

@app.route("/payment/callback")
@login_required
def payment_callback():

    reference = request.args.get("reference", "").strip()

    if not reference:
        flash("Payment reference is missing.", "danger")
        return redirect(url_for("premium"))

    payment = query(
        """
        SELECT id, user_id, amount, currency, status
        FROM payments
        WHERE reference = ?
        """,
        (reference,),
        one=True
    )

    if not payment or payment["user_id"] != current_user()["id"]:
        flash("Payment record not found.", "danger")
        return redirect(url_for("premium"))

    if payment["status"] == "success":
        flash("This payment has already been processed.", "success")
        return redirect(url_for("premium"))

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers,
            timeout=15
        )
        result = response.json()

    except requests.RequestException:
        flash(
            "We could not verify your payment. Please check your payment history or try again.",
            "warning"
        )
        return redirect(url_for("premium"))

    if not result.get("status"):
        flash("Payment verification failed.", "danger")
        return redirect(url_for("premium"))

    transaction = result.get("data", {})

    if (
        transaction.get("status") != "success"
        or transaction.get("reference") != reference
        or transaction.get("amount") != payment["amount"]
        or transaction.get("currency") != payment["currency"]
    ):
        query(
            "UPDATE payments SET status = ? WHERE reference = ?",
            ("failed", reference),
            commit=True
        )

        flash(
            "The payment could not be confirmed. Your plan has not been changed.",
            "danger"
        )
        return redirect(url_for("premium"))

    query(
        "UPDATE payments SET status = ?, paid_at = CURRENT_TIMESTAMP WHERE reference = ?",
        ("success", reference),
        commit=True
    )

    import datetime

    premium_expires_at = (
        datetime.datetime.now()
        + datetime.timedelta(days=30)
    )

    query(
        "UPDATE users SET plan = ?, premium_expires_at = ? WHERE id = ?",
        ("premium", premium_expires_at, payment["user_id"]),
        commit=True
    )

    flash(
        "Payment verified! Welcome to StudyNaija Premium.",
        "success"
    )

    return redirect(url_for("premium"))

@app.route("/payment-history")
@login_required
def payment_history():
    user = current_user()

    payments = query(
        """
        SELECT reference, amount, currency, status, paid_at, created_at
        FROM payments
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user["id"],)
    )

    return render_template(
        "payment_history.html",
        payments=payments
    )


@app.route("/payment-receipt/<reference>")
@login_required
def payment_receipt(reference):

    user = current_user()

    payment = query(
        """
        SELECT reference, amount, currency, status, paid_at, created_at
        FROM payments
        WHERE reference = ? AND user_id = ?
        """,
        (reference, user["id"]),
        one=True
    )

    if not payment:
        flash("Payment receipt not found.", "danger")
        return redirect(url_for("payment_history"))

    return render_template(
        "payment_receipt.html",
        payment=payment,
        user=user
    )


@app.route("/premium")
@login_required
def premium():
    user = current_user()

    import datetime

    premium_expires_at = user["premium_expires_at"]

    if isinstance(premium_expires_at, str):
        premium_expires_at = datetime.datetime.fromisoformat(
            premium_expires_at
        )

    return render_template(
        "premium.html",
        user_plan=user["plan"] or "free",
        premium_expires_at=premium_expires_at
    )



@app.route("/profile")
@login_required
def profile():

    return render_template(
        "profile.html",
        user=current_user()
    )

@app.route("/admin")
@admin_required
def admin():

    students = query(
        """
        SELECT id,name,email,class_level,points,plan
        FROM users
        WHERE role='student'
        ORDER BY name
        """
    )

    notes_rows = query(
        """
        SELECT *
        FROM notes
        ORDER BY id DESC
        LIMIT 100
        """
    )

    quiz_rows = query(
        """
        SELECT *
        FROM quizzes
        ORDER BY id DESC
        LIMIT 100
        """
    )

    question_search = request.args.get(
        "question_search",
        ""
    ).strip()

    question_exam = request.args.get(
        "question_exam",
        ""
    ).strip()

    question_subject = request.args.get(
        "question_subject",
        ""
    ).strip()

    question_year = request.args.get(
        "question_year",
        ""
    ).strip()

    question_class = request.args.get(
        "question_class",
        ""
    ).strip()

    question_topic = request.args.get(
        "question_topic",
        ""
    ).strip()

    question_conditions = []
    question_params = []

    placeholder = (
        "%s"
        if USE_POSTGRES
        else
        "?"
    )

    if question_search:

        search_pattern = (
            f"%{question_search}%"
        )

        if USE_POSTGRES:

            question_conditions.append(
                """
                (
                    question ILIKE %s
                    OR topic ILIKE %s
                    OR subject ILIKE %s
                    OR option_a ILIKE %s
                    OR option_b ILIKE %s
                    OR option_c ILIKE %s
                    OR option_d ILIKE %s
                )
                """
            )

        else:

            question_conditions.append(
                """
                (
                    question LIKE ?
                    OR topic LIKE ?
                    OR subject LIKE ?
                    OR option_a LIKE ?
                    OR option_b LIKE ?
                    OR option_c LIKE ?
                    OR option_d LIKE ?
                )
                """
            )

        question_params.extend([
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern
        ])

    if question_exam:

        question_conditions.append(
            f"exam = {placeholder}"
        )

        question_params.append(
            question_exam
        )

    if question_subject:

        if USE_POSTGRES:

            question_conditions.append(
                "subject ILIKE %s"
            )

        else:

            question_conditions.append(
                "subject LIKE ?"
            )

        question_params.append(
            f"%{question_subject}%"
        )

    if question_year:

        try:

            year_value = int(
                question_year
            )

            question_conditions.append(
                f"year = {placeholder}"
            )

            question_params.append(
                year_value
            )

        except ValueError:

            question_year = ""

    if question_class:

        if USE_POSTGRES:

            question_conditions.append(
                "class_level ILIKE %s"
            )

        else:

            question_conditions.append(
                "class_level LIKE ?"
            )

        question_params.append(
            f"%{question_class}%"
        )

    if question_topic:

        if USE_POSTGRES:

            question_conditions.append(
                "topic ILIKE %s"
            )

        else:

            question_conditions.append(
                "topic LIKE ?"
            )

        question_params.append(
            f"%{question_topic}%"
        )

    question_where = ""

    if question_conditions:

        question_where = (
            " WHERE "
            + " AND ".join(
                question_conditions
            )
        )

        # Pagination settings
    per_page = 20

    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1

    if page < 1:
        page = 1

    # Build the WHERE clause using the existing filters
    question_where = ""

    if question_conditions:
        question_where = (
            " WHERE "
            + " AND ".join(question_conditions)
        )

    # Count matching questions
    count_sql = (
        "SELECT COUNT(*) AS total "
        "FROM question_bank"
        + question_where
    )

    count_result = query(
        count_sql,
        tuple(question_params),
        one=True
    )

    total_questions = count_result["total"]

    total_pages = max(
        1,
        (total_questions + per_page - 1) // per_page
    )

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    # Fetch only the questions for this page
    question_sql = (
        "SELECT * FROM question_bank"
        + question_where
        + " ORDER BY id DESC LIMIT "
        + str(per_page)
        + " OFFSET "
        + str(offset)
    )

    question_rows = query(
        question_sql,
        tuple(question_params)
    )

    return render_template(
        "admin.html",
        students=students,
        notes=notes_rows,
        quizzes=quiz_rows,
        questions=question_rows,
        page=page,
        total_pages=total_pages,
        total_questions=total_questions
    )

@app.route("/admin/premium/<int:user_id>", methods=["POST"])
@admin_required
def update_student_premium(user_id):
    user = query(
        "SELECT id, name, role, plan FROM users WHERE id = ?",
        (user_id,),
        one=True
    )

    if not user:
        flash("Student not found.", "danger")
        return redirect(url_for("admin"))

    if user["role"] != "student":
        flash("Only student accounts can be upgraded.", "warning")
        return redirect(url_for("admin"))

    new_plan = request.form.get("plan", "").strip().lower()

    if new_plan not in ("free", "premium"):
        flash("Invalid subscription plan.", "danger")
        return redirect(url_for("admin"))

    query(
        "UPDATE users SET plan = ? WHERE id = ?",
        (new_plan, user_id),
        commit=True
    )

    flash(
        f"{user['name']}'s plan has been changed to {new_plan.title()}.",
        "success"
    )
    return redirect(url_for("admin"))


@app.route(
    "/admin/note/add",
    methods=["POST"]
)
@admin_required
def add_note():
    data = (
        request.form.get(
            "title",
            ""
        ).strip(),

        request.form.get(
            "subject",
            ""
        ).strip(),

        request.form.get(
            "class_level",
            "SS2"
        ),

        request.form.get(
            "term",
            "First Term"
        ),

        request.form.get(
            "topic",
            ""
        ).strip(),

        request.form.get(
            "content",
            ""
        ).strip()
    )

    if not all(data):

        flash(
            "All note fields are required.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    sql = """
    INSERT INTO notes
    (title,subject,class_level,term,topic,content)
    VALUES (%s,%s,%s,%s,%s,%s)
    """ if USE_POSTGRES else """
    INSERT INTO notes
    (title,subject,class_level,term,topic,content)
    VALUES (?,?,?,?,?,?)
    """

    query(
        sql,
        data,
        commit=True
    )

    flash(
        "Lesson note added.",
        "success"
    )

    return redirect(
        url_for("admin")
    )

@app.route("/exam")
@login_required
@premium_required
def exam_start():

    user = current_user()

    exam = request.args.get(
        "exam",
        ""
    ).strip().upper()

    subject = request.args.get(
        "subject",
        ""
    ).strip()

    sql = (
        """
        SELECT DISTINCT subject
        FROM question_bank
        WHERE class_level = %s
        ORDER BY subject
        """
        if USE_POSTGRES
        else
        """
        SELECT DISTINCT subject
        FROM question_bank
        WHERE class_level = ?
        ORDER BY subject
        """
    )

    rows = query(
        sql,
        (user["class_level"],)
    )

    subjects = [
        row["subject"]
        for row in rows
    ]

    return render_template(
        "exam_start.html",
        subjects=subjects,
        exam=exam,
        subject=subject
    )

@app.route(
    "/exam/start",
    methods=["POST"]
)
@login_required
@premium_required
def start_exam():

    user = current_user()

    exam = request.form.get(
        "exam",
        ""
    ).strip().upper()

    subject = request.form.get(
        "subject",
        ""
    ).strip()

    try:
        number_of_questions = int(
            request.form.get(
                "number_of_questions",
                "10"
            )
        )

        duration = int(
            request.form.get(
                "duration",
                "1800"
            )
        )

    except ValueError:

        flash(
            "Invalid exam settings.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if exam not in {
        "WAEC",
        "NECO",
        "JAMB"
    }:

        flash(
            "Choose a valid exam.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if number_of_questions not in {
        10,
        20,
        30,
        50
    }:

        flash(
            "Choose a valid number of questions.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if duration not in {
        600,
        1200,
        1800,
        3600
    }:

        flash(
            "Choose a valid exam duration.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if not subject:

        flash(
            "Please select a subject.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    question_sql = (
        """
        SELECT *
        FROM question_bank
        WHERE exam = %s
        AND subject = %s
        AND class_level = %s
        ORDER BY RANDOM()
        LIMIT %s
        """
        if USE_POSTGRES
        else
        """
        SELECT *
        FROM question_bank
        WHERE exam = ?
        AND subject = ?
        AND class_level = ?
        ORDER BY RANDOM()
        LIMIT ?
        """
    )

    questions = query(
        question_sql,
        (
            exam,
            subject,
            user["class_level"],
            number_of_questions
        )
    )

    if len(questions) < number_of_questions:

        flash(
            f"Only {len(questions)} questions are available "
            f"for {exam} {subject} for your class.",
            "warning"
        )

        return redirect(
            url_for("exam_start")
        )

    import datetime

    expires_at = (
        datetime.datetime.now()
        + datetime.timedelta(
            seconds=duration
        )
    )

    session_sql = """
    INSERT INTO exam_sessions
    (
        user_id,
        exam,
        subject,
        class_level,
        total_questions,
        duration_seconds,
        expires_at
    )
    VALUES (
        %s,%s,%s,%s,%s,%s,%s
    )
    """ if USE_POSTGRES else """
    INSERT INTO exam_sessions
    (
        user_id,
        exam,
        subject,
        class_level,
        total_questions,
        duration_seconds,
        expires_at
    )
    VALUES (
        ?,?,?,?,?,?,?
    )
    """

    if USE_POSTGRES:

        conn = db()

        try:

            cur = conn.cursor()

            cur.execute(
                session_sql,
                (
                    user["id"],
                    exam,
                    subject,
                    user["class_level"],
                    number_of_questions,
                    duration,
                    expires_at
                )
            )

            cur.execute(
                "SELECT LASTVAL()"
            )

            session_id = cur.fetchone()[0]

            for index, question in enumerate(
                questions,
                start=1
            ):

                cur.execute(
                    """
                    INSERT INTO exam_session_questions
                    (
                        session_id,
                        question_id,
                        question_order
                    )
                    VALUES (%s,%s,%s)
                    """,
                    (
                        session_id,
                        question["id"],
                        index
                    )
                )

            conn.commit()

        finally:

            conn.close()

    else:

        conn = db()

        try:

            cur = conn.execute(
                session_sql,
                (
                    user["id"],
                    exam,
                    subject,
                    user["class_level"],
                    number_of_questions,
                    duration,
                    expires_at
                )
            )

            session_id = cur.lastrowid

            for index, question in enumerate(
                questions,
                start=1
            ):

                conn.execute(
                    """
                    INSERT INTO exam_session_questions
                    (
                        session_id,
                        question_id,
                        question_order
                    )
                    VALUES (?,?,?)
                    """,
                    (
                        session_id,
                        question["id"],
                        index
                    )
                )

            conn.commit()

        finally:

            conn.close()

    return redirect(
        url_for(
            "take_exam",
            session_id=session_id
        )
    )

@app.route("/exam/<int:session_id>")
@login_required
@premium_required
def take_exam(session_id):

    user = current_user()

    session_sql = (
        """
        SELECT *
        FROM exam_sessions
        WHERE id = %s
        AND user_id = %s
        """
        if USE_POSTGRES
        else
        """
        SELECT *
        FROM exam_sessions
        WHERE id = ?
        AND user_id = ?
        """
    )

    exam_session = query(
        session_sql,
        (session_id, user["id"]),
        one=True
    )

    if not exam_session:

        flash(
            "Exam session not found.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if exam_session["submitted_at"]:

        flash(
            "This exam has already been submitted.",
            "warning"
        )

        return redirect(
            url_for("exam_start")
        )

    import datetime

    expires_at = exam_session["expires_at"]

    if isinstance(expires_at, str):

        expires_at = datetime.datetime.fromisoformat(
            expires_at
        )

    now = datetime.datetime.now()

    if now >= expires_at:

        return redirect(
            url_for(
                "submit_exam",
                session_id=session_id
            )
        )

    question_sql = (
        """
        SELECT
            esq.id AS session_question_id,
            esq.question_order,
            esq.selected_answer,
            qb.*
        FROM exam_session_questions esq
        JOIN question_bank qb
            ON qb.id = esq.question_id
        WHERE esq.session_id = %s
        ORDER BY esq.question_order
        """
        if USE_POSTGRES
        else
        """
        SELECT
            esq.id AS session_question_id,
            esq.question_order,
            esq.selected_answer,
            qb.*
        FROM exam_session_questions esq
        JOIN question_bank qb
            ON qb.id = esq.question_id
        WHERE esq.session_id = ?
        ORDER BY esq.question_order
        """
    )

    questions = query(
        question_sql,
        (session_id,)
    )

    remaining_seconds = max(
        0,
        int(
            (
                expires_at - now
            ).total_seconds()
        )
    )

    return render_template(
        "take_exam.html",
        exam_session=exam_session,
        questions=questions,
        remaining_seconds=remaining_seconds
    )


@app.route(
    "/exam/<int:session_id>/submit",
    methods=["POST", "GET"]
)
@login_required
@premium_required
def submit_exam(session_id):

    user = current_user()

    session_sql = (
        """
        SELECT *
        FROM exam_sessions
        WHERE id = %s
        AND user_id = %s
        """
        if USE_POSTGRES
        else
        """
        SELECT *
        FROM exam_sessions
        WHERE id = ?
        AND user_id = ?
        """
    )

    exam_session = query(
        session_sql,
        (session_id, user["id"]),
        one=True
    )

    if not exam_session:

        flash(
            "Exam session not found.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if exam_session["submitted_at"]:

        return redirect(
            url_for(
                "exam_result",
                session_id=session_id
            )
        )

    question_sql = (
        """
        SELECT
            esq.id AS session_question_id,
            esq.question_id,
            esq.question_order,
            qb.answer
        FROM exam_session_questions esq
        JOIN question_bank qb
            ON qb.id = esq.question_id
        WHERE esq.session_id = %s
        ORDER BY esq.question_order
        """
        if USE_POSTGRES
        else
        """
        SELECT
            esq.id AS session_question_id,
            esq.question_id,
            esq.question_order,
            qb.answer
        FROM exam_session_questions esq
        JOIN question_bank qb
            ON qb.id = esq.question_id
        WHERE esq.session_id = ?
        ORDER BY esq.question_order
        """
    )

    questions = query(
        question_sql,
        (session_id,)
    )

    correct_count = 0
    wrong_count = 0

    conn = db()

    try:

        if USE_POSTGRES:
            cur = conn.cursor()

        for question in questions:

            field_name = (
                f"question_{question['session_question_id']}"
            )

            selected = request.form.get(
                field_name,
                ""
            ).strip().upper()

            correct_answer = (
                question["answer"]
                .strip()
                .upper()
            )

            is_correct = (
                selected == correct_answer
                and selected != ""
            )

            if is_correct:
                correct_count += 1
            else:
                wrong_count += 1

            update_sql = (
                """
                UPDATE exam_session_questions
                SET selected_answer = %s,
                    is_correct = %s
                WHERE id = %s
                """
                if USE_POSTGRES
                else
                """
                UPDATE exam_session_questions
                SET selected_answer = ?,
                    is_correct = ?
                WHERE id = ?
                """
            )

            values = (
                selected or None,
                is_correct if USE_POSTGRES
                else 1 if is_correct else 0,
                question["session_question_id"]
            )

            if USE_POSTGRES:

                cur.execute(
                    update_sql,
                    values
                )

            else:

                conn.execute(
                    update_sql,
                    values
                )

        total_questions = len(questions)

        score = (
            correct_count * 100
        ) // total_questions if total_questions else 0

        import datetime

        submitted_at = datetime.datetime.now()

        session_update = (
            """
            UPDATE exam_sessions
            SET submitted_at = %s,
                score = %s,
                correct_count = %s,
                wrong_count = %s
            WHERE id = %s
            """
            if USE_POSTGRES
            else
            """
            UPDATE exam_sessions
            SET submitted_at = ?,
                score = ?,
                correct_count = ?,
                wrong_count = ?
            WHERE id = ?
            """
        )

        values = (
            submitted_at,
            score,
            correct_count,
            wrong_count,
            session_id
        )

        if USE_POSTGRES:

            cur.execute(
                session_update,
                values
            )

        else:

            conn.execute(
                session_update,
                values
            )

        # XP reward

        xp_earned = 50

        if score >= 70:
            xp_earned += 25

        if score >= 90:
            xp_earned += 50

        xp_update = (
            """
            UPDATE users
            SET points = points + %s
            WHERE id = %s
            """
            if USE_POSTGRES
            else
            """
            UPDATE users
            SET points = points + ?
            WHERE id = ?
            """
        )

        if USE_POSTGRES:
            cur.execute(
                xp_update,
                (
                    xp_earned,
                    user["id"]
                )
            )

        else:
            conn.execute(
                xp_update,
                (
                    xp_earned,
                    user["id"]
                )
            )

        # Badge helper for this exam submission
        def save_badge(
            badge_key,
            badge_name,
            badge_icon,
            description
        ):
            badge_sql = (
                """
                INSERT INTO badges
                (
                    user_id,
                    badge_key,
                    badge_name,
                    badge_icon,
                    description
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, badge_key)
                DO NOTHING
                """
                if USE_POSTGRES
                else
                """
                INSERT OR IGNORE INTO badges
                (
                    user_id,
                    badge_key,
                    badge_name,
                    badge_icon,
                    description
                )
                VALUES (?, ?, ?, ?, ?)
                """
            )

            badge_values = (
                user["id"],
                badge_key,
                badge_name,
                badge_icon,
                description
            )

            if USE_POSTGRES:
                cur.execute(
                    badge_sql,
                    badge_values
                )
            else:
                conn.execute(
                    badge_sql,
                    badge_values
                )

        # Get completed exam count
        completed_exams_sql = (
            """
            SELECT COUNT(*) AS count
            FROM exam_sessions
            WHERE user_id = %s
            AND submitted_at IS NOT NULL
            """
            if USE_POSTGRES
            else
            """
            SELECT COUNT(*) AS count
            FROM exam_sessions
            WHERE user_id = ?
            AND submitted_at IS NOT NULL
            """
        )

        if USE_POSTGRES:
            cur.execute(
                completed_exams_sql,
                (user["id"],)
            )
            completed_exams = cur.fetchone()
        else:
            completed_exams = conn.execute(
                completed_exams_sql,
                (user["id"],)
            ).fetchone()

        completed_count = int(
            completed_exams["count"]
        )

        # Badge: First Step
        if completed_count >= 1:
            save_badge(
                "first_step",
                "First Step",
                "🥉",
                "Complete your first exam"
            )

        # Badge: Sharp Mind
        if score >= 70:
            save_badge(
                "sharp_mind",
                "Sharp Mind",
                "🎯",
                "Score 70% or higher in an exam"
            )

        # Badge: Excellent
        if score >= 90:
            save_badge(
                "excellent",
                "Excellent",
                "🔥",
                "Score 90% or higher in an exam"
            )

        # Badge: Dedicated Learner
        if completed_count >= 5:
            save_badge(
                "dedicated_learner",
                "Dedicated Learner",
                "📚",
                "Complete 5 exams"
            )

        # Get updated XP
        new_xp_sql = (
            """
            SELECT points
            FROM users
            WHERE id = %s
            """
            if USE_POSTGRES
            else
            """
            SELECT points
            FROM users
            WHERE id = ?
            """
        )

        if USE_POSTGRES:
            cur.execute(
                new_xp_sql,
                (user["id"],)
            )
            updated_user = cur.fetchone()
        else:
            updated_user = conn.execute(
                new_xp_sql,
                (user["id"],)
            ).fetchone()

        new_xp = int(
            updated_user["points"]
        )

        # Badge: Champion
        if new_xp >= 1000:
            save_badge(
                "champion",
                "Champion",
                "🏆",
                "Reach 1,000 XP"
            )

        # Badge: Legend
        if new_xp >= 4000:
            save_badge(
                "legend",
                "Legend",
                "👑",
                "Reach 4,000 XP"
            )

        conn.commit()


    finally:

        conn.close()

    record_study_activity(
        user["id"]
    )

    update_daily_challenges(
        user["id"],
        "exam"
    )

    award_daily_challenge_bonus(user["id"])

    return redirect(
        url_for(
            "exam_result",
            session_id=session_id
        )
    )


@app.route(
    "/exam/<int:session_id>/result"
)
@login_required
@premium_required
def exam_result(session_id):

    user = current_user()

    session_sql = (
        """
        SELECT *
        FROM exam_sessions
        WHERE id = %s
        AND user_id = %s
        """
        if USE_POSTGRES
        else
        """
        SELECT *
        FROM exam_sessions
        WHERE id = ?
        AND user_id = ?
        """
    )

    exam_session = query(
        session_sql,
        (session_id, user["id"]),
        one=True
    )

    if not exam_session:

        flash(
            "Exam result not found.",
            "danger"
        )

        return redirect(
            url_for("exam_start")
        )

    if not exam_session["submitted_at"]:

        return redirect(
            url_for(
                "take_exam",
                session_id=session_id
            )
        )

    question_sql = (
        """
        SELECT
            esq.*,
            qb.question,
            qb.option_a,
            qb.option_b,
            qb.option_c,
            qb.option_d,
            qb.answer,
            qb.explanation
        FROM exam_session_questions esq
        JOIN question_bank qb
            ON qb.id = esq.question_id
        WHERE esq.session_id = %s
        ORDER BY esq.question_order
        """
        if USE_POSTGRES
        else
        """
        SELECT
            esq.*,
            qb.question,
            qb.option_a,
            qb.option_b,
            qb.option_c,
            qb.option_d,
            qb.answer,
            qb.explanation
        FROM exam_session_questions esq
        JOIN question_bank qb
            ON qb.id = esq.question_id
        WHERE esq.session_id = ?
        ORDER BY esq.question_order
        """
    )

    questions = query(
        question_sql,
        (session_id,)
    )

    return render_template(
        "exam_result.html",
        exam_session=exam_session,
        questions=questions
    )

@app.route("/exam-history")
@login_required
@premium_required
def exam_history():

    user = current_user()

    history_sql = (
        """
        SELECT
            id,
            exam,
            subject,
            class_level,
            total_questions,
            duration_seconds,
            submitted_at,
            score,
            correct_count,
            wrong_count
        FROM exam_sessions
        WHERE user_id = %s
        AND submitted_at IS NOT NULL
        ORDER BY submitted_at DESC
        """
        if USE_POSTGRES
        else
        """
        SELECT
            id,
            exam,
            subject,
            class_level,
            total_questions,
            duration_seconds,
            submitted_at,
            score,
            correct_count,
            wrong_count
        FROM exam_sessions
        WHERE user_id = ?
        AND submitted_at IS NOT NULL
        ORDER BY submitted_at DESC
        """
    )

    exams = query(
        history_sql,
        (user["id"],)
    )

    total_exams = len(exams)

    if total_exams > 0:

        total_score = sum(
            float(exam["score"] or 0)
            for exam in exams
        )

        average_score = round(
            total_score / total_exams,
            1
        )

        best_score = max(
            float(exam["score"] or 0)
            for exam in exams
        )

        total_questions = sum(
            int(exam["total_questions"] or 0)
            for exam in exams
        )

        total_correct = sum(
            int(exam["correct_count"] or 0)
            for exam in exams
        )

        total_wrong = sum(
            int(exam["wrong_count"] or 0)
            for exam in exams
        )

    else:

        average_score = 0
        best_score = 0
        total_questions = 0
        total_correct = 0
        total_wrong = 0


    subject_sql = (
        """
        SELECT
            subject,
            COUNT(*) AS exam_count,
            AVG(score) AS average_score,
            MAX(score) AS best_score
        FROM exam_sessions
        WHERE user_id = %s
        AND submitted_at IS NOT NULL
        GROUP BY subject
        ORDER BY subject
        """
        if USE_POSTGRES
        else
        """
        SELECT
            subject,
            COUNT(*) AS exam_count,
            AVG(score) AS average_score,
            MAX(score) AS best_score
        FROM exam_sessions
        WHERE user_id = ?
        AND submitted_at IS NOT NULL
        GROUP BY subject
        ORDER BY subject
        """
    )

    subject_stats = query(
        subject_sql,
        (user["id"],)
    )


    return render_template(
        "exam_history.html",
        exams=exams,
        total_exams=total_exams,
        average_score=average_score,
        best_score=best_score,
        total_questions=total_questions,
        total_correct=total_correct,
        total_wrong=total_wrong,
        subject_stats=subject_stats
    )


@app.route("/question-bank")
@login_required
def question_bank():

    exam = request.args.get(
        "exam",
        ""
    ).strip().upper()

    subject = request.args.get(
        "subject",
        ""
    ).strip()

    year = request.args.get(
        "year",
        ""
    ).strip()

    search = request.args.get(
        "search",
        ""
    ).strip()

    user = current_user()

    params = [
        user["class_level"]
    ]

    sql = (
        """
        SELECT *
        FROM question_bank
        WHERE class_level = %s
        """
        if USE_POSTGRES
        else
        """
        SELECT *
        FROM question_bank
        WHERE class_level = ?
        """
    )

    if exam:

        sql += (
            " AND exam = %s"
            if USE_POSTGRES
            else
            " AND exam = ?"
        )

        params.append(exam)

    if subject:

        sql += (
            " AND subject = %s"
            if USE_POSTGRES
            else
            " AND subject = ?"
        )

        params.append(subject)

    if year:

        try:
            year_number = int(year)

            sql += (
                " AND year = %s"
                if USE_POSTGRES
                else
                " AND year = ?"
            )

            params.append(year_number)

        except ValueError:

            year = ""

    if search:

        search_pattern = f"%{search}%"

        if USE_POSTGRES:

            sql += """
                AND (
                    question ILIKE %s
                    OR subject ILIKE %s
                    OR topic ILIKE %s
                )
            """

        else:

            sql += """
                AND (
                    question LIKE ?
                    OR subject LIKE ?
                    OR topic LIKE ?
                )
            """

        params.extend([
            search_pattern,
            search_pattern,
            search_pattern
        ])

    sql += """
        ORDER BY year DESC, subject ASC, id DESC
    """

    questions = query(
        sql,
        tuple(params)
    )

    subject_sql = (
        """
        SELECT DISTINCT subject
        FROM question_bank
        WHERE class_level = %s
        ORDER BY subject
        """
        if USE_POSTGRES
        else
        """
        SELECT DISTINCT subject
        FROM question_bank
        WHERE class_level = ?
        ORDER BY subject
        """
    )

    subject_rows = query(
        subject_sql,
        (user["class_level"],)
    )

    subjects = [
        row["subject"]
        for row in subject_rows
    ]

    year_sql = (
        """
        SELECT DISTINCT year
        FROM question_bank
        WHERE class_level = %s
        ORDER BY year DESC
        """
        if USE_POSTGRES
        else
        """
        SELECT DISTINCT year
        FROM question_bank
        WHERE class_level = ?
        ORDER BY year DESC
        """
    )

    year_rows = query(
        year_sql,
        (user["class_level"],)
    )

    years = [
        row["year"]
        for row in year_rows
    ]

    return render_template(
        "question_bank.html",
        questions=questions,
        subjects=subjects,
        years=years,
        exam=exam,
        subject=subject,
        year=year,
        search=search
    )

@app.route("/question-bank/<int:question_id>")
@login_required
def question_detail(question_id):

    sql = (
        "SELECT * FROM question_bank WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM question_bank WHERE id = ?"
    )

    question = query(
        sql,
        (question_id,),
        one=True
    )

    if not question:

        flash(
            "Question not found.",
            "danger"
        )

        return redirect(
            url_for("question_bank")
        )

    user = current_user()

    if question["class_level"] != user["class_level"]:

        flash(
            "You cannot access this question.",
            "danger"
        )

        return redirect(
            url_for("question_bank")
        )

    return render_template(
        "question_detail.html",
        question=question
    )

@app.route(
    "/admin/question/add",
    methods=["POST"]
)
@admin_required
def add_question():

    exam = request.form.get(
        "exam",
        ""
    ).strip().upper()

    year = request.form.get(
        "year",
        ""
    ).strip()

    subject = request.form.get(
        "subject",
        ""
    ).strip()

    class_level = request.form.get(
        "class_level",
        "SS2"
    ).strip()

    if exam not in {
        "WAEC",
        "NECO",
        "JAMB"
    }:

        flash(
            "Choose WAEC, NECO or JAMB.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    try:
        year_number = int(year)

    except ValueError:

        flash(
            "Enter a valid exam year.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    questions = request.form.getlist(
        "question"
    )

    option_as = request.form.getlist(
        "option_a"
    )

    option_bs = request.form.getlist(
        "option_b"
    )

    option_cs = request.form.getlist(
        "option_c"
    )

    option_ds = request.form.getlist(
        "option_d"
    )

    answers = request.form.getlist(
        "answer"
    )

    topics = request.form.getlist(
        "topic"
    )

    explanations = request.form.getlist(
        "explanation"
    )

    if not questions:

        flash(
            "Add at least one question.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    sql = """
    INSERT INTO question_bank
    (
        exam,
        year,
        subject,
        class_level,
        topic,
        question,
        option_a,
        option_b,
        option_c,
        option_d,
        answer,
        explanation
    )
    VALUES (
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
    )
    """ if USE_POSTGRES else """
    INSERT INTO question_bank
    (
        exam,
        year,
        subject,
        class_level,
        topic,
        question,
        option_a,
        option_b,
        option_c,
        option_d,
        answer,
        explanation
    )
    VALUES (
        ?,?,?,?,?,?,?,?,?,?,?,?
    )
    """

    saved_count = 0

    for index in range(len(questions)):

        question = questions[index].strip()

        option_a = (
            option_as[index].strip()
            if index < len(option_as)
            else ""
        )

        option_b = (
            option_bs[index].strip()
            if index < len(option_bs)
            else ""
        )

        option_c = (
            option_cs[index].strip()
            if index < len(option_cs)
            else ""
        )

        option_d = (
            option_ds[index].strip()
            if index < len(option_ds)
            else ""
        )

        answer = (
            answers[index].strip().upper()
            if index < len(answers)
            else ""
        )

        topic = (
            topics[index].strip()
            if index < len(topics)
            else ""
        )

        explanation = (
            explanations[index].strip()
            if index < len(explanations)
            else ""
        )

        if not all([
            question,
            option_a,
            option_b,
            option_c,
            option_d
        ]):

            flash(
                f"Question {index + 1} is incomplete.",
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        if answer not in {
            "A",
            "B",
            "C",
            "D"
        }:

            flash(
                f"Choose A, B, C or D for question {index + 1}.",
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        data = (
            exam,
            year_number,
            subject,
            class_level,
            topic,
            question,
            option_a,
            option_b,
            option_c,
            option_d,
            answer,
            explanation
        )

        query(
            sql,
            data,
            commit=True
        )

        saved_count += 1

    flash(
        f"{saved_count} question(s) added to the question bank.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/question/import",
    methods=["POST"]
)
@admin_required
@limiter.limit("10 per minute")
def import_questions_csv():

    file = request.files.get(
        "csv_file"
    )

    if not file or not file.filename:

        flash(
            "Please select a CSV file.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    if not file.filename.lower().endswith(".csv"):

        flash(
            "Only CSV files are allowed.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    try:

        content = file.read().decode(
            "utf-8-sig"
        )

        reader = csv.DictReader(
            io.StringIO(content)
        )

        required_columns = {
            "exam",
            "year",
            "subject",
            "class_level",
            "topic",
            "question",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "answer",
            "explanation"
        }

        if not reader.fieldnames:

            flash(
                "The CSV file has no header row.",
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        columns = {
            column.strip().lower()
            for column in reader.fieldnames
            if column
        }

        missing_columns = (
            required_columns - columns
        )

        if missing_columns:

            flash(
                "CSV is missing columns: "
                + ", ".join(
                    sorted(missing_columns)
                ),
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        rows = list(reader)

        if not rows:

            flash(
                "The CSV file contains no questions.",
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        if len(rows) > 1000:

            flash(
                "You can import a maximum of 1000 questions at once.",
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        cleaned_rows = []

        for index, row in enumerate(
            rows,
            start=2
        ):

            normalized = {
                str(key).strip().lower(): (
                    value.strip()
                    if value is not None
                    else ""
                )
                for key, value in row.items()
            }

            exam = normalized.get(
                "exam",
                ""
            ).upper()

            year = normalized.get(
                "year",
                ""
            )

            subject = normalized.get(
                "subject",
                ""
            )

            class_level = normalized.get(
                "class_level",
                ""
            )

            topic = normalized.get(
                "topic",
                ""
            )

            question = normalized.get(
                "question",
                ""
            )

            option_a = normalized.get(
                "option_a",
                ""
            )

            option_b = normalized.get(
                "option_b",
                ""
            )

            option_c = normalized.get(
                "option_c",
                ""
            )

            option_d = normalized.get(
                "option_d",
                ""
            )

            answer = normalized.get(
                "answer",
                ""
            ).upper()

            explanation = normalized.get(
                "explanation",
                ""
            )

            if exam not in {
                "WAEC",
                "NECO",
                "JAMB"
            }:

                flash(
                    f"Row {index}: Exam must be WAEC, NECO or JAMB.",
                    "danger"
                )

                return redirect(
                    url_for("admin")
                )

            try:

                year_number = int(
                    year
                )

            except ValueError:

                flash(
                    f"Row {index}: Invalid exam year.",
                    "danger"
                )

                return redirect(
                    url_for("admin")
                )

            if not all([
                subject,
                class_level,
                question,
                option_a,
                option_b,
                option_c,
                option_d
            ]):

                flash(
                    f"Row {index}: Complete all required fields.",
                    "danger"
                )

                return redirect(
                    url_for("admin")
                )

            if answer not in {
                "A",
                "B",
                "C",
                "D"
            }:

                flash(
                    f"Row {index}: Answer must be A, B, C or D.",
                    "danger"
                )

                return redirect(
                    url_for("admin")
                )

            cleaned_rows.append(
                (
                    exam,
                    year_number,
                    subject,
                    class_level,
                    topic,
                    question,
                    option_a,
                    option_b,
                    option_c,
                    option_d,
                    answer,
                    explanation
                )
            )

        sql = """
        INSERT INTO question_bank
        (
            exam,
            year,
            subject,
            class_level,
            topic,
            question,
            option_a,
            option_b,
            option_c,
            option_d,
            answer,
            explanation
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """ if USE_POSTGRES else """
        INSERT INTO question_bank
        (
            exam,
            year,
            subject,
            class_level,
            topic,
            question,
            option_a,
            option_b,
            option_c,
            option_d,
            answer,
            explanation
        )
        VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?
        )
        """

        conn = db()

        try:

            cur = conn.cursor()

            for data in cleaned_rows:

                cur.execute(
                    sql,
                    data
                )

            conn.commit()

        except Exception:

            conn.rollback()

            flash(
                "The questions could not be imported. "
                "No questions were added.",
                "danger"
            )

            return redirect(
                url_for("admin")
            )

        finally:

            try:
                cur.close()
            except Exception:
                pass

            conn.close()

        flash(
            f"{len(cleaned_rows)} question(s) imported successfully.",
            "success"
        )

        return redirect(
            url_for("admin")
        )
    except Exception as e:
        app.logger.exception("CSV import failed")

        flash(
            f"CSV import failed: {e}",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

@app.route(
    "/admin/note/delete/<int:note_id>",
    methods=["POST"]
)
@admin_required
def delete_note(note_id):

    sql = (
        "DELETE FROM notes WHERE id = %s"
        if USE_POSTGRES
        else
        "DELETE FROM notes WHERE id = ?"
    )

    query(
        sql,
        (note_id,),
        commit=True
    )

    flash(
        "Note deleted.",
        "success"
    )

    return redirect(
        url_for("admin")
    )

@app.route(
    "/admin/question/delete/<int:question_id>",
    methods=["POST"]
)
@admin_required
def delete_question(question_id):

    sql = (
        "DELETE FROM question_bank WHERE id = %s"
        if USE_POSTGRES
        else
        "DELETE FROM question_bank WHERE id = ?"
    )

    query(
        sql,
        (question_id,),
        commit=True
    )

    flash(
        "Question deleted.",
        "success"
    )

    return redirect(
        url_for("admin")
    )

@app.route(
    "/admin/question/delete-bulk",
    methods=["POST"]
)
@admin_required
@limiter.limit("20 per minute")
def delete_questions_bulk():

    question_ids = request.form.getlist(
        "question_ids"
    )

    if not question_ids:
        flash(
            "Select at least one question to delete.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    valid_ids = []

    for question_id in question_ids:
        try:
            valid_ids.append(
                int(question_id)
            )
        except ValueError:
            continue

    if not valid_ids:
        flash(
            "No valid questions were selected.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    placeholders = (
        ",".join(
            ["%s"] * len(valid_ids)
        )
        if USE_POSTGRES
        else
        ",".join(
            ["?"] * len(valid_ids)
        )
    )

    sql = (
        f"DELETE FROM question_bank "
        f"WHERE id IN ({placeholders})"
    )

    query(
        sql,
        tuple(valid_ids),
        commit=True
    )

    flash(
        f"{len(valid_ids)} question(s) deleted.",
        "success"
    )

    return redirect(
        url_for("admin")
    )

@app.route(
    "/admin/question/edit/<int:question_id>",
    methods=["GET", "POST"]
)
@admin_required
def edit_question(question_id):

    question = query(
        (
            "SELECT * FROM question_bank WHERE id = %s"
            if USE_POSTGRES
            else
            "SELECT * FROM question_bank WHERE id = ?"
        ),
        (question_id,),
        one=True
    )

    if not question:
        flash(
            "Question not found.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    if request.method == "POST":

        exam = request.form.get("exam", "").strip()
        year = request.form.get("year", "").strip()
        subject = request.form.get("subject", "").strip()
        class_level = request.form.get("class_level", "").strip()
        topic = request.form.get("topic", "").strip()
        question_text = request.form.get("question", "").strip()
        option_a = request.form.get("option_a", "").strip()
        option_b = request.form.get("option_b", "").strip()
        option_c = request.form.get("option_c", "").strip()
        option_d = request.form.get("option_d", "").strip()
        answer = request.form.get("answer", "").strip().upper()
        explanation = request.form.get("explanation", "").strip()

        if not all([
            exam,
            year,
            subject,
            class_level,
            question_text,
            option_a,
            option_b,
            option_c,
            option_d,
            answer
        ]):
            flash(
                "Please fill in all required fields.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_question",
                    question_id=question_id
                )
            )

        if exam not in ["WAEC", "NECO", "JAMB"]:
            flash(
                "Invalid examination type.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_question",
                    question_id=question_id
                )
            )

        try:
            year = int(year)
        except ValueError:
            flash(
                "Year must be a number.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_question",
                    question_id=question_id
                )
            )

        if answer not in ["A", "B", "C", "D"]:
            flash(
                "Answer must be A, B, C, or D.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_question",
                    question_id=question_id
                )
            )

        sql = (
            """
            UPDATE question_bank
            SET exam = %s,
                year = %s,
                subject = %s,
                class_level = %s,
                topic = %s,
                question = %s,
                option_a = %s,
                option_b = %s,
                option_c = %s,
                option_d = %s,
                answer = %s,
                explanation = %s
            WHERE id = %s
            """
            if USE_POSTGRES
            else
            """
            UPDATE question_bank
            SET exam = ?,
                year = ?,
                subject = ?,
                class_level = ?,
                topic = ?,
                question = ?,
                option_a = ?,
                option_b = ?,
                option_c = ?,
                option_d = ?,
                answer = ?,
                explanation = ?
            WHERE id = ?
            """
        )

        query(
            sql,
            (
                exam,
                year,
                subject,
                class_level,
                topic,
                question_text,
                option_a,
                option_b,
                option_c,
                option_d,
                answer,
                explanation,
                question_id
            ),
            commit=True
        )

        flash(
            "Question updated successfully.",
            "success"
        )

        return redirect(
            url_for("admin")
        )

    return render_template(
        "edit_question.html",
        question=question
    )



@app.route(
    "/admin/quiz/add",
    methods=["POST"]
)
@admin_required
def add_quiz():

    data = (
        request.form.get(
            "title",
            ""
        ).strip(),

        request.form.get(
            "subject",
            ""
        ).strip(),

        request.form.get(
            "class_level",
            "SS2"
        ),

        request.form.get(
            "question",
            ""
        ).strip(),

        request.form.get(
            "option_a",
            ""
        ).strip(),

        request.form.get(
            "option_b",
            ""
        ).strip(),

        request.form.get(
            "option_c",
            ""
        ).strip(),

        request.form.get(
            "option_d",
            ""
        ).strip(),

        request.form.get(
            "answer",
            "A"
        ).upper(),

        request.form.get(
            "explanation",
            ""
        ).strip()
    )

    if (
        not all(data[:9])
        or data[8] not in {
            "A",
            "B",
            "C",
            "D"
        }
    ):

        flash(
            "Complete all quiz fields and choose A, B, C or D as the answer.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    sql = """
    INSERT INTO quizzes
    (title,subject,class_level,question,
     option_a,option_b,option_c,option_d,
     answer,explanation)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """ if USE_POSTGRES else """
    INSERT INTO quizzes
    (title,subject,class_level,question,
     option_a,option_b,option_c,option_d,
     answer,explanation)
    VALUES (?,?,?,?,?,?,?,?,?,?)
    """

    query(
        sql,
        data,
        commit=True
    )

    flash(
        "Quiz question added.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/quiz/delete/<int:quiz_id>",
    methods=["POST"]
)
@admin_required
def delete_quiz(quiz_id):

    sql = (
        "DELETE FROM quizzes WHERE id = %s"
        if USE_POSTGRES
        else
        "DELETE FROM quizzes WHERE id = ?"
    )

    query(
        sql,
        (quiz_id,),
        commit=True
    )

    flash(
        "Quiz question deleted.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/student/delete/<int:user_id>",
    methods=["POST"]
)
@admin_required
def delete_student(user_id):

    sql = (
        "DELETE FROM users WHERE id = %s AND role='student'"
        if USE_POSTGRES
        else
        "DELETE FROM users WHERE id = ? AND role='student'"
    )

    query(
        sql,
        (user_id,),
        commit=True
    )

    flash(
        "Student deleted.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


if __name__ == "__main__":
    app.run(debug=True)
