"""CRUD-операції для відгуків користувачів."""
from .db import get_db


def create_feedback(name, email, message):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO feedback (name, email, message) VALUES (?, ?, ?)",
        (name.strip(), email.strip(), message.strip()),
    )
    db.commit()
    return cursor.lastrowid


def get_all_feedback():
    return get_db().execute(
        "SELECT id, name, email, message, created_at FROM feedback ORDER BY created_at DESC, id DESC"
    ).fetchall()


def get_feedback(feedback_id):
    return get_db().execute(
        "SELECT id, name, email, message, created_at FROM feedback WHERE id = ?",
        (feedback_id,),
    ).fetchone()


def delete_feedback(feedback_id):
    db = get_db()
    cursor = db.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    db.commit()
    return cursor.rowcount > 0
