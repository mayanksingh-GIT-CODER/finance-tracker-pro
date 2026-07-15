"""Small SQLite repository layer with strict per-user data isolation."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                    category TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                    occurred_on TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_user_date
                    ON transactions(user_id, occurred_on DESC);
                """
            )

    def create_user(self, name: str, email: str, password_hash: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO users(name, email, password_hash) VALUES (?, ?, ?)",
                (name.strip(), email.strip().lower(), password_hash),
            )
            return int(cursor.lastrowid)

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),)
            ).fetchone()
        return dict(row) if row else None

    def user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def add_transaction(
        self,
        user_id: int,
        kind: str,
        category: str,
        amount_cents: int,
        occurred_on: date,
        note: str = "",
    ) -> int:
        if kind not in {"income", "expense"}:
            raise ValueError("Transaction kind must be income or expense")
        if amount_cents <= 0:
            raise ValueError("Amount must be greater than zero")
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO transactions
                   (user_id, kind, category, amount_cents, occurred_on, note)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, kind, category.strip(), amount_cents, occurred_on.isoformat(), note.strip()),
            )
            return int(cursor.lastrowid)

    def delete_transaction(self, user_id: int, transaction_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM transactions WHERE id = ? AND user_id = ?",
                (transaction_id, user_id),
            )
            return cursor.rowcount == 1

    def transactions(self, user_id: int, month: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM transactions WHERE user_id = ?"
        params: list[Any] = [user_id]
        if month:
            sql += " AND substr(occurred_on, 1, 7) = ?"
            params.append(month)
        sql += " ORDER BY occurred_on DESC, id DESC"
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def summary(self, user_id: int, month: str | None = None) -> dict[str, Any]:
        items = self.transactions(user_id, month)
        income = sum(item["amount_cents"] for item in items if item["kind"] == "income")
        expenses = sum(item["amount_cents"] for item in items if item["kind"] == "expense")
        categories: dict[str, int] = {}
        for item in items:
            if item["kind"] == "expense":
                categories[item["category"]] = categories.get(item["category"], 0) + item["amount_cents"]
        return {
            "income_cents": income,
            "expense_cents": expenses,
            "balance_cents": income - expenses,
            "categories": categories,
            "count": len(items),
        }
