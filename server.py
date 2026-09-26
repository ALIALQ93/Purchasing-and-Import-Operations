# -*- coding: utf-8 -*-
"""Local server for the customs calculator and its SQLite database."""
import json
import os
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "calculator.db")
HOST = "127.0.0.1"
PORT = 8765


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    return conn


def list_records():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, updated_at FROM records ORDER BY datetime(updated_at) DESC, id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_record(rec_id):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, name, payload, updated_at FROM records WHERE id = ?",
            (int(rec_id),),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data["payload"])
        return data
    finally:
        conn.close()


def save_record(body):
    name = str(body.get("name") or "").strip()[:120]
    payload = body.get("payload")
    if not name or not isinstance(payload, dict):
        raise ValueError("invalid")
    blob = json.dumps(payload, ensure_ascii=False)
    rec_id = body.get("id")
    conn = connect()
    try:
        if rec_id not in (None, ""):
            cur = conn.execute(
                """
                UPDATE records
                SET name = ?, payload = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (name, blob, int(rec_id)),
            )
            if cur.rowcount == 0:
                rec_id = None
        if rec_id in (None, ""):
            cur = conn.execute(
                "INSERT INTO records (name, payload) VALUES (?, ?)",
                (name, blob),
            )
            rec_id = cur.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT id, name, updated_at FROM records WHERE id = ?",
            (rec_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_record(rec_id):
    conn = connect()
    try:
        conn.execute("DELETE FROM records WHERE id = ?", (int(rec_id),))
        conn.commit()
    finally:
        conn.close()


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 2_000_000:
            raise ValueError("body")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _record_id(self):
        path = urlparse(self.path).path.rstrip("/")
        part = path.rsplit("/", 1)[-1]
        if not part.isdigit():
            raise ValueError("id")
        return int(part)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/api/health":
            return self._json({"ok": True})
        if path == "/api/records":
            return self._json(list_records())
        if path.startswith("/api/records/"):
            try:
                rec = get_record(self._record_id())
            except ValueError:
                return self._json({"error": "invalid"}, 400)
            if not rec:
                return self._json({"error": "not found"}, 404)
            return self._json(rec)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path != "/api/records":
            return self._json({"error": "not found"}, 404)
        try:
            saved = save_record(self._read_json())
        except (ValueError, json.JSONDecodeError, sqlite3.Error):
            return self._json({"error": "invalid"}, 400)
        return self._json(saved)

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip("/")
        if not path.startswith("/api/records/"):
            return self._json({"error": "not found"}, 404)
        try:
            delete_record(self._record_id())
        except ValueError:
            return self._json({"error": "invalid"}, 400)
        return self._json({"ok": True})

    def log_message(self, fmt, *args):
        if str(args[0]).startswith("GET /api") or str(args[0]).startswith("POST /api") or str(args[0]).startswith("DELETE /api"):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    connect().close()
    try:
        server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    except OSError:
        print("المنفذ %s مستخدم. أغلق نافذة التشغيل السابقة ثم أعد فتح الملف." % PORT)
        raise SystemExit(1)
    print("الحاسبة تعمل على http://%s:%s/customs-calculator.html" % (HOST, PORT))
    print("قاعدة البيانات: %s" % DB_PATH)
    print("أغلق هذه النافذة لإيقاف البرنامج.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم الإيقاف.")
    finally:
        server.server_close()
