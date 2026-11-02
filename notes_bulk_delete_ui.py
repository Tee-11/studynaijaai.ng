from flask import request

from app import app


@app.after_request
def add_bulk_note_delete_ui(response):
    if request.path != "/admin":
        return response

    if not response.content_type or "text/html" not in response.content_type:
        return response

    html = response.get_data(as_text=True)

    script = r"""
<style>
    .study-bulk-note-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        flex-wrap: wrap;
        margin: 0 0 18px;
        padding: 14px 16px;
        border: 1px solid #dbe3ef;
        border-radius: 12px;
        background: #f8fafc;
    }

    .study-bulk-note-select {
        display: flex;
        align-items: center;
        gap: 9px;
        margin: 0;
        font-weight: 600;
        cursor: pointer;
    }

    .study-bulk-note-select input {
        width: 18px;
        height: 18px;
        margin: 0;
        cursor: pointer;
    }

    .study-bulk-note-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }

    .study-note-row {
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
    }

    .study-note-row .note-checkbox {
        width: 18px;
        height: 18px;
        margin: 0 2px 0 0 !important;
        flex: 0 0 auto;
        cursor: pointer;
    }

    .study-note-row .note-content {
        flex: 1 1 auto;
        min-width: 0;
    }

    @media (max-width: 600px) {
        .study-bulk-note-toolbar {
            align-items: stretch;
        }

        .study-bulk-note-actions,
        .study-bulk-note-actions button {
            width: 100%;
        }

        .study-bulk-note-actions button {
            text-align: center;
        }
    }
</style>

<script>
(function () {
    const cards = Array.from(document.querySelectorAll(".wide-card"));

    const notesCard = cards.find(card => {
        const heading = card.querySelector("h2");
        return heading && heading.textContent.includes("Existing Lesson Notes");
    });

    if (!notesCard || document.getElementById("bulk-note-delete-form")) {
        return;
    }

    const rows = Array.from(notesCard.querySelectorAll(".admin-row"));

    if (!rows.length) {
        return;
    }

    const csrfInput = document.querySelector("input[name='csrf_token']");
    const csrfToken = csrfInput ? csrfInput.value : "";

    const toolbar = document.createElement("div");
    toolbar.className = "study-bulk-note-toolbar";
    toolbar.innerHTML = `
        <label class="study-bulk-note-select">
            <input type="checkbox" id="select-all-notes">
            <span>Select All Lesson Notes</span>
        </label>

        <div class="study-bulk-note-actions">
            <button
                type="submit"
                form="bulk-note-delete-form"
                class="danger-button"
            >
                🗑️ Delete Selected
            </button>
        </div>
    `;

    const form = document.createElement("form");
    form.id = "bulk-note-delete-form";
    form.style.display = "none";
    document.body.appendChild(form);

    notesCard.insertBefore(toolbar, rows[0]);

    rows.forEach(row => {
        const deleteForm = row.querySelector("form");
        if (!deleteForm) return;

        const action = deleteForm.getAttribute("action") || "";
        const match = action.match(/\/admin\/note\/delete\/(\d+)/);
        if (!match) return;

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = match[1];
        checkbox.className = "note-checkbox";
        checkbox.dataset.deleteUrl = action;
        checkbox.setAttribute("aria-label", "Select lesson note");

        row.classList.add("study-note-row");

        const content = document.createElement("div");
        content.className = "note-content";

        while (row.firstChild) {
            content.appendChild(row.firstChild);
        }

        row.appendChild(checkbox);
        row.appendChild(content);
    });

    const selectAll = document.getElementById("select-all-notes");

    selectAll.addEventListener("change", function () {
        document.querySelectorAll(".note-checkbox").forEach(box => {
            box.checked = selectAll.checked;
        });
    });

    document.getElementById("bulk-note-delete-form").addEventListener("submit", async function (event) {
        event.preventDefault();

        const selected = Array.from(
            document.querySelectorAll(".note-checkbox:checked")
        );

        if (!selected.length) {
            alert("Please select at least one lesson note to delete.");
            return;
        }

        if (!confirm(`Are you sure you want to delete ${selected.length} lesson note(s)?`)) {
            return;
        }

        const button = document.querySelector(
            ".study-bulk-note-actions button"
        );
        button.disabled = true;
        button.textContent = "Deleting...";

        try {
            for (const checkbox of selected) {
                const body = new URLSearchParams();
                body.append("csrf_token", csrfToken);

                const result = await fetch(checkbox.dataset.deleteUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: body.toString(),
                    credentials: "same-origin"
                });

                if (!result.ok) {
                    throw new Error("A lesson note could not be deleted.");
                }
            }

            window.location.href = "/admin";
        } catch (error) {
            button.disabled = false;
            button.textContent = "🗑️ Delete Selected";
            alert("Something went wrong while deleting the selected notes. Please refresh and try again.");
        }
    });
})();
</script>
"""

    if "</body>" in html:
        html = html.replace("</body>", script + "</body>", 1)
    else:
        html += script

    response.set_data(html)
    return response
