import csv
import io

from flask import request, redirect, url_for, flash

from app import app, db, USE_POSTGRES, admin_required, limiter


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
