import sqlite3
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "memory", "jobs.db")

def init_db():
    """Initialize the applications table in jobs.db SQLite database."""
    # Ensure memory directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            role TEXT,
            country TEXT,
            date TEXT,
            status TEXT,
            url TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_application(company: str, role: str, country: str, date: str, status: str, url: str) -> None:
    """Save an application entry to the SQLite database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO applications (company, role, country, date, status, url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (company, role, country, date, status, url))
    conn.commit()
    conn.close()

def is_already_applied(company: str, role: str) -> bool:
    """Check if the user has already applied to this role at this company."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM applications 
        WHERE LOWER(company) = ? AND LOWER(role) = ?
    """, (company.lower(), role.lower()))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

