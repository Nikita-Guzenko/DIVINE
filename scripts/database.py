"""
SQLite Database for Divine Recruiting
Fast, reliable candidate storage with deduplication
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "candidates.db")


def get_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Basic info
            first_name TEXT,
            last_name TEXT,
            email TEXT UNIQUE,
            phone TEXT,

            -- Application info
            position TEXT,
            location TEXT,
            source TEXT DEFAULT 'CareerPlug/ZipRecruiter',
            careerplug_url TEXT,

            -- Call tracking
            date_called TEXT,
            call_status TEXT DEFAULT 'New',
            comment TEXT,

            -- Driver info (filled during call)
            experience_years TEXT,
            open_to_team TEXT,
            reason_switching TEXT,
            days_on_road TEXT,
            home_time TEXT,
            temp_controlled_exp TEXT,
            endorsement_doubles TEXT,
            endorsement_tanker TEXT,
            endorsement_hazmat TEXT,
            employment_type TEXT,

            -- Status tracking
            email_sent_at TIMESTAMP,
            intelliapp_completed INTEGER DEFAULT 0,
            hired INTEGER DEFAULT 0,

            -- Pre-screening
            screening_sent_at TIMESTAMP,
            screening_response TEXT,

            -- Sync tracking
            synced_to_sheet INTEGER DEFAULT 0
        )
    """)

    # Add new columns if they don't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE candidates ADD COLUMN screening_sent_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE candidates ADD COLUMN screening_response TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Index for fast lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_email ON candidates(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_phone ON candidates(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON candidates(call_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_synced ON candidates(synced_to_sheet)")

    conn.commit()
    conn.close()
    print(f"✓ Database initialized: {DB_PATH}")


def normalize_phone(phone: str) -> str:
    """Normalize phone number for comparison"""
    if not phone:
        return ""
    return phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "").replace("+1", "")


def candidate_exists(email: str = None, phone: str = None) -> bool:
    """Check if candidate already exists by email or phone"""
    conn = get_connection()
    cursor = conn.cursor()

    if email:
        cursor.execute("SELECT id FROM candidates WHERE email = ?", (email.lower(),))
        if cursor.fetchone():
            conn.close()
            return True

    if phone:
        # Check normalized phone
        cursor.execute("SELECT phone FROM candidates")
        for row in cursor.fetchall():
            if normalize_phone(row[0]) == normalize_phone(phone):
                conn.close()
                return True

    conn.close()
    return False


def add_candidate(candidate: Dict) -> Optional[int]:
    """
    Add new candidate to database
    Returns candidate ID or None if duplicate
    """
    email = candidate.get('email', '').lower()
    phone = candidate.get('phone', '')

    # Check for duplicates
    if candidate_exists(email=email, phone=phone):
        return None

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO candidates (
            first_name, last_name, email, phone,
            position, location, source, careerplug_url,
            call_status, comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        candidate.get('first_name', ''),
        candidate.get('last_name', ''),
        email,
        phone,
        candidate.get('position', ''),
        candidate.get('location', ''),
        candidate.get('source', 'CareerPlug/ZipRecruiter'),
        candidate.get('careerplug_url', ''),
        'New',
        candidate.get('comment', '')
    ))

    candidate_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return candidate_id


def get_candidate(candidate_id: int) -> Optional[Dict]:
    """Get candidate by ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_candidates(status: str = None, synced: bool = None, limit: int = None) -> List[Dict]:
    """Get candidates with optional filters"""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM candidates WHERE 1=1"
    params = []

    if status:
        query += " AND call_status = ?"
        params.append(status)

    if synced is not None:
        query += " AND synced_to_sheet = ?"
        params.append(1 if synced else 0)

    query += " ORDER BY created_at DESC"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_unsynced_candidates() -> List[Dict]:
    """Get candidates not yet synced to Google Sheet"""
    return get_candidates(synced=False)


def mark_synced(candidate_ids: List[int]):
    """Mark candidates as synced to Google Sheet"""
    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ','.join('?' * len(candidate_ids))
    cursor.execute(f"UPDATE candidates SET synced_to_sheet = 1 WHERE id IN ({placeholders})", candidate_ids)

    conn.commit()
    conn.close()


def update_candidate(candidate_id: int, updates: Dict):
    """Update candidate fields"""
    conn = get_connection()
    cursor = conn.cursor()

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [candidate_id]

    cursor.execute(f"UPDATE candidates SET {set_clause} WHERE id = ?", values)

    conn.commit()
    conn.close()


def update_call_status(candidate_id: int, status: str, comment: str = None):
    """Update call status and optionally add comment"""
    updates = {
        'call_status': status,
        'date_called': datetime.now().strftime("%m/%d")
    }
    if comment:
        updates['comment'] = comment

    update_candidate(candidate_id, updates)


def mark_email_sent(candidate_id: int):
    """Mark that email was sent to candidate"""
    update_candidate(candidate_id, {'email_sent_at': datetime.now().isoformat()})


def mark_screening_sent(candidate_id: int):
    """Mark that pre-screening email was sent"""
    update_candidate(candidate_id, {
        'screening_sent_at': datetime.now().isoformat(),
        'call_status': 'Screening'
    })


def update_screening_response(candidate_id: int, response: str, status: str):
    """Update candidate with screening response and new status"""
    update_candidate(candidate_id, {
        'screening_response': response,
        'call_status': status
    })


def get_candidates_for_screening() -> List[Dict]:
    """Get candidates ready to receive pre-screening email (status: New)"""
    return get_candidates(status='New')


def get_candidates_awaiting_response() -> List[Dict]:
    """Get candidates waiting for screening response"""
    return get_candidates(status='Screening')


def get_stats() -> Dict:
    """Get database statistics"""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) FROM candidates")
    stats['total'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE call_status = 'New'")
    stats['new'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE call_status = 'Screening'")
    stats['screening'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE call_status = 'Team OK'")
    stats['team_ok'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE call_status = 'Solo Only'")
    stats['solo_only'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE call_status = 'Done'")
    stats['called'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE email_sent_at IS NOT NULL")
    stats['emailed'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates WHERE synced_to_sheet = 0")
    stats['unsynced'] = cursor.fetchone()[0]

    conn.close()
    return stats


def search_candidates(query: str) -> List[Dict]:
    """Search candidates by name, email, or phone"""
    conn = get_connection()
    cursor = conn.cursor()

    search = f"%{query}%"
    cursor.execute("""
        SELECT * FROM candidates
        WHERE first_name LIKE ?
           OR last_name LIKE ?
           OR email LIKE ?
           OR phone LIKE ?
        ORDER BY created_at DESC
    """, (search, search, search, search))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# Initialize database on import
init_db()


if __name__ == "__main__":
    # Test
    print("\nDatabase stats:")
    stats = get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
