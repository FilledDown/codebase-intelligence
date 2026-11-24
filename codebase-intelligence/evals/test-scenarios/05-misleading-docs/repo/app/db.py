import os
import sqlite3

DB_PATH = os.environ.get("NOTES_DB", "notes.sqlite3")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
