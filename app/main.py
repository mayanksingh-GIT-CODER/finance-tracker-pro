"""FastAPI web application for Finance Tracker Pro."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import Database
from .security import SessionSigner, hash_password, verify_password

BASE_DIR = Path(__file__).resolve().parent


def money(cents: int) -> str:
    return f"₹{cents / 100:,.2f}"


def amount_to_cents(raw: str) -> int:
    try:
        value = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Enter a valid amount") from exc
    cents = int(value * 100)
    if cents <= 0:
        raise ValueError("Amount must be greater than zero")
    return cents


def create_app(db_path: str | Path | None = None, secret_key: str | None = None) -> FastAPI:
    database = Database(db_path or os.getenv("DATABASE_PATH", "data/finance.db"))
    signer = SessionSigner(secret_key or os.getenv("SECRET_KEY", "dev-only-change-me"))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        yield

    app = FastAPI(title="Finance Tracker Pro", version="1.0.0", lifespan=lifespan)
    app.state.database = database
    app.state.signer = signer
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    templates.env.filters["money"] = money

    def signed_in_user(request: Request):
        token = request.cookies.get("finance_session", "")
        user_id = signer.read(token) if token else None
        return database.user_by_id(user_id) if user_id else None

    def render(request: Request, template: str, **context):
        return templates.TemplateResponse(
            request=request,
            name=template,
            context={"user": signed_in_user(request), **context},
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "finance-tracker-pro"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return RedirectResponse("/dashboard" if signed_in_user(request) else "/login", status_code=303)

    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request):
        return render(request, "register.html", error=None)

    @app.post("/register")
    def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
        if not name.strip() or "@" not in email:
            return render(request, "register.html", error="Enter a valid name and email")
        try:
            user_id = database.create_user(name, email, hash_password(password))
        except ValueError as exc:
            return render(request, "register.html", error=str(exc))
        except sqlite3.IntegrityError:
            return render(request, "register.html", error="An account with that email already exists")
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie("finance_session", signer.create(user_id), httponly=True, samesite="lax")
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return render(request, "login.html", error=None)

    @app.post("/login")
    def login(request: Request, email: str = Form(...), password: str = Form(...)):
        user = database.user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            return render(request, "login.html", error="Invalid email or password")
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie("finance_session", signer.create(user["id"]), httponly=True, samesite="lax")
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("finance_session")
        return response

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request):
        user = signed_in_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        items = database.transactions(user["id"])
        return render(request, "dashboard.html", items=items, summary=database.summary(user["id"]), today=date.today())

    @app.post("/transactions")
    def add_transaction(
        request: Request,
        kind: str = Form(...),
        category: str = Form(...),
        amount: str = Form(...),
        occurred_on: date = Form(...),
        note: str = Form(""),
    ):
        user = signed_in_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        try:
            database.add_transaction(user["id"], kind, category, amount_to_cents(amount), occurred_on, note)
        except ValueError as exc:
            return RedirectResponse(f"/dashboard?error={str(exc)}", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)

    @app.post("/transactions/{transaction_id}/delete")
    def delete_transaction(request: Request, transaction_id: int):
        user = signed_in_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        database.delete_transaction(user["id"], transaction_id)
        return RedirectResponse("/dashboard", status_code=303)

    @app.get("/reports", response_class=HTMLResponse)
    def reports(request: Request, month: str | None = None):
        user = signed_in_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        selected_month = month or date.today().strftime("%Y-%m")
        return render(
            request,
            "reports.html",
            month=selected_month,
            items=database.transactions(user["id"], selected_month),
            summary=database.summary(user["id"], selected_month),
        )

    @app.get("/export.csv")
    def export_csv(request: Request, month: str | None = None):
        user = signed_in_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "type", "category", "amount", "note"])
        for item in database.transactions(user["id"], month):
            writer.writerow([item["occurred_on"], item["kind"], item["category"], f"{item['amount_cents'] / 100:.2f}", item["note"]])
        filename = f"finance-transactions-{month or 'all'}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


app = create_app()
