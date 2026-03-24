import sqlite3
import random
from datetime import datetime, timedelta, time
from faker import Faker

# ================= KONFIGURACJA =================
DB_NAME = 'medical.db'
NUM_NEW_PATIENTS = 30       # Dodam jeszcze trochę nowych pacjentów
NUM_RANDOM_APPOINTMENTS = 100 # Losowe wizyty rozrzucone po całym roku

# Inicjalizacja Fakera
fake = Faker('pl_PL')

# ================= LISTA REALISTYCZNYCH OBJAWÓW =================
REALISTIC_SYMPTOMS = [
    "Silny ból głowy, światłowstręt, nudności (podejrzenie migreny).",
    "Wysoka gorączka 39st, dreszcze, ból mięśni i suchy kaszel.",
    "Ból w klatce piersiowej promieniujący do lewego ramienia.",
    "Czerwona, swędząca wysypka na przedramionach i plecach.",
    "Przewlekły ból odcinka lędźwiowego kręgosłupa, drętwienie nogi.",
    "Ostry ból brzucha w okolicy podżebrowej, zgaga.",
    "Uporczywy ból gardła, trudności z przełykaniem.",
    "Kołatanie serca, uczucie niepokoju, wysokie ciśnienie.",
    "Opuchlizna stawu skokowego po upadku, krwiak.",
    "Zmiany skórne na twarzy, trądzik różowaty.",
    "Ból ucha, niedosłuch, szumy uszne.",
    "Częste oddawanie moczu, pieczenie, ból w podbrzuszu.",
    "Zawroty głowy przy wstawaniu, osłabienie.",
    "Duszności, świszczący oddech (zaostrzenie astmy).",
    "Ból kolana przy zginaniu, problem z wyprostem.",
    "Bezsenność, przewlekłe zmęczenie, brak apetytu.",
    "Krwawienie z nosa, bóle głowy.",
    "Nagła utrata widzenia w jednym oku, mroczki.",
    "Pieprzyk o nieregularnym kształcie, zmiana koloru.",
    "Ból zęba promieniujący do ucha."
]

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def generate_time_slots():
    """Generuje sloty czasowe 08:00 - 18:00 co 30 min"""
    slots = []
    start = datetime.combine(datetime.today(), time(8, 0))
    end = datetime.combine(datetime.today(), time(18, 0))
    while start < end:
        slots.append(start.strftime("%H:%M"))
        start += timedelta(minutes=30)
    return slots

def seed_doctors(conn):
    """Dodaje lekarzy TYLKO jeśli baza jest pusta"""
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM doctors")
    count = cur.fetchone()[0]
    
    if count == 0:
        print("[i] Brak lekarzy w bazie. Dodaję domyślnych...")
        doctors = [
            ("dr Jan Kowalski", "Kardiolog", "101", "jan@med.pl", "lekarz123"),
            ("dr Anna Nowak", "Pediatra", "102", "anna@med.pl", "lekarz123"),
            ("dr Tomasz Wiśniewski", "Dermatolog", "103", "tomasz@med.pl", "lekarz123"),
            ("dr Maria Lewandowska", "Okulista", "204", "maria@med.pl", "lekarz123"),
            ("dr Piotr Zieliński", "Ortopeda", "205", "piotr@med.pl", "lekarz123")
        ]
        cur.executemany(
            'INSERT INTO doctors (name, specialization, room_number, email, password) VALUES (?, ?, ?, ?, ?)',
            doctors
        )
        conn.commit()
        print(f"[+] Dodano {len(doctors)} nowych lekarzy.")
    else:
        print(f"[ok] Znaleziono {count} lekarzy. Pomijam.")

def seed_patients(conn):
    """Dopisuje nowych pacjentów"""
    cur = conn.cursor()
    patients_data = []
    default_password = "haslo123" 

    print(f"[i] Generuję {NUM_NEW_PATIENTS} nowych pacjentów...")

    for _ in range(NUM_NEW_PATIENTS):
        first_name = fake.first_name()
        last_name = fake.last_name()
        
        def clean(s):
            return s.lower().replace('ą','a').replace('ć','c').replace('ę','e').replace('ł','l').replace('ń','n').replace('ó','o').replace('ś','s').replace('ź','z').replace('ż','z')
        
        email = f"{clean(first_name)}.{clean(last_name)}.{random.randint(100,999)}@{fake.free_email_domain()}"
        pesel = fake.pesel()
        phone = fake.phone_number().replace(" ", "")
        if len(phone) > 9: phone = phone[-9:]

        patients_data.append((first_name, last_name, pesel, email, phone, default_password))

    added_count = 0
    for p in patients_data:
        try:
            cur.execute(
                'INSERT INTO patients (first_name, last_name, pesel, email, phone, password) VALUES (?, ?, ?, ?, ?, ?)',
                p
            )
            added_count += 1
        except sqlite3.IntegrityError:
            continue
            
    conn.commit()
    print(f"[+] Pomyślnie dopisano {added_count} pacjentów.")

def get_taken_slots(cur):
    """Pomocnicza funkcja pobierająca zajęte terminy"""
    existing_rows = cur.execute("SELECT doctor_id, appointment_time FROM appointments").fetchall()
    taken_slots = set()
    for row in existing_rows:
        taken_slots.add((row['doctor_id'], row['appointment_time']))
    return taken_slots

def seed_random_appointments(conn):
    """Dopisuje losowe wizyty w skali roku (dla wykresu rocznego)"""
    cur = conn.cursor()
    doctors = cur.execute("SELECT id FROM doctors").fetchall()
    patients = cur.execute("SELECT id FROM patients").fetchall()
    
    if not doctors or not patients: return

    doc_ids = [d['id'] for d in doctors]
    pat_ids = [p['id'] for p in patients]
    
    taken_slots = get_taken_slots(cur)
    slots = generate_time_slots()
    
    # Zakres: rok wstecz - miesiąc w przód
    start_date = datetime.now() - timedelta(days=365)
    end_date = datetime.now() + timedelta(days=30)
    days_range = (end_date - start_date).days

    appointments_batch = []
    attempts = 0
    
    while len(appointments_batch) < NUM_RANDOM_APPOINTMENTS:
        attempts += 1
        if attempts > NUM_RANDOM_APPOINTMENTS * 20: break

        random_days = random.randrange(days_range)
        appt_date = (start_date + timedelta(days=random_days)).date()
        full_time_str = f"{appt_date.strftime('%Y-%m-%d')} {random.choice(slots)}"
        
        doctor_id = random.choice(doc_ids)
        
        if (doctor_id, full_time_str) in taken_slots: continue
        taken_slots.add((doctor_id, full_time_str))
        
        # Status
        appt_datetime = datetime.strptime(full_time_str, "%Y-%m-%d %H:%M")
        if appt_datetime < datetime.now():
            status = random.choices(['done', 'no_show', 'scheduled'], weights=[75, 15, 10], k=1)[0]
        else:
            status = 'scheduled'

        appointments_batch.append((
            doctor_id, random.choice(pat_ids), full_time_str, random.choice(REALISTIC_SYMPTOMS), 1, 0, status
        ))

    cur.executemany(
        '''INSERT INTO appointments 
           (doctor_id, patient_id, appointment_time, symptoms, remind_email, remind_sms, status) 
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        appointments_batch
    )
    conn.commit()
    print(f"[+] Dodano {len(appointments_batch)} losowych wizyt z całego roku.")

def seed_recent_activity(conn):
    """
    SPECJALNA FUNKCJA: Generuje gęste dane dla ostatnich 7 dni,
    aby wykres dzienny wyglądał ładnie dla każdego lekarza.
    """
    print("[i] Uruchamiam 'Booster' ostatnich 7 dni...")
    cur = conn.cursor()
    doctors = cur.execute("SELECT id FROM doctors").fetchall()
    patients = cur.execute("SELECT id FROM patients").fetchall()
    
    if not doctors or not patients: return

    pat_ids = [p['id'] for p in patients]
    taken_slots = get_taken_slots(cur)
    slots = generate_time_slots()
    
    appointments_batch = []
    
    # Generuj dla KAŻDEGO lekarza
    for doc in doctors:
        doc_id = doc['id']
        
        # Dla każdego z ostatnich 7 dni
        for i in range(7):
            day_date = datetime.now() - timedelta(days=i)
            day_str = day_date.strftime("%Y-%m-%d")
            
            # Losuj ile wizyt tego dnia (np. od 3 do 6)
            num_visits_today = random.randint(3, 6)
            
            # Próbuj wylosować wolne godziny
            # Mieszamy sloty, żeby brać losowe godziny
            daily_slots = list(slots)
            random.shuffle(daily_slots)
            
            added_today = 0
            for slot in daily_slots:
                if added_today >= num_visits_today:
                    break
                
                full_time_str = f"{day_str} {slot}"
                
                if (doc_id, full_time_str) not in taken_slots:
                    # Mamy wolny termin!
                    taken_slots.add((doc_id, full_time_str))
                    
                    # Status: głównie 'done', czasem 'no_show'
                    status = random.choices(['done', 'no_show'], weights=[85, 15], k=1)[0]
                    
                    appointments_batch.append((
                        doc_id, 
                        random.choice(pat_ids), 
                        full_time_str, 
                        random.choice(REALISTIC_SYMPTOMS), 
                        1, 0, 
                        status
                    ))
                    added_today += 1

    cur.executemany(
        '''INSERT INTO appointments 
           (doctor_id, patient_id, appointment_time, symptoms, remind_email, remind_sms, status) 
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        appointments_batch
    )
    conn.commit()
    print(f"[+] 'Booster': Dodano {len(appointments_batch)} wizyt w ostatnich 7 dniach (dla wszystkich lekarzy).")

if __name__ == '__main__':
    print("--- Start aktualizacji bazy ---")
    conn = get_db_connection()
    
    try:
        seed_doctors(conn)
        seed_patients(conn)
        
        # 1. Trochę historii ogólnej
        seed_random_appointments(conn)
        
        # 2. Gęste dane z tego tygodnia (dla wykresu)
        seed_recent_activity(conn)
        
    except Exception as e:
        print(f"Błąd: {e}")

    conn.close()
    print("--- Gotowe! Wykresy powinny być teraz pełne. ---")