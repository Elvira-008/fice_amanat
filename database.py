import hashlib
import hmac
import secrets
import sqlite3
import threading
from datetime import datetime

import numpy as np

from settings import DB_NAME, TEACHER_PASSWORD

attendance_lock = threading.Lock()


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=15)
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            name TEXT PRIMARY KEY,
            class_name TEXT,
            parent_id TEXT,
            photo_path TEXT,
            embedding BLOB,
            parent_name TEXT,
            parent_code TEXT,
            role TEXT DEFAULT 'student'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            class_name TEXT,
            status TEXT,
            timestamp TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parents (
            code TEXT PRIMARY KEY,
            name TEXT,
            role TEXT DEFAULT 'parent'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            login TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            class_names TEXT NOT NULL DEFAULT ''
        )
    """)
    # === КӨП-РАКУРСТУК ТААНУУ ҮЧҮН ЖАҢЫ ТАБЛИЦА ===
    # Бир окуучуга бир нече ракурстун (front/left/right/up/down) эмбеддингин сактайт.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS face_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            angle_label TEXT DEFAULT 'front',
            embedding BLOB NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (name) REFERENCES students(name) ON DELETE CASCADE
        )
    """)

    ensure_column(cursor, "students", "parent_name", "TEXT")
    ensure_column(cursor, "students", "parent_code", "TEXT")
    ensure_column(cursor, "students", "role", "TEXT DEFAULT 'student'")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_name_day
        ON attendance (name, timestamp, id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_class_time
        ON attendance (class_name, timestamp, id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_students_parent
        ON students (parent_code, parent_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_face_embeddings_name
        ON face_embeddings (name)
    """)

    cursor.execute("SELECT 1 FROM teachers LIMIT 1")
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO teachers (login, password_hash, class_names) VALUES (?, ?, ?)",
            ("teacher", hash_password(TEACHER_PASSWORD), ""),
        )

    conn.commit()
    conn.close()


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password, stored_hash):
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (AttributeError, ValueError):
        return False


def save_teacher(login, password, class_names):
    login = login.strip()
    classes = [value.strip() for value in class_names if value.strip()]
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash, class_names FROM teachers WHERE login = ?", (login,))
    existing = cur.fetchone()
    password_hash = hash_password(password) if password else (existing[0] if existing else "")
    if not login or not password_hash:
        conn.close()
        return False
    existing_classes = [value for value in existing[1].split(",") if value] if existing else []
    merged_classes = list(dict.fromkeys(existing_classes + classes))
    cur.execute(
        "INSERT OR REPLACE INTO teachers (login, password_hash, class_names) VALUES (?, ?, ?)",
        (login, password_hash, ",".join(merged_classes)),
    )
    conn.commit()
    conn.close()
    return True


def authenticate_teacher(login, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash, class_names FROM teachers WHERE login = ?", (login.strip(),))
    row = cur.fetchone()
    conn.close()
    if row is None or not verify_password(password, row[0]):
        return None
    return [value for value in row[1].split(",") if value]


def get_teachers():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT login, class_names FROM teachers ORDER BY login")
    rows = [(login, [value for value in classes.split(",") if value]) for login, classes in cur.fetchall()]
    conn.close()
    return rows


def delete_teacher(login):
    conn = get_connection()
    conn.execute("DELETE FROM teachers WHERE login = ?", (login.strip(),))
    conn.commit()
    conn.close()


def save_student(name, class_name, parent_code_input, photo_path, embedding, parent_name="", parent_code=""):
    parent_code = (parent_code or parent_code_input or "").strip()
    parent_name = (parent_name or "").strip()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO students
            (name, class_name, parent_name, parent_code, role, photo_path, embedding)
        VALUES (?, ?, ?, ?, 'student', ?, ?)
    """, (
        name,
        class_name,
        parent_name,
        parent_code,
        photo_path,
        embedding.astype(np.float32).tobytes(),
    ))
    if parent_code:
        cur.execute("""
            INSERT OR REPLACE INTO parents (code, name, role)
            VALUES (?, ?, 'parent')
        """, (parent_code, parent_name))
    conn.commit()
    conn.close()


# === КӨП-РАКУРСТУК ТААНУУ ҮЧҮН ЖАҢЫ ФУНКЦИЯЛАР ===

def add_face_embedding(name, embedding, angle_label="front"):
    """
    Бир окуучуга кошумча ракурс (сол, оң, жогору, ылдый ж.б.) эмбеддингин кошот.
    students таблицасындагы негизги embedding'ди өчүрбөйт/өзгөртпөйт —
    face_embeddings таблицасына кошумчалап гана коет ("галерея" катары).
    """
    embedding = np.asarray(embedding, dtype=np.float32)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO face_embeddings (name, angle_label, embedding) VALUES (?, ?, ?)",
        (name, angle_label, embedding.tobytes()),
    )
    conn.commit()
    conn.close()


def load_all_face_embeddings():
    """
    Таанууда колдонуу үчүн: face_embeddings таблицасындагы БАРДЫК ракурстарды,
    ар бирине тиешелүү class_name/parent_code менен кошо кайтарат.
    Бир окуучунун бир нече катары болушу мүмкүн — бул нормалдуу.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.name, s.parent_code, s.class_name, f.embedding
        FROM face_embeddings f
        JOIN students s ON s.name = f.name
    """)
    rows = cur.fetchall()
    conn.close()

    names, parent_codes, embeddings, classes = [], [], [], []
    for name, parent_code, class_name, embedding_blob in rows:
        names.append(name)
        parent_codes.append(parent_code or "")
        classes.append(class_name or "")
        embeddings.append(np.frombuffer(embedding_blob, dtype=np.float32))
    return names, parent_codes, embeddings, classes


def delete_face_embeddings(name):
    """Окуучу өчүрүлгөндө/кайра импорттолгондо анын бардык ракурстарын тазалайт."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM face_embeddings WHERE name = ?", (name,))
    conn.commit()
    conn.close()


def count_face_embeddings(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM face_embeddings WHERE name = ?", (name,))
    count = cur.fetchone()[0]
    conn.close()
    return count


def load_all_students():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, parent_code, embedding, class_name FROM students ORDER BY class_name, name")
    rows = cursor.fetchall()
    conn.close()

    names, parent_codes, embeddings, classes = [], [], [], []
    for name, parent_code, embedding, class_name in rows:
        names.append(name)
        parent_codes.append(parent_code or "")
        embeddings.append(np.frombuffer(embedding, dtype=np.float32) if embedding else np.zeros(512, dtype=np.float32))
        classes.append(class_name or "")
    return names, parent_codes, embeddings, classes


def get_all_students_list():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, class_name, photo_path, parent_name, parent_code
        FROM students
        ORDER BY class_name, name
    """)
    data = cur.fetchall()
    conn.close()
    return data


def get_student_by_name(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, class_name, photo_path, parent_name, parent_code, embedding
        FROM students
        WHERE name = ?
    """, (name,))
    data = cur.fetchone()
    conn.close()
    return data


def update_student(old_name, name, class_name, parent_name, parent_code, photo_path=None, embedding=None):
    conn = get_connection()
    cur = conn.cursor()

    if old_name != name:
        cur.execute("SELECT 1 FROM students WHERE name = ?", (name,))
        if cur.fetchone() is not None:
            conn.close()
            return False

    fields = [
        "name = ?",
        "class_name = ?",
        "parent_name = ?",
        "parent_code = ?",
    ]
    values = [name, class_name, parent_name, parent_code]

    if photo_path is not None and embedding is not None:
        fields.extend(["photo_path = ?", "embedding = ?"])
        values.extend([photo_path, embedding.astype(np.float32).tobytes()])

    values.append(old_name)
    cur.execute(f"""
        UPDATE students
        SET {", ".join(fields)}
        WHERE name = ?
    """, values)
    changed = cur.rowcount > 0

    cur.execute("""
        UPDATE attendance
        SET name = ?, class_name = ?
        WHERE name = ?
    """, (name, class_name, old_name))

    # Аты өзгөргөндө face_embeddings таблицасындагы катарлар да жаңы атка ээ болсун
    if old_name != name:
        cur.execute("""
            UPDATE face_embeddings
            SET name = ?
            WHERE name = ?
        """, (name, old_name))

    if parent_code:
        cur.execute("""
            INSERT OR REPLACE INTO parents (code, name, role)
            VALUES (?, ?, 'parent')
        """, (parent_code, parent_name))

    conn.commit()
    conn.close()
    return changed


def get_students_by_class(class_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, parent_code
        FROM students
        WHERE class_name = ?
        ORDER BY name
    """, (class_name.strip(),))
    data = cur.fetchall()
    conn.close()
    return data


def delete_student_by_name(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE name = ?", (name,))
    cur.execute("DELETE FROM attendance WHERE name = ?", (name,))
    cur.execute("DELETE FROM face_embeddings WHERE name = ?", (name,))  # <-- ракурстарды да тазалайт
    conn.commit()
    conn.close()


def clear_attendance(class_name=None):
    conn = get_connection()
    cur = conn.cursor()
    if isinstance(class_name, (list, tuple, set)):
        classes = [str(value).strip() for value in class_name if str(value).strip()]
        placeholders = ",".join("?" for _ in classes)
        if classes:
            cur.execute(f"DELETE FROM attendance WHERE class_name IN ({placeholders})", classes)
    elif class_name:
        cur.execute("DELETE FROM attendance WHERE class_name = ?", (class_name.strip(),))
    else:
        cur.execute("DELETE FROM attendance")
        cur.execute("DELETE FROM sqlite_sequence WHERE name = 'attendance'")
    conn.commit()
    conn.close()


def has_attendance_today(name, status):
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        SELECT id
        FROM attendance
        WHERE name = ? AND status = ? AND date(timestamp) = ?
        LIMIT 1
    """, (name, status, today))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def is_status_change(row, last_status_by_name_and_day, name_index, status_index, timestamp_index):
    name = row[name_index]
    status = row[status_index]
    day = str(row[timestamp_index] or "")[:10]
    key = (name, day)
    if last_status_by_name_and_day.get(key) == status:
        return False
    last_status_by_name_and_day[key] = status
    return True


def log_attendance(name, class_name, status="keldi"):
    if status not in {"keldi", "ketti"}:
        return False

    with attendance_lock:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            today = datetime.now().strftime("%Y-%m-%d")
            cur.execute("""
                SELECT status
                FROM attendance
                WHERE name = ? AND date(timestamp) = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
            """, (name, today))
            row = cur.fetchone()
            last_status = row[0] if row else None

            if last_status == status or (last_status is None and status == "ketti"):
                conn.rollback()
                return False

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO attendance (name, class_name, status, timestamp)
                VALUES (?, ?, ?, ?)
            """, (name, class_name, status, timestamp))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_class_attendance(class_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, status, strftime('%H:%M', timestamp), timestamp
        FROM attendance
        WHERE class_name = ?
        ORDER BY timestamp ASC, id ASC
    """, (class_name.strip(),))
    rows = cur.fetchall()
    conn.close()
    last_status = {}
    data = [row[:3] for row in rows if is_status_change(row, last_status, 0, 1, 3)]
    return list(reversed(data))


def get_recent_attendance(limit=50):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.name, a.class_name, a.status, a.timestamp, s.parent_name, s.parent_code
        FROM attendance a
        LEFT JOIN students s ON s.name = a.name
        ORDER BY a.timestamp ASC, a.id ASC
    """)
    rows = cur.fetchall()
    conn.close()
    last_status = {}
    data = [row for row in rows if is_status_change(row, last_status, 0, 2, 3)]
    return list(reversed(data))[:limit]


def get_class_report(class_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.name, a.class_name, a.status, a.timestamp, s.parent_name, s.parent_code
        FROM attendance a
        LEFT JOIN students s ON s.name = a.name
        WHERE a.class_name = ?
        ORDER BY a.timestamp ASC, a.id ASC
    """, (class_name.strip(),))
    rows = cur.fetchall()
    conn.close()
    last_status = {}
    data = [row for row in rows if is_status_change(row, last_status, 0, 2, 3)]
    return list(reversed(data))


def get_class_daily_report(class_name):
    """Return one attendance summary per student and day for a teacher report."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        WITH report_days AS (
            SELECT s.name, s.class_name, s.parent_name, s.parent_code,
                   date('now', 'localtime') AS report_date
            FROM students s
            WHERE s.class_name = ?

            UNION

            SELECT s.name, s.class_name, s.parent_name, s.parent_code,
                   date(a.timestamp) AS report_date
            FROM students s
            JOIN attendance a ON a.name = s.name
            WHERE s.class_name = ?
        )
        SELECT d.name,
               d.class_name,
               d.report_date,
               MIN(CASE WHEN a.status = 'keldi' THEN time(a.timestamp) END) AS arrived_at,
               MAX(CASE WHEN a.status = 'ketti' THEN time(a.timestamp) END) AS left_at,
               d.parent_name,
               d.parent_code
        FROM report_days d
        LEFT JOIN attendance a
               ON a.name = d.name
              AND date(a.timestamp) = d.report_date
        GROUP BY d.name, d.class_name, d.report_date, d.parent_name, d.parent_code
        ORDER BY d.report_date DESC, d.name
    """, (class_name.strip(), class_name.strip()))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_parent_report(parent_code, parent_name=""):
    conn = get_connection()
    cur = conn.cursor()
    parent_code = (parent_code or "").strip()
    parent_name = (parent_name or "").strip()

    if not parent_code or not parent_name:
        conn.close()
        return []

    cur.execute("""
        SELECT s.name, s.class_name, a.status, a.timestamp
        FROM students s
        LEFT JOIN attendance a ON a.name = s.name
        WHERE s.parent_code = ? AND lower(trim(s.parent_name)) = lower(trim(?))
        ORDER BY s.name, a.timestamp ASC, a.id ASC
    """, (parent_code, parent_name))
    rows = cur.fetchall()
    conn.close()
    last_status = {}
    data = [
        row for row in rows
        if row[2] is None or is_status_change(row, last_status, 0, 2, 3)
    ]
    return sorted(data, key=lambda row: (row[0], row[3] or ""), reverse=True)


def get_classes_summary():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.class_name,
               COUNT(*) AS students_count,
               COUNT(DISTINCT CASE WHEN a.status = 'keldi' AND date(a.timestamp) = date('now', 'localtime') THEN s.name END),
               COUNT(DISTINCT CASE WHEN a.status = 'ketti' AND date(a.timestamp) = date('now', 'localtime') THEN s.name END)
        FROM students s
        LEFT JOIN attendance a ON a.name = s.name
        GROUP BY s.class_name
        ORDER BY s.class_name
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_parents_summary(class_names=None):
    conn = get_connection()
    cur = conn.cursor()
    classes = [str(value).strip() for value in (class_names or []) if str(value).strip()]
    where = ""
    params = []
    if classes:
        where = f"WHERE s.class_name IN ({','.join('?' for _ in classes)})"
        params = classes
    cur.execute(f"""
        SELECT s.parent_name, s.parent_code,
               COUNT(*) AS children_count,
               GROUP_CONCAT(s.name || ' (' || s.class_name || ')', ', ')
        FROM students s
        {where}
        GROUP BY s.parent_name, s.parent_code
        ORDER BY s.parent_name, s.parent_code
    """, params)
    rows = cur.fetchall()
    conn.close()
    return rows
