"""SQLite schema remains compatible with the original prototype."""
import json
import sqlite3
from pathlib import Path
from threading import RLock

class Database:
    def __init__(self, filename: str):
        if filename != ':memory:':
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(filename, check_same_thread=False, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        self.connection.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS farms (user_id INTEGER PRIMARY KEY REFERENCES users(id), data TEXT NOT NULL, photo TEXT);
            CREATE TABLE IF NOT EXISTS otp_challenges (phone TEXT PRIMARY KEY, hash TEXT NOT NULL, expires INTEGER NOT NULL, requested INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
        ''')

    def farm_for(self, user_id: int):
        with self.lock:
            row = self.connection.execute('SELECT * FROM farms WHERE user_id=?', (user_id,)).fetchone()
            return {**json.loads(row['data']), 'hasPhoto': bool(row['photo'])} if row else None

    def close(self):
        self.connection.close()
