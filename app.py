import os
import sqlite3
import json
import random
import requests
import time
import csv
import io
from functools import wraps
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PLAN_AMOUNT = 500000
PAYSTACK_CURRENCY = "NGN"
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor


def db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)

    conn = sqlite3.connect("studynaija.db")
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=(), one=False, commit=False):
    conn = db()

    try:
        if USE_POSTGRES:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(sql, params)

            if commit:
                conn.commit()
                result = None
            else:
                result = cur.fetchone() if one else cur.fetchall()

            cur.close()

        else:
            cur = conn.execute(sql, params)

            if commit:
                conn.commit()
                result = None
            else:
                result = cur.fetchone() if one else cur.fetchall()

        return result

    finally:
        conn.close()


