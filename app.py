from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PORTABLE_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA_DIR = PORTABLE_ROOT / "data"
DB_PATH = DATA_DIR / "catalog.db"
THUMB_DIR = DATA_DIR / "thumbnails"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".webm", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg"}
SUPPORTED = IMAGE_EXTS | VIDEO_EXTS
state = {"scanning": False, "seen": 0, "indexed": 0, "message": "Ready", "started": None}


def connection():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS media (
              id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
              kind TEXT NOT NULL, taken REAL NOT NULL, date_source TEXT NOT NULL,
              size INTEGER NOT NULL, mtime REAL NOT NULL, thumb TEXT
            );
            CREATE INDEX IF NOT EXISTS media_taken ON media(taken DESC);
            CREATE INDEX IF NOT EXISTS media_kind ON media(kind);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)


def get_library():
    with connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key='library'").fetchone()
    return Path(row["value"]) if row and row["value"] else None


def set_library(path: Path):
    with connection() as db:
        db.execute("INSERT INTO settings(key,value) VALUES('library',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(path),))


def choose_library():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Choose your photo and video library")
        root.destroy()
        if selected:
            set_library(Path(selected))
            return Path(selected)
    except Exception:
        pass
    return None


def jpeg_exif_date(path: Path):
    try:
        data = path.read_bytes()[:2_000_000]
        if not data.startswith(b"\xff\xd8"):
            return None
        pos = 2
        while pos + 4 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            size = int.from_bytes(data[pos + 2:pos + 4], "big")
            block = data[pos + 4:pos + 2 + size]
            pos += 2 + size
            if marker != 0xE1 or not block.startswith(b"Exif\x00\x00"):
                continue
            tiff = block[6:]
            endian = "<" if tiff[:2] == b"II" else ">"
            ifd0 = struct.unpack(endian + "I", tiff[4:8])[0]
            count = struct.unpack(endian + "H", tiff[ifd0:ifd0 + 2])[0]
            exif_offset = None
            for i in range(count):
                entry = tiff[ifd0 + 2 + i * 12:ifd0 + 14 + i * 12]
                tag, typ, num, val = struct.unpack(endian + "HHII", entry)
                if tag == 0x8769:
                    exif_offset = val
            offsets = [ifd0]
            if exif_offset:
                offsets.insert(0, exif_offset)
            for offset in offsets:
                count = struct.unpack(endian + "H", tiff[offset:offset + 2])[0]
                for i in range(count):
                    entry = tiff[offset + 2 + i * 12:offset + 14 + i * 12]
                    tag, typ, num, val = struct.unpack(endian + "HHII", entry)
                    if tag in (0x9003, 0x9004, 0x0132) and typ == 2:
                        raw = tiff[val:val + num] if num > 4 else entry[8:8 + num]
                        text = raw.rstrip(b"\0").decode("ascii", "ignore")
                        try:
                            return dt.datetime.strptime(text, "%Y:%m:%d %H:%M:%S").timestamp()
                        except ValueError:
                            pass
    except (OSError, ValueError, struct.error):
        pass
    return None


def filename_date(name: str):
    patterns = [
        r"(?<!\d)(19\d{2}|20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)?([0-5]\d)?([0-5]\d)?",
        r"(?<!\d)([01]\d)([0-3]\d)(19\d{2}|20\d{2})(?!\d)",
    ]
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, name)
        if not match:
            continue
        try:
            values = [int(x) if x else 0 for x in match.groups()]
            if index == 0:
                y, m, d, hh, mm, ss = values
            else:
                m, d, y = values
                hh = mm = ss = 0
            return dt.datetime(y, m, d, hh, mm, ss).timestamp()
        except ValueError:
            pass
    return None


def capture_date(path: Path, stat):
    if path.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff"}:
        value = jpeg_exif_date(path)
        if value:
            return value, "camera metadata"
    value = filename_date(path.name)
    if value:
        return value, "filename"
    return stat.st_mtime, "file modified"


def create_thumb(path: Path, kind: str):
    key = hashlib.sha1(str(path).encode("utf-8", "surrogatepass")).hexdigest() + ".jpg"
    target = THUMB_DIR / key
    if target.exists():
        return key
    try:
        from PIL import Image, ImageOps
        if kind == "image":
            with Image.open(path) as source:
                source = ImageOps.exif_transpose(source).convert("RGB")
                thumb = ImageOps.fit(source, (480, 320), Image.Resampling.LANCZOS)
                thumb.save(target, "JPEG", quality=76, optimize=True)
        else:
            import imageio_ffmpeg
            reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24", output_params=["-frames:v", "1"])
            metadata = next(reader)
            frame = next(reader)
            width, height = metadata["size"]
            source = Image.frombytes("RGB", (width, height), frame)
            thumb = ImageOps.fit(source, (480, 320), Image.Resampling.LANCZOS)
            thumb.save(target, "JPEG", quality=76, optimize=True)
        return key if target.exists() else None
    except Exception:
        return None


def scan_library():
    if state["scanning"]:
        return
    state.update(scanning=True, seen=0, indexed=0, message="Starting scan…", started=time.time())
    library = get_library()
    if not library or not library.exists():
        state.update(scanning=False, message=f"Folder not found: {library}")
        return
    try:
        with connection() as db:
            known = {r["path"]: (r["mtime"], r["size"]) for r in db.execute("SELECT path,mtime,size FROM media")}
            touched = set()
            pending = 0
            for root, dirs, files in os.walk(library):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in files:
                    path = Path(root) / name
                    if path.suffix.lower() not in SUPPORTED:
                        continue
                    state["seen"] += 1
                    touched.add(str(path))
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    if known.get(str(path)) == (stat.st_mtime, stat.st_size):
                        continue
                    kind = "image" if path.suffix.lower() in IMAGE_EXTS else "video"
                    taken, source = capture_date(path, stat)
                    thumb = create_thumb(path, kind)
                    db.execute("""INSERT INTO media(path,name,kind,taken,date_source,size,mtime,thumb)
                                  VALUES(?,?,?,?,?,?,?,?)
                                  ON CONFLICT(path) DO UPDATE SET name=excluded.name,kind=excluded.kind,
                                  taken=excluded.taken,date_source=excluded.date_source,size=excluded.size,
                                  mtime=excluded.mtime,thumb=excluded.thumb""",
                               (str(path), name, kind, taken, source, stat.st_size, stat.st_mtime, thumb))
                    state["indexed"] += 1
                    pending += 1
                    if pending >= 25:
                        db.commit()
                        pending = 0
                    state["message"] = f"Scanning… {state['seen']:,} media files found"
            if known:
                removed = set(known) - touched
                db.executemany("DELETE FROM media WHERE path=?", ((p,) for p in removed))
            db.commit()
        state["message"] = f"Scan complete — {state['seen']:,} media files"
    except Exception as exc:
        state["message"] = f"Scan stopped: {exc}"
    finally:
        state["scanning"] = False


def start_scan():
    if not state["scanning"]:
        threading.Thread(target=scan_library, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "ChronologicalMediaViewer/1.0"

    def log_message(self, fmt, *args):
        return

    def json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/scan":
            start_scan()
            return self.json(state)
        if self.path == "/api/library":
            library = choose_library()
            if not library:
                return self.json({"changed": False})
            with connection() as db:
                db.execute("DELETE FROM media")
            start_scan()
            return self.json({"changed": True, "library": str(library)})
        if self.path == "/api/shutdown":
            self.json({"stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self.send_error(404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            return self.send_file(APP_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/app.js":
            return self.send_file(APP_DIR / "app.js", "text/javascript; charset=utf-8")
        if parsed.path == "/style.css":
            return self.send_file(APP_DIR / "style.css", "text/css; charset=utf-8")
        if parsed.path == "/api/status":
            with connection() as db:
                total = db.execute("SELECT count(*) FROM media").fetchone()[0]
                first, last = db.execute("SELECT min(taken),max(taken) FROM media").fetchone()
            library = get_library()
            return self.json({**state, "total": total, "first": first, "last": last, "library": str(library) if library else None})
        if parsed.path == "/api/media":
            q = urllib.parse.parse_qs(parsed.query)
            limit = min(int(q.get("limit", ["120"])[0]), 300)
            offset = max(int(q.get("offset", ["0"])[0]), 0)
            kind = q.get("kind", ["all"])[0]
            year = q.get("year", [""])[0]
            clauses, args = [], []
            if kind in ("image", "video"):
                clauses.append("kind=?")
                args.append(kind)
            if year.isdigit():
                start = dt.datetime(int(year), 1, 1).timestamp()
                end = dt.datetime(int(year) + 1, 1, 1).timestamp()
                clauses.append("taken>=? AND taken<?")
                args += [start, end]
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            with connection() as db:
                rows = db.execute(f"SELECT id,name,kind,taken,date_source,thumb FROM media{where} ORDER BY taken DESC,id DESC LIMIT ? OFFSET ?",
                                  (*args, limit, offset)).fetchall()
            return self.json([dict(r) for r in rows])
        if parsed.path.startswith("/thumb/"):
            name = Path(parsed.path).name
            return self.send_file(THUMB_DIR / name, "image/jpeg", cache=True)
        if parsed.path.startswith("/media/"):
            try:
                media_id = int(parsed.path.rsplit("/", 1)[1])
                with connection() as db:
                    row = db.execute("SELECT path FROM media WHERE id=?", (media_id,)).fetchone()
                if not row:
                    return self.send_error(404)
                return self.send_file(Path(row["path"]), mimetypes.guess_type(row["path"])[0] or "application/octet-stream", ranges=True)
            except ValueError:
                return self.send_error(400)
        self.send_error(404)

    def send_file(self, path: Path, content_type: str, cache=False, ranges=False):
        try:
            size = path.stat().st_size
            start, end = 0, size - 1
            status = 200
            if ranges and self.headers.get("Range"):
                match = re.match(r"bytes=(\d*)-(\d*)", self.headers["Range"])
                if match:
                    start = int(match.group(1) or 0)
                    end = min(int(match.group(2) or end), end)
                    status = 206
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "public, max-age=31536000" if cache else "no-cache")
            self.end_headers()
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (OSError, BrokenPipeError, ConnectionResetError):
            if not self.wfile.closed:
                try:
                    self.send_error(404)
                except OSError:
                    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    init_db()
    if not get_library():
        choose_library()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    start_scan()
    print(f"Chronological Media Viewer is running at http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
