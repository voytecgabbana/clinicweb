import sqlite3

DB_NAME = "medical.db"

def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())

def main():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    # 1) DODAJ KOLUMNY (jeśli nie istnieją)
    if not column_exists(cur, "appointments", "status"):
        cur.execute("ALTER TABLE appointments ADD COLUMN status TEXT;")
        print("Added appointments.status")

    if not column_exists(cur, "appointments", "created_at"):
        cur.execute("ALTER TABLE appointments ADD COLUMN created_at TEXT;")
        print("Added appointments.created_at")

    if not column_exists(cur, "appointments", "cancel_reason"):
        cur.execute("ALTER TABLE appointments ADD COLUMN cancel_reason TEXT;")
        print("Added appointments.cancel_reason")

    # 2) UZUPEŁNIJ ISTNIEJĄCE REKORDY
    cur.execute("UPDATE appointments SET status='scheduled' WHERE status IS NULL OR status=''")
    cur.execute("UPDATE appointments SET created_at=datetime('now') WHERE created_at IS NULL OR created_at=''")

    # 3) INDEKSY (szybsze dashboardy)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_appointments_doctor_time
        ON appointments(doctor_id, appointment_time)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_appointments_patient_time
        ON appointments(patient_id, appointment_time)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_appointments_status
        ON appointments(status)
    """)

    
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_appointments_set_created_at
        AFTER INSERT ON appointments
        FOR EACH ROW
        WHEN NEW.created_at IS NULL OR NEW.created_at = ''
        BEGIN
            UPDATE appointments
            SET created_at = datetime('now')
            WHERE id = NEW.id;
        END;
    """)
    
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_appointments_set_status
        AFTER INSERT ON appointments
        FOR EACH ROW
        WHEN NEW.status IS NULL OR NEW.status = ''
        BEGIN
            UPDATE appointments
            SET status = 'scheduled'
            WHERE id = NEW.id;
        END;
    """)

    conn.commit()
    conn.close()
    print("Migration done ✅")

if __name__ == "__main__":
    main()
