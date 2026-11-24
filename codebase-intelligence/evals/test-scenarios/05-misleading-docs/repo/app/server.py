import os

from flask import Flask, jsonify, request

from app import auth, db

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]


@app.post("/login")
def login():
    ok = auth.login(request.json["username"], request.json["password"])
    return jsonify(ok=ok), (200 if ok else 401)


@app.get("/notes")
def notes():
    uid = auth.current_user_id()
    if uid is None:
        return jsonify(error="unauthorised"), 401
    rows = db.connect().execute("select id, body from notes where user_id=?", (uid,)).fetchall()
    return jsonify([dict(r) for r in rows])
