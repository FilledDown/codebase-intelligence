from flask import session
from werkzeug.security import check_password_hash

from app import db


def login(username, password):
    row = db.connect().execute("select id, pw_hash from users where name=?", (username,)).fetchone()
    if row and check_password_hash(row["pw_hash"], password):
        session["user_id"] = row["id"]
        return True
    return False


def current_user_id():
    return session.get("user_id")
