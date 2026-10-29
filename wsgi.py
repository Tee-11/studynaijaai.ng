import csv
import io

from flask import request, redirect, url_for, flash, render_template

from app import (
    app,
    db,
    USE_POSTGRES,
    admin_required,
    login_required,
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
            "class_level",
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
            class_level = normalized.get("class_level", "")
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
                class_level,
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
                    f"Row {index} has an invalid answer '{answer}'. "
                    "Use A, B, C, or D.",
                    "error"
                )
                return redirect(url_for("admin"))

            cleaned_rows.append(
                (
                    title,
                    subject,
                    class_level,
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
            "The CSV file could not be read as UTF-8. "
            "Please save it as a CSV UTF-8 file and try again.",
            "error"
        )
    except Exception:
        flash(
            "Something went wrong while importing the practice questions. "
            "No questions were imported from this upload.",
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


# Keep the existing /notes URL and endpoint name while removing the class restriction.
app.view_functions["notes"] = all_class_notes
