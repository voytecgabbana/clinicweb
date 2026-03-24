import sqlite3
import os

def init_db():
    if os.path.exists('medical.db'):
        os.remove('medical.db') # Zacznij od nowa, aby łatwo stosować zmiany schematu

    conn = sqlite3.connect('medical.db')
    cursor = conn.cursor()

    # tabela lekarzy
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialization TEXT NOT NULL,
        room_number TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        pesel TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    ''')
    # tabela wizyt
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER NOT NULL,
        patient_id INTEGER NOT NULL,
        appointment_time TEXT NOT NULL,
        symptoms TEXT,
        remind_email BOOLEAN DEFAULT 0,
        remind_sms BOOLEAN DEFAULT 0,
        FOREIGN KEY (doctor_id) REFERENCES doctors (id),
        FOREIGN KEY (patient_id) REFERENCES patients (id)
    )
    ''')

    # dopisanie lekarzy
    doctors = [
        ('Dr. Jan Kowalski', 'Kardiolog', '101', 'jan.kowalski@clinic.pl', 'haslo1'),
        ('Dr. Anna Nowak', 'Pediatra', '102','anna.nowak@clinic.pl', 'haslo2'),
        ('Dr. Piotr Wiśniewski', 'Dermatolog', '205', 'piotr.wisniewski@clinic.pl', 'haslo3'),
        ('Dr. Maria Zielińska', 'Okulista', '206','maria.zielinska@clinic.pl', 'haslo4'),
    ]
    cursor.executemany('INSERT INTO doctors (name, specialization, room_number, email, password) VALUES (?, ?, ?, ?, ?)', doctors)
    print("Doctors seeded with room numbers.")

    conn.commit()
    conn.close()
    print("Database initialized.")

if __name__ == '__main__':
    init_db()
