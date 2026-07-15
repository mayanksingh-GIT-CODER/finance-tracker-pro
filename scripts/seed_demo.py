"""Create a local demo account and representative transaction data."""

from datetime import date, timedelta
from pathlib import Path

from app.database import Database
from app.security import hash_password


def main() -> None:
    database = Database(Path("data") / "finance.db")
    database.initialize()
    user = database.user_by_email("demo@example.com")
    if not user:
        user_id = database.create_user("Mayank", "demo@example.com", hash_password("demo-pass-123"))
    else:
        user_id = user["id"]
    if database.transactions(user_id):
        print("Demo data already exists.")
        return

    today = date.today()
    samples = [
        ("income", "Freelance", 48_000_00, today - timedelta(days=12), "Product prototype"),
        ("income", "Stipend", 18_000_00, today - timedelta(days=6), "Monthly internship stipend"),
        ("expense", "Learning", 4_299_00, today - timedelta(days=10), "AI engineering course"),
        ("expense", "Equipment", 8_450_00, today - timedelta(days=8), "Webcam and microphone"),
        ("expense", "Food", 3_780_00, today - timedelta(days=4), "Meals and groceries"),
        ("expense", "Transport", 2_150_00, today - timedelta(days=2), "Local travel"),
    ]
    for kind, category, amount, occurred_on, note in samples:
        database.add_transaction(user_id, kind, category, amount, occurred_on, note)
    print("Demo account: demo@example.com / demo-pass-123")


if __name__ == "__main__":
    main()
