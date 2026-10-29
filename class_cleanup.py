import csv
import io

from flask import request, redirect, url_for, flash

import app as app_module



def apply():
    app = app_module.app
    query = app_module.query
    db = app_module.db
    USE_POSTGRES = app_module.USE_POSTGRES
    admin_required = app_module.admin_required
    limiter = app_module.limiter

    def import_questions_csv_no_class():
        file = request.files.get("csv_file")

        if not file or not file.filename:
            flash("Please select a CSV file.", "danger")
            return redirect(url_for("admin"))

        if not file.filename.lower().endswith(".csv"):
            flash("Only CSV files are allowed.", "danger")
            return redirect(url_for("admin"))

        try:
            content = file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))

            required_columns = {
                "exam",
                "year",
                "subject",
                "topic",
                "question",
                "option_a",
                "option_b",
                "option_c",
                "option_d",
                "answer",
                "explanation",
            }

            columns = {
                (column or "").strip().lower()
                for column in (reader.fieldnames or [])
            }

            if not columns:
                flash("The CSV file has no header row.", "danger")
                return redirect(url_for("admin"))

            missing = required_columns - columns

            if missing:
                flash(
                    "CSV is missing columns: "
                    + ", ".join(sorted(missing)),
                    "danger"
                )
                return redirect(url_for("admin"))

            rows = list(reader)

            if not rows:
                flash("The CSV file contains no questions.", "danger")
                return redirect(url_for("admin"))

            if len(rows) > 1000:
                flash("You can import a maximum of 1000 questions at once.", "danger")
                return redirect(url_for("admin"))

            cleaned_rows = []

            for index, row in enumerate(rows, start=2):
                normalized = {
                    (key or "").strip().lower(): (value or "").strip()
                    for key, value in row.items()
                }

                exam = normalized.get("exam", "").upper()
                subject = normalized.get("subject", "")
                topic = normalized.get("topic", "")
                question = normalized.get("question", "")
                option_a = normalized.get("option_a", "")
                option_b = normalized.get("option_b", "")
                option_c = normalized.get("option_c", "")
                option_d = normalized.get("option_d", "")
                answer = normalized.get("answer", "").upper()
                explanation = normalized.get("explanation", "")

                try:
                    year_number = int(normalized.get("year", ""))
                except ValueError:
                    flash(f"Row {index}: Invalid exam year.", "danger")
                    return redirect(url_for("admin"))

                if exam not in {"WAEC", "NECO", "JAMB"}:
                    flash(
                        f"Row {index}: Exam must be WAEC, NECO or JAMB.",
                        "danger"
                    )
                    return redirect(url_for("admin"))

                if not all([
                    subject,
                    question,
                    option_a,
                    option_b,
                    option_c,
                    option_d,
                ]):
                    flash(f"Row {index}: Complete all required fields.", "danger")
                    return redirect(url_for("admin"))

                if answer not in {"A", "B", "C", "D"}:
                    flash(f"Row {index}: Answer must be A, B, C or D.", "danger")
                    return redirect(url_for("admin"))

                cleaned_rows.append(
                    (
                        exam,
                        year_number,
                        subject,
                        "ALL",
                        topic,
                        question,
                        option_a,
                        option_b,
                        option_c,
                        option_d,
                        answer,
                        explanation,
                    )
                )

            sql = (
                """
                INSERT INTO question_bank
                (exam, year, subject, class_level, topic, question,
                 option_a, option_b, option_c, option_d, answer, explanation)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """
                if USE_POSTGRES
                else
                """
                INSERT INTO question_bank
                (exam, year, subject, class_level, topic, question,
                 option_a, option_b, option_c, option_d, answer, explanation)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
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
                f"{len(cleaned_rows)} question(s) imported successfully.",
                "success"
            )

        except UnicodeDecodeError:
            flash(
                "The CSV file could not be read as UTF-8. Please save it as a CSV UTF-8 file and try again.",
                "danger"
            )
        except Exception as exc:
            app.logger.exception("CSV import failed")
            flash(f"CSV import failed: {exc}", "danger")

        return redirect(url_for("admin"))

    wrapped = admin_required(import_questions_csv_no_class)
    wrapped = limiter.limit("10 per minute")(wrapped)
    app.view_functions["import_questions_csv"] = wrapped
