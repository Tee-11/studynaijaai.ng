import datetime

from flask import redirect, request, url_for
from psycopg2.extras import RealDictCursor

from app import (
    app,
    USE_POSTGRES,
    db,
    current_user,
    login_required,
    premium_required,
    query,
    record_study_activity,
    update_daily_challenges,
    award_daily_challenge_bonus,
)


@login_required
@premium_required
def submit_exam_fixed(session_id):
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
        return redirect(url_for("exam_start"))

    if exam_session["submitted_at"]:
        return redirect(
            url_for("exam_result", session_id=session_id)
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

    questions = query(question_sql, (session_id,))

    correct_count = 0
    wrong_count = 0
    conn = db()

    try:
        if USE_POSTGRES:
            # The original route used a normal PostgreSQL cursor here.
            # The rest of the route accesses fetched rows by column name,
            # so the cursor must return dictionaries.
            cur = conn.cursor(cursor_factory=RealDictCursor)

        for question in questions:
            field_name = f"question_{question['session_question_id']}"
            selected = request.form.get(field_name, "").strip().upper()
            correct_answer = question["answer"].strip().upper()
            is_correct = selected == correct_answer and selected != ""

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
                is_correct if USE_POSTGRES else (1 if is_correct else 0),
                question["session_question_id"]
            )

            if USE_POSTGRES:
                cur.execute(update_sql, values)
            else:
                conn.execute(update_sql, values)

        total_questions = len(questions)
        score = (correct_count * 100) // total_questions if total_questions else 0
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

        session_values = (
            submitted_at,
            score,
            correct_count,
            wrong_count,
            session_id
        )

        if USE_POSTGRES:
            cur.execute(session_update, session_values)
        else:
            conn.execute(session_update, session_values)

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

        xp_values = (xp_earned, user["id"])

        if USE_POSTGRES:
            cur.execute(xp_update, xp_values)
        else:
            conn.execute(xp_update, xp_values)

        def save_badge(badge_key, badge_name, badge_icon, description):
            badge_sql = (
                """
                INSERT INTO badges
                (user_id, badge_key, badge_name, badge_icon, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, badge_key) DO NOTHING
                """
                if USE_POSTGRES
                else
                """
                INSERT OR IGNORE INTO badges
                (user_id, badge_key, badge_name, badge_icon, description)
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
                cur.execute(badge_sql, badge_values)
            else:
                conn.execute(badge_sql, badge_values)

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
            cur.execute(completed_exams_sql, (user["id"],))
            completed_exams = cur.fetchone()
        else:
            completed_exams = conn.execute(
                completed_exams_sql,
                (user["id"],)
            ).fetchone()

        completed_count = int(completed_exams["count"])

        if completed_count >= 1:
            save_badge(
                "first_step",
                "First Step",
                "🥉",
                "Complete your first exam"
            )

        if score >= 70:
            save_badge(
                "sharp_mind",
                "Sharp Mind",
                "🎯",
                "Score 70% or higher in an exam"
            )

        if score >= 90:
            save_badge(
                "excellent",
                "Excellent",
                "🔥",
                "Score 90% or higher in an exam"
            )

        if completed_count >= 5:
            save_badge(
                "dedicated_learner",
                "Dedicated Learner",
                "📚",
                "Complete 5 exams"
            )

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
            cur.execute(new_xp_sql, (user["id"],))
            updated_user = cur.fetchone()
        else:
            updated_user = conn.execute(
                new_xp_sql,
                (user["id"],)
            ).fetchone()

        new_xp = int(updated_user["points"])

        if new_xp >= 1000:
            save_badge(
                "champion",
                "Champion",
                "🏆",
                "Reach 1,000 XP"
            )

        if new_xp >= 4000:
            save_badge(
                "legend",
                "Legend",
                "👑",
                "Reach 4,000 XP"
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        try:
            if USE_POSTGRES:
                cur.close()
        except Exception:
            pass
        conn.close()

    record_study_activity(user["id"])
    update_daily_challenges(user["id"], "exam")
    award_daily_challenge_bonus(user["id"])

    return redirect(
        url_for("exam_result", session_id=session_id)
    )


# Replace the original view function without changing the original app.py.
app.view_functions["submit_exam"] = submit_exam_fixed
