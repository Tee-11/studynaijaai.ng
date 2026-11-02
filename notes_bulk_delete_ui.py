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
    toolbar.style.marginBottom = "20px";
    toolbar.style.padding = "15px";
    toolbar.style.border = "1px solid #dbe3ef";
    toolbar.style.borderRadius = "12px";
    toolbar.style.background = "#f8fafc";

    toolbar.innerHTML = `
        <form
            id="bulk-note-delete-form"
            style="margin:0;"
        >
            <label
                style="display:flex; align-items:center; gap:8px; cursor:pointer; font-weight:600;"
            >
                <input
                    type="checkbox"
                    id="select-all-notes"
                >
                Select All Lesson Notes
            </label>

            <button
                type="submit"
                class="danger-button"
                style="margin-top:12px;"
            >
                🗑️ Delete Selected Notes
            </button>
        </form>
    `;

    notesCard.insertBefore(toolbar, rows[0]);

    rows.forEach(row => {
        const form = row.querySelector("form");
        if (!form) return;

        const action = form.getAttribute("action") || "";
        const match = action.match(/\/admin\/note\/delete\/(\d+)/);
        if (!match) return;

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = match[1];
        checkbox.className = "note-checkbox";
        checkbox.dataset.deleteUrl = action;
        checkbox.style.marginRight = "10px";
        checkbox.style.flexShrink = "0";

        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.gap = "8px";

        row.insertBefore(checkbox, row.firstChild);
    });

    const selectAll = document.getElementById("select-all-notes");

    if (selectAll) {
        selectAll.addEventListener("change", function () {
            document.querySelectorAll(".note-checkbox").forEach(box => {
                box.checked = selectAll.checked;
            });
        });
    }

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

        const button = this.querySelector("button[type='submit']");
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
            button.textContent = "🗑️ Delete Selected Notes";
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
