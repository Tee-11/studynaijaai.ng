import csv
import io
import re
import random

from flask import request, redirect, url_for, flash, render_template

import app as app_module

from app import (
    app,
    db,
    USE_POSTGRES,
    admin_required,
    login_required,
    premium_required,
    limiter,
    query,
)


@app.route(
    "/admin/quiz/import",
    methods=["POST"]
)
@admin_required
@limiter.limit("10 per minute")
def import_practice_questions_csv():
    file = request.files.get("csv_file")

    if not file or not file.filename:
        flash("Please choose a CSV file.", "error")
        return redirect(url_for("admin"))

    if not file.filename.lower().endswith(".csv"):
        flash("Please upload a .csv file.", "error")
        return redirect(url_for("admin"))

    try:
        text = file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        required_columns = {
            "title",
            "subject",
            "question",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "answer",
            "explanation",
        }

        actual_columns = {
            (column or "").strip().lower()
            for column in (reader.fieldnames or [])
        }

        missing = required_columns - actual_columns

        if missing:
            flash(
                "Missing CSV column(s): "
                + ", ".join(sorted(missing)),
                "error"
            )
            return redirect(url_for("admin"))

        cleaned_rows = []

        for index, row in enumerate(reader, start=2):
            normalized = {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in row.items()
            }

            title = normalized.get("title", "")
            subject = normalized.get("subject", "")
            question = normalized.get("question", "")
            option_a = normalized.get("option_a", "")
            option_b = normalized.get("option_b", "")
            option_c = normalized.get("option_c", "")
            option_d = normalized.get("option_d", "")
            answer = normalized.get("answer", "").upper()
            explanation = normalized.get("explanation", "")

            if not all([
                title,
                subject,
                question,
                option_a,
                option_b,
                option_c,
                option_d,
                answer,
            ]):
                flash(
                    f"Row {index} is missing one or more required values.",
                    "error"
                )
                return redirect(url_for("admin"))

            if answer not in {"A", "B", "C", "D"}:
                flash(
                    f"Row {index} has an invalid answer '{answer}'. Use A, B, C, or D.",
                    "error"
                )
                return redirect(url_for("admin"))

            cleaned_rows.append(
                (
                    title,
                    subject,
                    "ALL",
                    question,
                    option_a,
                    option_b,
                    option_c,
                    option_d,
                    answer,
                    explanation,
                )
            )

        if not cleaned_rows:
            flash("The CSV file contains no questions.", "error")
            return redirect(url_for("admin"))

        sql = (
            """
            INSERT INTO quizzes
            (title, subject, class_level, question,
             option_a, option_b, option_c, option_d,
             answer, explanation)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            if USE_POSTGRES
            else
            """
            INSERT INTO quizzes
            (title, subject, class_level, question,
             option_a, option_b, option_c, option_d,
             answer, explanation)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """
        )

        conn = db()

        try:
            cur = conn.cursor()
            for data in cleaned_rows:
                cur.execute(sql, data)
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        flash(
            f"{len(cleaned_rows)} practice question(s) imported successfully.",
            "success"
        )

    except UnicodeDecodeError:
        flash(
            "The CSV file could not be read as UTF-8. Please save it as a CSV UTF-8 file and try again.",
            "error"
        )
    except Exception:
        flash(
            "Something went wrong while importing the practice questions. No questions were imported from this upload.",
            "error"
        )

    return redirect(url_for("admin"))


@login_required
def all_class_notes():
    """Show lesson notes from every class to every logged-in user."""

    subject = request.args.get("subject", "").strip()
    term = request.args.get("term", "").strip()
    search = request.args.get("search", "").strip()

    params = []
    sql = "SELECT * FROM notes WHERE 1=1"
    placeholder = "%s" if USE_POSTGRES else "?"

    if subject:
        sql += f" AND subject = {placeholder}"
        params.append(subject)

    if term:
        sql += f" AND term = {placeholder}"
        params.append(term)

    if search:
        search_pattern = f"%{search}%"

        if USE_POSTGRES:
            sql += """
                AND (
                    title ILIKE %s
                    OR subject ILIKE %s
                    OR topic ILIKE %s
                    OR class_level ILIKE %s
                )
            """
        else:
            sql += """
                AND (
                    title LIKE ?
                    OR subject LIKE ?
                    OR topic LIKE ?
                    OR class_level LIKE ?
                )
            """

        params.extend([
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
        ])

    sql += " ORDER BY class_level ASC, subject ASC, term ASC, title ASC"

    rows = query(sql, tuple(params))

    subject_rows = query("""
        SELECT DISTINCT subject
        FROM notes
        ORDER BY subject
    """)

    subjects = [row["subject"] for row in subject_rows]

    return render_template(
        "notes.html",
        notes=rows,
        subjects=subjects,
        subject=subject,
        term=term,
        search=search
    )


# Remove the class restriction from the existing /notes endpoint.
app.view_functions["notes"] = all_class_notes


@app.route(
    "/register",
    methods=["GET", "POST"]
)
@limiter.limit("5 per hour")
def register_no_class():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash(
                "Enter your name, a valid email and a password of at least 6 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        exists_sql = (
            "SELECT id FROM users WHERE email = %s"
            if USE_POSTGRES
            else "SELECT id FROM users WHERE email = ?"
        )

        if query(exists_sql, (email,), one=True):
            flash("That email is already registered.", "danger")
            return redirect(url_for("login"))

        insert_sql = (
            """
            INSERT INTO users
            (name,email,password,class_level,role)
            VALUES (%s,%s,%s,%s,%s)
            """
            if USE_POSTGRES
            else
            """
            INSERT INTO users
            (name,email,password,class_level,role)
            VALUES (?,?,?,?,?)
            """
        )

        query(
            insert_sql,
            (
                name,
                email,
                app_module.generate_password_hash(password),
                "SS2",
                "student"
            ),
            commit=True
        )

        flash("Account created. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


app.view_functions["register"] = register_no_class


@app.route("/quiz")
@login_required
def quiz_no_class():
    subject = request.args.get("subject", "").strip()

    params = []
    sql = "SELECT * FROM quizzes"

    if subject:
        sql += (
            " WHERE subject = %s"
            if USE_POSTGRES
            else " WHERE subject = ?"
        )
        params.append(subject)

    sql += " ORDER BY id DESC"

    rows = query(sql, tuple(params))
    return render_template("quiz.html", quizzes=rows)


app.view_functions["quiz"] = quiz_no_class


# The existing tutor fallback contains a class line. Remove that line while
# keeping the rest of the tutor behaviour unchanged.
_original_demo_tutor = app_module.demo_tutor


def demo_tutor_without_class(question, subject, class_level):
    answer = _original_demo_tutor(question, subject, "")
    return re.sub(r"\nClass:\s*\n", "\n", answer)


app_module.demo_tutor = demo_tutor_without_class


@app.route(
    "/tutor",
    methods=["GET", "POST"]
)
@limiter.limit("30 per hour")
@login_required
def tutor_no_class():
    user = app_module.current_user()
    answer = None
    question = ""
    subject = request.form.get("subject", "General").strip() or "General"
    learning_mode = request.form.get("learning_mode", "explain").strip()

    if request.method == "POST":
        question = request.form.get("question", "").strip()

        if question:
            history_sql = (
                "SELECT question, answer FROM tutor_history WHERE user_id = %s ORDER BY id DESC LIMIT 8"
                if USE_POSTGRES
                else
                "SELECT question, answer FROM tutor_history WHERE user_id = ? ORDER BY id DESC LIMIT 8"
            )

            previous_turns = query(history_sql, (user["id"],))
            previous_turns = list(reversed(previous_turns))

            if previous_turns and app_module.OPENAI_API_KEY and app_module.openai_client is not None:
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

            answer = app_module.ai_tutor(
                contextual_question,
                subject,
                "",
                learning_mode
            )

            insert_sql = (
                "INSERT INTO tutor_history (user_id, subject, question, answer) VALUES (%s, %s, %s, %s)"
                if USE_POSTGRES
                else
                "INSERT INTO tutor_history (user_id, subject, question, answer) VALUES (?, ?, ?, ?)"
            )

            query(
                insert_sql,
                (user["id"], subject, question, answer),
                commit=True
            )

    history_sql = (
        "SELECT id, subject, question, answer, created_at FROM tutor_history WHERE user_id = %s ORDER BY id DESC LIMIT 30"
        if USE_POSTGRES
        else
        "SELECT id, subject, question, answer, created_at FROM tutor_history WHERE user_id = ? ORDER BY id DESC LIMIT 30"
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


app.view_functions["tutor"] = tutor_no_class


@app.route("/ai-quiz/create", methods=["POST"])
@limiter.limit("5 per hour")
@login_required
def create_ai_quiz_no_class():
    user = app_module.current_user()

    subject = request.form.get("subject", "").strip()
    topic = request.form.get("topic", "").strip()
    difficulty = request.form.get("difficulty", "Medium").strip().title()

    try:
        count = int(request.form.get("count", "10"))
    except (ValueError, TypeError):
        count = 10

    if not subject or not topic:
        flash("Please enter both a subject and a topic.", "danger")
        return redirect(url_for("quiz"))

    if difficulty not in ["Easy", "Medium", "Hard"]:
        difficulty = "Medium"

    count = max(5, min(count, 20))

    questions = app_module.generate_ai_quiz_questions(
        subject,
        topic,
        "",
        difficulty,
        count
    )

    if not questions:
        sql = (
            """
            SELECT *
            FROM question_bank
            WHERE LOWER(subject) = LOWER(%s)
              AND LOWER(topic) LIKE LOWER(%s)
            ORDER BY id DESC
            """
            if USE_POSTGRES
            else
            """
            SELECT *
            FROM question_bank
            WHERE LOWER(subject) = LOWER(?)
              AND LOWER(topic) LIKE LOWER(?)
            ORDER BY id DESC
            """
        )

        bank_questions = query(
            sql,
            (subject, f"%{topic}%")
        )

        if len(bank_questions) < count:
            flash(
                "There are not enough matching questions in the question bank, and AI generation is unavailable.",
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
            for item in random.sample(list(bank_questions), count)
        ]

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ai_quiz_sessions
                (user_id, subject, topic, class_level, difficulty, total_questions)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user["id"], subject, topic, "ALL", difficulty, len(questions))
            )
            session_id = cur.fetchone()[0]

            for index, item in enumerate(questions, start=1):
                cur.execute(
                    """
                    INSERT INTO ai_quiz_questions
                    (session_id, question, option_a, option_b, option_c, option_d,
                     answer, explanation, question_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                (user_id, subject, topic, class_level, difficulty, total_questions)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], subject, topic, "ALL", difficulty, len(questions))
            )
            session_id = cur.lastrowid

            for index, item in enumerate(questions, start=1):
                cur.execute(
                    """
                    INSERT INTO ai_quiz_questions
                    (session_id, question, option_a, option_b, option_c, option_d,
                     answer, explanation, question_order)
                    VALUES (?,?,?,?,?,?,?,?,?)
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

    flash("Your AI quiz has been created successfully!", "success")
    return redirect(f"/ai-quiz/{session_id}")


app.view_functions["create_ai_quiz"] = create_ai_quiz_no_class


@app.route("/exam")
@login_required
@premium_required
def exam_start_no_class():
    exam = request.args.get("exam", "").strip().upper()
    subject = request.args.get("subject", "").strip()

    rows = query("""
        SELECT DISTINCT subject
        FROM question_bank
        ORDER BY subject
    """)

    subjects = [row["subject"] for row in rows]

    return render_template(
        "exam_start.html",
        subjects=subjects,
        exam=exam,
        subject=subject
    )


app.view_functions["exam_start"] = exam_start_no_class


@app.route("/exam/start", methods=["POST"])
@login_required
@premium_required
def start_exam_no_class():
    user = app_module.current_user()

    exam = request.form.get("exam", "").strip().upper()
    subject = request.form.get("subject", "").strip()

    try:
        number_of_questions = int(request.form.get("number_of_questions", "10"))
        duration = int(request.form.get("duration", "1800"))
    except ValueError:
        flash("Invalid exam settings.", "danger")
        return redirect(url_for("exam_start"))

    if exam not in {"WAEC", "NECO", "JAMB"}:
        flash("Choose a valid exam.", "danger")
        return redirect(url_for("exam_start"))

    if number_of_questions not in {10, 20, 30, 50}:
        flash("Choose a valid number of questions.", "danger")
        return redirect(url_for("exam_start"))

    if duration not in {600, 1200, 1800, 3600}:
        flash("Choose a valid exam duration.", "danger")
        return redirect(url_for("exam_start"))

    if not subject:
        flash("Please select a subject.", "danger")
        return redirect(url_for("exam_start"))

    question_sql = (
        """
        SELECT * FROM question_bank
        WHERE exam = %s AND subject = %s
        ORDER BY RANDOM()
        LIMIT %s
        """
        if USE_POSTGRES
        else
        """
        SELECT * FROM question_bank
        WHERE exam = ? AND subject = ?
        ORDER BY RANDOM()
        LIMIT ?
        """
    )

    questions = query(
        question_sql,
        (exam, subject, number_of_questions)
    )

    if len(questions) < number_of_questions:
        flash(
            f"Only {len(questions)} questions are available for {exam} {subject}.",
            "warning"
        )
        return redirect(url_for("exam_start"))

    import datetime
    expires_at = datetime.datetime.now() + datetime.timedelta(seconds=duration)

    session_sql = (
        """
        INSERT INTO exam_sessions
        (user_id, exam, subject, class_level, total_questions, duration_seconds, expires_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """
        if USE_POSTGRES
        else
        """
        INSERT INTO exam_sessions
        (user_id, exam, subject, class_level, total_questions, duration_seconds, expires_at)
        VALUES (?,?,?,?,?,?,?)
        """
    )

    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(
                session_sql,
                (user["id"], exam, subject, "ALL", number_of_questions, duration, expires_at)
            )
            cur.execute("SELECT LASTVAL()")
            session_id = cur.fetchone()[0]

            for index, question in enumerate(questions, start=1):
                cur.execute(
                    """
                    INSERT INTO exam_session_questions
                    (session_id, question_id, question_order)
                    VALUES (%s,%s,%s)
                    """,
                    (session_id, question["id"], index)
                )
            conn.commit()
        else:
            cur = conn.execute(
                session_sql,
                (user["id"], exam, subject, "ALL", number_of_questions, duration, expires_at)
            )
            session_id = cur.lastrowid

            for index, question in enumerate(questions, start=1):
                conn.execute(
                    """
                    INSERT INTO exam_session_questions
                    (session_id, question_id, question_order)
                    VALUES (?,?,?)
                    """,
                    (session_id, question["id"], index)
                )
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for("take_exam", session_id=session_id))


app.view_functions["start_exam"] = start_exam_no_class


@app.route("/exam-history")
@login_required
@premium_required
def exam_history_no_class():
    user = app_module.current_user()

    history_sql = (
        """
        SELECT id, exam, subject, total_questions, duration_seconds,
               submitted_at, score, correct_count, wrong_count
        FROM exam_sessions
        WHERE user_id = %s AND submitted_at IS NOT NULL
        ORDER BY submitted_at DESC
        """
        if USE_POSTGRES
        else
        """
        SELECT id, exam, subject, total_questions, duration_seconds,
               submitted_at, score, correct_count, wrong_count
        FROM exam_sessions
        WHERE user_id = ? AND submitted_at IS NOT NULL
        ORDER BY submitted_at DESC
        """
    )

    exams = query(history_sql, (user["id"],))
    total_exams = len(exams)

    if total_exams:
        total_score = sum(float(exam["score"] or 0) for exam in exams)
        average_score = round(total_score / total_exams, 1)
        best_score = max(float(exam["score"] or 0) for exam in exams)
        total_questions = sum(int(exam["total_questions"] or 0) for exam in exams)
        total_correct = sum(int(exam["correct_count"] or 0) for exam in exams)
        total_wrong = sum(int(exam["wrong_count"] or 0) for exam in exams)
    else:
        average_score = 0
        best_score = 0
        total_questions = 0
        total_correct = 0
        total_wrong = 0

    subject_sql = (
        """
        SELECT subject, COUNT(*) AS exam_count, AVG(score) AS average_score,
               MAX(score) AS best_score
        FROM exam_sessions
        WHERE user_id = %s AND submitted_at IS NOT NULL
        GROUP BY subject ORDER BY subject
        """
        if USE_POSTGRES
        else
        """
        SELECT subject, COUNT(*) AS exam_count, AVG(score) AS average_score,
               MAX(score) AS best_score
        FROM exam_sessions
        WHERE user_id = ? AND submitted_at IS NOT NULL
        GROUP BY subject ORDER BY subject
        """
    )

    subject_stats = query(subject_sql, (user["id"],))

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


app.view_functions["exam_history"] = exam_history_no_class


@app.route("/question-bank")
@login_required
def question_bank_no_class():
    exam = request.args.get("exam", "").strip().upper()
    subject = request.args.get("subject", "").strip()
    year = request.args.get("year", "").strip()
    search = request.args.get("search", "").strip()

    params = []
    sql = "SELECT * FROM question_bank WHERE 1=1"
    placeholder = "%s" if USE_POSTGRES else "?"

    if exam:
        sql += f" AND exam = {placeholder}"
        params.append(exam)

    if subject:
        sql += f" AND subject = {placeholder}"
        params.append(subject)

    if year:
        try:
            year_number = int(year)
            sql += f" AND year = {placeholder}"
            params.append(year_number)
        except ValueError:
            year = ""

    if search:
        search_pattern = f"%{search}%"
        if USE_POSTGRES:
            sql += " AND (question ILIKE %s OR subject ILIKE %s OR topic ILIKE %s)"
        else:
            sql += " AND (question LIKE ? OR subject LIKE ? OR topic LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])

    sql += " ORDER BY year DESC, subject ASC, id DESC"
    questions = query(sql, tuple(params))

    subject_rows = query("SELECT DISTINCT subject FROM question_bank ORDER BY subject")
    subjects = [row["subject"] for row in subject_rows]

    year_rows = query("SELECT DISTINCT year FROM question_bank ORDER BY year DESC")
    years = [row["year"] for row in year_rows]

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


app.view_functions["question_bank"] = question_bank_no_class


@app.route("/question-bank/<int:question_id>")
@login_required
def question_detail_no_class(question_id):
    sql = (
        "SELECT * FROM question_bank WHERE id = %s"
        if USE_POSTGRES
        else
        "SELECT * FROM question_bank WHERE id = ?"
    )

    question = query(sql, (question_id,), one=True)

    if not question:
        flash("Question not found.", "danger")
        return redirect(url_for("question_bank"))

    return render_template("question_detail.html", question=question)


app.view_functions["question_detail"] = question_detail_no_class
