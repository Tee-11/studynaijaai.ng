from flask import render_template, flash, redirect, url_for, request

import datetime
import requests

import app as app_module
import wsgi

from app import (
    app,
    USE_POSTGRES,
    login_required,
    query,
)


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


def initialize_premium_payment_fixed():
    user = app_module.current_user()

    if user["plan"] == "premium":
        flash("You already have Premium access.", "info")
        return redirect(url_for("premium"))

    paystack_secret_key = app_module.PAYSTACK_SECRET_KEY

    if not paystack_secret_key:
        flash("Payment system is not configured yet.", "danger")
        return redirect(url_for("premium"))

    reference = f"STUDYNAIJA-{user['id']}-{int(__import__('time').time())}"

    payment_data = {
        "email": user["email"],
        "amount": app_module.PAYSTACK_PLAN_AMOUNT,
        "currency": app_module.PAYSTACK_CURRENCY,
        "reference": reference,
        "callback_url": url_for("payment_callback", _external=True)
    }

    headers = {
        "Authorization": f"Bearer {paystack_secret_key}",
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

    insert_sql = (
        """
        INSERT INTO payments
        (user_id, reference, amount, currency, status)
        VALUES (%s, %s, %s, %s, %s)
        """
        if USE_POSTGRES
        else
        """
        INSERT INTO payments
        (user_id, reference, amount, currency, status)
        VALUES (?, ?, ?, ?, ?)
        """
    )

    query(
        insert_sql,
        (
            user["id"],
            reference,
            app_module.PAYSTACK_PLAN_AMOUNT,
            app_module.PAYSTACK_CURRENCY,
            "pending"
        ),
        commit=True
    )

    authorization_url = result["data"]["authorization_url"]
    return redirect(authorization_url)


def payment_callback_fixed():
    reference = request.args.get("reference", "").strip()

    if not reference:
        flash("Payment reference is missing.", "danger")
        return redirect(url_for("premium"))

    select_sql = (
        """
        SELECT id, user_id, amount, currency, status
        FROM payments
        WHERE reference = %s
        """
        if USE_POSTGRES
        else
        """
        SELECT id, user_id, amount, currency, status
        FROM payments
        WHERE reference = ?
        """
    )

    payment = query(select_sql, (reference,), one=True)
    user = app_module.current_user()

    if not payment or payment["user_id"] != user["id"]:
        flash("Payment record not found.", "danger")
        return redirect(url_for("premium"))

    if payment["status"] == "success":
        flash("This payment has already been processed.", "success")
        return redirect(url_for("premium"))

    paystack_secret_key = app_module.PAYSTACK_SECRET_KEY
    headers = {
        "Authorization": f"Bearer {paystack_secret_key}",
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
        update_failed_sql = (
            "UPDATE payments SET status = %s WHERE reference = %s"
            if USE_POSTGRES
            else
            "UPDATE payments SET status = ? WHERE reference = ?"
        )
        query(update_failed_sql, ("failed", reference), commit=True)

        flash(
            "The payment could not be confirmed. Your plan has not been changed.",
            "danger"
        )
        return redirect(url_for("premium"))

    update_success_sql = (
        "UPDATE payments SET status = %s, paid_at = CURRENT_TIMESTAMP WHERE reference = %s"
        if USE_POSTGRES
        else
        "UPDATE payments SET status = ?, paid_at = CURRENT_TIMESTAMP WHERE reference = ?"
    )
    query(update_success_sql, ("success", reference), commit=True)

    premium_expires_at = datetime.datetime.now() + datetime.timedelta(days=30)

    update_user_sql = (
        "UPDATE users SET plan = %s, premium_expires_at = %s WHERE id = %s"
        if USE_POSTGRES
        else
        "UPDATE users SET plan = ?, premium_expires_at = ? WHERE id = ?"
    )
    query(
        update_user_sql,
        ("premium", premium_expires_at, payment["user_id"]),
        commit=True
    )

    flash(
        "Payment verified! Welcome to StudyNaija Premium.",
        "success"
    )

    return redirect(url_for("premium"))


app.view_functions["payment_history"] = login_required(payment_history_fixed)
app.view_functions["payment_receipt"] = login_required(payment_receipt_fixed)
app.view_functions["initialize_premium_payment"] = login_required(initialize_premium_payment_fixed)
app.view_functions["payment_callback"] = login_required(payment_callback_fixed)
