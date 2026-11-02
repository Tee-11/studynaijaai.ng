import csv
import io

from flask import Response, flash, redirect, render_template, request, url_for

from app import app, USE_POSTGRES, admin_required, db


ALLOWED_CLASSES = {"JSS1", "JSS2", "JSS3", "SS1", "SS2", "SS3"}
ALLOWED_TERMS = {"First Term", "Second Term", "Third Term"}
REQUIRED_COLUMNS = {
    "title",
    "subject",
    "class_level",
    "term",
    "topic",
    "content",
}


def _normalize(value):
    return (value or "").strip()


@app.route("/admin/notes/import", methods=["GET", "POST"])
@admin_required
def import_notes_csv():
    if request.method == "GET":
        return render_template("admin_notes_csv.html")

    file = request.files.get("csv_file")

    if not file or not file.filename:
        flash("Please choose a CSV file.", "error")
        return redirect(url_for("import_notes_csv"))

    if not file.filename.lower().endswith(".csv"):
        flash("Please upload a .csv file.", "error")
        return redirect(url_for("import_notes_csv"))

    try:
        text = file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        actual_columns = {
            _normalize(column).lower()
            for column in (reader.fieldnames or [])
        }

        missing = REQUIRED_COLUMNS - actual_columns
        if missing:
            flash(
                "Missing CSV column(s): " + ", ".join(sorted(missing)),
                "error",
            )
            return redirect(url_for("import_notes_csv"))

        rows = []

        for line_number, row in enumerate(reader, start=2):
            normalized = {
                _normalize(key).lower(): _normalize(value)
                for key, value in row.items()
            }

            title = normalized.get("title", "")
            subject = normalized.get("subject", "")
            class_level = normalized.get("class_level", "").upper()
            term = normalized.get("term", "")
            topic = normalized.get("topic", "")
            content = normalized.get("content", "")

            if not all([title, subject, class_level, term, topic, content]):
                flash(
                    f"Row {line_number} is missing a required value. Nothing was imported.",
                    "error",
                )
                return redirect(url_for("import_notes_csv"))

            if class_level not in ALLOWED_CLASSES:
                flash(
                    f"Row {line_number} has invalid class '{class_level}'. "
                    "Use JSS1, JSS2, JSS3, SS1, SS2, or SS3.",
                    "error",
                )
                return redirect(url_for("import_notes_csv"))

            if term not in ALLOWED_TERMS:
                flash(
                    f"Row {line_number} has invalid term '{term}'. "
                    "Use First Term, Second Term, or Third Term.",
                    "error",
                )
                return redirect(url_for("import_notes_csv"))

            rows.append(
                (title, subject, class_level, term, topic, content)
            )

        if not rows:
            flash("The CSV file contains no lesson notes.", "error")
            return redirect(url_for("import_notes_csv"))

        if USE_POSTGRES:
            insert_sql = """
                INSERT INTO notes
                (title, subject, class_level, term, topic, content)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
        else:
            insert_sql = """
                INSERT INTO notes
                (title, subject, class_level, term, topic, content)
                VALUES (?, ?, ?, ?, ?, ?)
            """

        conn = db()

        try:
            cur = conn.cursor()
            for data in rows:
                cur.execute(insert_sql, data)
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        flash(
            f"{len(rows)} lesson note(s) imported successfully.",
            "success",
        )
        return redirect(url_for("import_notes_csv"))

    except UnicodeDecodeError:
        flash(
            "The CSV file could not be read as UTF-8. Save it as CSV UTF-8 and try again.",
            "error",
        )
    except Exception:
        flash(
            "Something went wrong while importing the notes. Nothing was imported from this upload.",
            "error",
        )

    return redirect(url_for("import_notes_csv"))


@app.route("/admin/notes/csv-template")
@admin_required
def notes_csv_template():
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "title",
        "subject",
        "class_level",
        "term",
        "topic",
        "content",
    ])
    writer.writerow([
        "Introduction to Number Bases",
        "Mathematics",
        "JSS1",
        "First Term",
        "Number Bases",
        "Write the complete lesson note here. Excel will keep commas and line breaks inside the cell when saved as CSV.",
    ])
    writer.writerow([
        "Living Things",
        "Basic Science",
        "JSS1",
        "First Term",
        "Characteristics of Living Things",
        "Write the complete lesson note here.",
    ])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=studynaija_notes_template.csv"
    return response
