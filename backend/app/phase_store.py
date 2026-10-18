"""Additive, transactional schema migration; existing tables are untouched."""
import json

def migrate(db):
    with db.lock, db.connection:
        db.connection.executescript('''
        CREATE TABLE IF NOT EXISTS phase_migrations(version INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS farm_events(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          kind TEXT NOT NULL, data TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        CREATE INDEX IF NOT EXISTS farm_events_owner ON farm_events(user_id,kind,id DESC);
        CREATE TABLE IF NOT EXISTS mandi_prices(
          id INTEGER PRIMARY KEY, state TEXT NOT NULL, district TEXT NOT NULL,
          market TEXT NOT NULL, commodity TEXT NOT NULL, variety TEXT NOT NULL,
          date TEXT NOT NULL, minimum REAL NOT NULL, maximum REAL NOT NULL,
          modal REAL NOT NULL, unit TEXT NOT NULL, source TEXT NOT NULL,
          original TEXT NOT NULL, synced_at TEXT NOT NULL,
          UNIQUE(state,district,market,commodity,variety,date,source));
        CREATE TABLE IF NOT EXISTS msp_records(
          crop TEXT NOT NULL, variety TEXT NOT NULL, season TEXT NOT NULL,
          price REAL NOT NULL, unit TEXT NOT NULL, source TEXT NOT NULL,
          period_start TEXT, period_end TEXT,
          PRIMARY KEY(crop,variety,season));
        INSERT OR IGNORE INTO phase_migrations VALUES(3);
        ''')
        columns={row[1] for row in db.connection.execute('PRAGMA table_info(msp_records)')}
        for column in ['period_start','period_end']:
            if column not in columns: db.connection.execute(f'ALTER TABLE msp_records ADD COLUMN {column} TEXT')

def record(db, user, kind, data):
    with db.lock, db.connection:
        result = db.connection.execute('INSERT INTO farm_events(user_id,kind,data) VALUES(?,?,?)',
            (user,kind,json.dumps(data,allow_nan=False)))
        return result.lastrowid

def history(db, user, kind):
    with db.lock:
        rows = db.connection.execute('SELECT * FROM farm_events WHERE user_id=? AND kind=? ORDER BY id DESC LIMIT 100',(user,kind)).fetchall()
    return [{'id':r['id'],'createdAt':r['created_at'], **json.loads(r['data'])} for r in rows]
