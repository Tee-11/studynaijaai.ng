from flask import render_template, flash, redirect, url_for

import app as app_module
import wsgi

from app import app, USE_POSTGRES, login_required, query


def payment_history_fixed():
    user = app_module.current_user()

    sql = (
        """
        SELECT reference, amount, currency, status, paid_at, created_at
        FROM payments
        WHERE user_id = %s
        ORDER BY id DESC
        """
        if USE_POSTGRES
        else
        """
        SELECT reference, amount, currency, status, paid_at, created_at
        FROM payments
        WHERE user_id = ?
        ORDER BY id DESC
        """
    )

    payments = query(sql, (user["id"],))

    return render_template(
        "payment_history.html",
        payments=payments
    )


def payment_receipt_fixed(reference):
    user = app_module.current_user()

    sql = (
        """
        SELECT reference, amount, currency, status, paid_at, created_at
        FROM payments
        WHERE reference = %s AND user_id = %s
        """
        if USE_POSTGRES
        else
        """
        SELECT reference, amount, currency, status, paid_at, created_at
        FROM payments
        WHERE reference = ? AND user_id = ?
        """
    )

    payment = query(
        sql,
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


app.view_functions["payment_history"] = login_required(payment_history_fixed)
app.view_functions["payment_receipt"] = login_required(payment_receipt_fixed)
