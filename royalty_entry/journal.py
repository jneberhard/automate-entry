"""Write-ahead records prevent blind retries after a partially saved payment."""
import sqlite3
from datetime import datetime, timezone
from .rules import normalized


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=2)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS entries (
            license TEXT, publisher TEXT, reference TEXT, status TEXT,
            amount TEXT, detail TEXT, updated TEXT,
            PRIMARY KEY (license, publisher, reference))''')
        self.db.commit()

    def get(self, record, reference):
        result = self.db.execute('SELECT status, amount, detail FROM entries WHERE license=? AND publisher=? AND reference=?',
                               (*record.key, normalized(reference))).fetchone()
        if result is None and record.publisher_number:
            # Existing installations recorded payments under publisher names.
            # Honor those records so upgrading never retries an old payment.
            result = self.db.execute('SELECT status, amount, detail FROM entries WHERE license=? AND publisher=? AND reference=?',
                (record.license, normalized(record.publisher), normalized(reference))).fetchone()
        return result

    def put(self, record, reference, status, amount='', detail=''):
        self.db.execute('''INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(license,publisher,reference) DO UPDATE SET
            status=excluded.status, amount=excluded.amount, detail=excluded.detail, updated=excluded.updated''',
            (*record.key, normalized(reference), status, str(amount), detail, datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def close(self):
        self.db.close()

    def paid_licenses(self, reference):
        return {row[0] for row in self.db.execute(
            "SELECT DISTINCT license FROM entries WHERE reference=? AND status='paid'",
            (normalized(reference),))}
