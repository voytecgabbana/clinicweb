from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3, json
from datetime import datetime, time, timedelta, date
from flask import send_file
from io import BytesIO
from openpyxl import Workbook


app = Flask(__name__)
app.secret_key = 'supersecretkey'

DB_NAME = 'medical.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
def generate_time_slots():
    slots = []
    start = datetime.combine(datetime.today(), time(8, 0))
    end = datetime.combine(datetime.today(), time(18, 0))
    while start < end:
        slots.append(start.strftime("%H:%M"))
        start += timedelta(minutes=30)
    return slots

@app.route("/")
def index():
    role = session.get("role")

    if role == "doctor":
        return redirect(url_for("doctor_start"))

    if role == "patient":
        return redirect(url_for("patient_start"))

    return render_template("index.html")


@app.route('/create-account', methods=('GET', 'POST'))
def create_account():
    if request.method == 'POST':
        first_name = request.form['first_name'].strip()
        last_name = request.form['last_name'].strip()
        pesel = request.form['pesel'].strip()
        email = request.form['email'].strip().lower()
        phone = request.form['phone'].strip()
        password = request.form['password']  # na razie zwykły tekst (hash jest póżniej zrobiony)

        conn = get_db_connection()

        # 1) sprawdzamy, czy konto już istnieje (PESEL lub email)
        existing = conn.execute(
            'SELECT id FROM patients WHERE pesel = ? OR email = ?',
            (pesel, email)
        ).fetchone()

        if existing:
            conn.close()
            flash('Konto z tym PESEL lub e-mailem już istnieje.', 'error')
            return redirect(url_for('create_account'))

        # 2) zapis do bazy
        conn.execute(
            'INSERT INTO patients (first_name, last_name, pesel, email, phone, password) VALUES (?, ?, ?, ?, ?, ?)',
            (first_name, last_name, pesel, email, phone, password)
        )
        conn.commit()
        conn.close()

        flash('Konto zostało utworzone. Możesz się teraz zalogować.',
              'success')
        return redirect(url_for('index'))

    return render_template('create_account.html')

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        identifier = request.form['identifier'].strip().lower()  # email lub PESEL
        password = request.form['password']

        conn = get_db_connection()

        if identifier.isdigit() and len(identifier) == 11:
            patient = conn.execute(
                'SELECT id, first_name, last_name, email, pesel, password FROM patients WHERE pesel = ?',
                (identifier,)
            ).fetchone()
        else:
            patient = conn.execute(
                'SELECT id, first_name, last_name, email, pesel, password FROM patients WHERE email = ?',
                (identifier,)
            ).fetchone()

        conn.close()

        if not patient or patient['password'] != password:
            flash('Nieprawidłowy email/PESEL lub hasło.', 'error')
            return redirect(url_for('login'))

        # zapisujemy info o zalogowanym pacjencie w sesji
        session.clear()
        session['role'] = 'patient'
        session['patient_id'] = patient['id']
        session['patient_name'] = f"{patient['first_name']} {patient['last_name']}"
        flash('Zalogowano pomyślnie', 'success')
        return redirect(url_for('patient_start'))

    return render_template('login.html')

@app.route('/logout', methods=('POST',))
def logout():
    session.clear()
    flash('Wylogowano.', 'success')
    return redirect(url_for('index'))

@app.route('/register', methods=('GET', 'POST'))
def register():
    if session.get("role") != "patient":
        return redirect(url_for("index"))

    if not session.get('patient_id'):
        flash('Musisz się zalogować, aby umówić wizytę.', 'error')
        return redirect(url_for('login'))

    conn = get_db_connection()

    # ---------- POST: zapis wizyty ----------
    if request.method == 'POST':
        doctor_id = int(request.form['doctor'])
        appointment_date = request.form['appointment_date']      # YYYY-MM-DD
        appointment_clock = request.form['appointment_time']     # HH:MM
        symptoms = request.form['symptoms']
        remind_email = 1 if request.form.get('remind_email') else 0
        remind_sms = 1 if request.form.get('remind_sms') else 0
        patient_id = session['patient_id']

        # składamy jeden string do bazy
        appointment_time = f"{appointment_date} {appointment_clock}"

        # pobranie kontaktu pacjenta
        patient = conn.execute(
            "SELECT email, phone FROM patients WHERE id = ?",
            (patient_id,)
        ).fetchone()
        patient_email = patient['email'] if patient else None
        patient_sms = patient['phone'] if patient else None

        # walidacja: godzina musi być jednym z dozwolonych slotów
        allowed = set(generate_time_slots())
        if appointment_clock not in allowed:
            conn.close()
            flash("Nieprawidłowa godzina wizyty. Wybierz godzinę z listy.", "error")
            return redirect(url_for('register'))

        # sprawdzenie dostępności
        existing_appointment = conn.execute(
            'SELECT 1 FROM appointments WHERE doctor_id = ? AND appointment_time = ?',
            (doctor_id, appointment_time)
        ).fetchone()

        if existing_appointment:
            conn.close()
            flash('Ten termin jest już zajęty dla wybranego lekarza. Proszę wybrać inny.', 'error')
            return redirect(url_for('register'))

        # zapis wizyty
        conn.execute(
            '''INSERT INTO appointments 
               (doctor_id, patient_id, appointment_time, symptoms, remind_email, remind_sms) 
               VALUES (?, ?, ?, ?, ?, ?)''',
            (doctor_id, patient_id, appointment_time, symptoms, remind_email, remind_sms)
        )
        conn.commit()
        conn.close()

        # jeden komunikat
        selected = []
        if remind_email and patient_email:
            selected.append(f"e-mail: {patient_email}")
        if remind_sms and patient_sms:
            selected.append(f"SMS: {patient_sms}")

        if selected:
            flash("Rejestracja pomyślna. Przypomnienie zostanie wysłane na: " + ", ".join(selected), "success")
        else:
            flash("Rejestracja pomyślna.", "success")

        return redirect(url_for('success'))

    # ---------- GET: formularz + dostępność ----------
    doctors = conn.execute('SELECT * FROM doctors').fetchall()

    selected_doctor_id = request.args.get('doctor', type=int)
    selected_date = request.args.get('appointment_date')  # YYYY-MM-DD

    time_slots = generate_time_slots()

    # jeśli wybrano lekarza i datę -> odfiltruj zajęte sloty
    if selected_doctor_id and selected_date:
        taken = conn.execute(
            '''
            SELECT appointment_time
            FROM appointments
            WHERE doctor_id = ?
              AND appointment_time LIKE ?
            ''',
            (selected_doctor_id, f"{selected_date} %")
        ).fetchall()

        taken_times = {row['appointment_time'].split(' ')[1] for row in taken}
        time_slots = [t for t in time_slots if t not in taken_times]

    conn.close()

    return render_template(
        'register.html',
        doctors=doctors,
        time_slots=time_slots,
        selected_doctor_id=selected_doctor_id,
        selected_date=selected_date
    )

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/schedule')
def schedule():
    if session.get("role") != "doctor":
        return redirect(url_for("index"))
    conn = get_db_connection()
    # połączenie wszystkich wizyt z nazwiskami lekarzy w wykazie
    appointments = conn.execute('''
        SELECT a.appointment_time, d.name as doctor_name, d.specialization, p.first_name, p.last_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN patients p ON a.patient_id = p.id
        ORDER BY a.appointment_time ASC
        
    ''').fetchall()

    conn.close()
    return render_template('schedule.html', appointments=appointments)

@app.route('/patients')
def patients():
    conn = get_db_connection()
    appointments = conn.execute('''
        SELECT
            a.id,
            p.first_name || ' ' || p.last_name AS patient_name,
            p.email as patient_email,
            p.phone as patient_phone,
            a.appointment_time,
            a.symptoms,
            a.remind_email,
            a.remind_sms,
            d.name AS doctor_name,
            d.specialization,
            d.room_number
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN patients p ON a.patient_id = p.id
        ORDER BY a.appointment_time ASC
    ''').fetchall()
    conn.close()

    return render_template('patients.html', appointments=appointments)

@app.route("/my-appointments")
def my_appointments():
    # zabezpieczenie – tylko pacjent
    if session.get("role") != "patient":
        return redirect(url_for("index"))

    patient_id = session.get("patient_id")

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT 
            a.id,
            a.appointment_time,
            a.symptoms,
            d.name AS doctor_name,
            d.specialization
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ?
        ORDER BY datetime(a.appointment_time) ASC
    """, (patient_id,)).fetchall()
    conn.close()

    now = datetime.now()

    upcoming_appointments = []
    past_appointments = []

    for a in rows:
        appt_time = datetime.strptime(a["appointment_time"], "%Y-%m-%d %H:%M")

        if appt_time >= now:
            upcoming_appointments.append(a)
        else:
            past_appointments.append(a)

    # przeszłe: od najnowszej do najstarszej
    past_appointments.reverse()

    return render_template(
        "my_appointments.html",
        upcoming_appointments=upcoming_appointments,
        past_appointments=past_appointments
    )

@app.route('/cancel-appointment/<int:appointment_id>', methods=('POST',))
def cancel_appointment(appointment_id):
    # 1) tylko zalogowany
    if session.get("role") != "patient":
        return redirect(url_for("index"))

    if not session.get('patient_id'):
        flash('Musisz się zalogować.', 'error')
        return redirect(url_for('login'))

    patient_id = session['patient_id']
    conn = get_db_connection()

    # 2) sprawdź czy wizyta istnieje i do kogo należy
    appt = conn.execute(
        "SELECT id, patient_id FROM appointments WHERE id = ?",
        (appointment_id,)
    ).fetchone()

    if not appt:
        conn.close()
        flash('Nie znaleziono wizyty.', 'error')
        return redirect(url_for('my_appointments'))

    if appt['patient_id'] != patient_id:
        conn.close()
        flash('Nie możesz anulować cudzej wizyty.', 'error')
        return redirect(url_for('my_appointments'))

    # 3) usuń wizytę
    conn.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
    conn.commit()
    conn.close()

    flash('Wizyta została anulowana.', 'success')
    return redirect(url_for('my_appointments'))

@app.route('/doctor/login', methods=('GET', 'POST'))
def doctor_login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = get_db_connection()
        doctor = conn.execute(
            "SELECT id, name, email, password FROM doctors WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if not doctor or doctor['password'] != password:
            flash('Nieprawidłowy email lub hasło lekarza.', 'error')
            return redirect(url_for('doctor_login'))

        session.clear()
        session['role'] = 'doctor'
        session['doctor_id'] = doctor['id']
        session['doctor_name'] = doctor['name']
        flash('Zalogowano jako lekarz.', 'success')
        return redirect(url_for('doctor_start'))

    return render_template('doctor_login.html')

@app.route('/doctor/logout', methods=('POST',))
def doctor_logout():
    session.clear()
    flash('Wylogowano lekarza.', 'success')
    return redirect(url_for('index'))

@app.route("/doctor/export/patients.xlsx")
def export_patients_xlsx():
    if session.get("role") != "doctor":
        return redirect(url_for("index"))

    conn = get_db_connection()
    patients = conn.execute("""
        SELECT DISTINCT p.id, p.first_name, p.last_name, p.pesel, p.phone, p.email
        FROM patients p
        JOIN appointments a ON a.patient_id = p.id
        WHERE a.doctor_id = ?
        ORDER BY p.last_name, p.first_name
    """, (session["doctor_id"],)).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "patients"

    headers = ["id", "first_name", "last_name", "pesel", "phone", "email"]
    ws.append(headers)

    for p in patients:
        ws.append([p[h] for h in headers])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="patients_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

from datetime import datetime
from flask import request, render_template, redirect, url_for, session

@app.route("/doctor/dashboard")
def doctor_dashboard():
    if session.get("role") != "doctor":
        return redirect(url_for("index"))

    doctor_id = session.get("doctor_id")
    selected_date = request.args.get("date")  # YYYY-MM-DD albo None

    # anchor_date = wybrana data (jeśli filtrujesz) albo dzisiaj
    if selected_date:
        anchor_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        anchor_date = date.today()

    conn = get_db_connection()

    # --------------------------
    # LISTA WIZYT (z filtrem daty lub bez)
    # --------------------------
    if selected_date:
        rows = conn.execute("""
            SELECT 
                a.id,
                a.appointment_time,
                a.symptoms,
                a.status,
                p.first_name,
                p.last_name,
                p.pesel,
                p.phone AS patient_phone,
                p.email AS patient_email
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            WHERE a.doctor_id = ?
              AND a.appointment_time LIKE ?
            ORDER BY datetime(a.appointment_time) ASC
        """, (doctor_id, f"{selected_date} %")).fetchall()
    else:
        rows = conn.execute("""
            SELECT 
                a.id,
                a.appointment_time,
                a.symptoms,
                a.status,
                p.first_name,
                p.last_name,
                p.pesel,
                p.phone AS patient_phone,
                p.email AS patient_email
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            WHERE a.doctor_id = ?
            ORDER BY datetime(a.appointment_time) ASC
        """, (doctor_id,)).fetchall()

    now_dt = datetime.now()
    upcoming_appointments, past_appointments = [], []

    for a in rows:
        # Format w DB: "YYYY-MM-DD HH:MM"
        appt_time = datetime.strptime(a["appointment_time"], "%Y-%m-%d %H:%M")
        if appt_time >= now_dt:
            upcoming_appointments.append(a)
        else:
            past_appointments.append(a)

    past_appointments.reverse()
    next_appointment = upcoming_appointments[0] if upcoming_appointments else None

    # --------------------------
    # STATYSTYKI: dzień / tydzień / miesiąc (dla anchor_date)
    # --------------------------
    day_str = anchor_date.strftime("%Y-%m-%d")
    next_day = anchor_date + timedelta(days=1)

    week_start = anchor_date - timedelta(days=anchor_date.weekday())  # poniedziałek
    week_end = week_start + timedelta(days=7)  # exclusive

    month_start = anchor_date.replace(day=1)
    if month_start.month == 12:
        next_month_start = date(month_start.year + 1, 1, 1)
    else:
        next_month_start = date(month_start.year, month_start.month + 1, 1)

    def stats_for_range(time_min: str, time_max: str):
        total = conn.execute("""
            SELECT COUNT(*) AS c
            FROM appointments
            WHERE doctor_id = ?
              AND datetime(appointment_time) >= datetime(?)
              AND datetime(appointment_time) < datetime(?)
        """, (doctor_id, time_min, time_max)).fetchone()["c"]

        done = conn.execute("""
            SELECT COUNT(*) AS c
            FROM appointments
            WHERE doctor_id = ?
              AND status = 'done'
              AND datetime(appointment_time) >= datetime(?)
              AND datetime(appointment_time) < datetime(?)
        """, (doctor_id, time_min, time_max)).fetchone()["c"]

        no_show = conn.execute("""
            SELECT COUNT(*) AS c
            FROM appointments
            WHERE doctor_id = ?
              AND status = 'no_show'
              AND datetime(appointment_time) >= datetime(?)
              AND datetime(appointment_time) < datetime(?)
        """, (doctor_id, time_min, time_max)).fetchone()["c"]

        scheduled = conn.execute("""
            SELECT COUNT(*) AS c
            FROM appointments
            WHERE doctor_id = ?
              AND status = 'scheduled'
              AND datetime(appointment_time) >= datetime(?)
              AND datetime(appointment_time) < datetime(?)
        """, (doctor_id, time_min, time_max)).fetchone()["c"]

        return {"total": total, "done": done, "no_show": no_show, "scheduled": scheduled}

    # dzień: [00:00, następny dzień 00:00)
    stats_day = stats_for_range(f"{day_str} 00:00:00", f"{next_day} 00:00:00")
    stats_week = stats_for_range(f"{week_start} 00:00:00", f"{week_end} 00:00:00")
    stats_month = stats_for_range(f"{month_start} 00:00:00", f"{next_month_start} 00:00:00")

    # --------------------------
    # WYKRES DZIENNY: ostatnie 7 dni (łącznie)
    # --------------------------
    last7_start = anchor_date - timedelta(days=6)
    daily_rows = conn.execute("""
        SELECT substr(appointment_time, 1, 10) AS d, COUNT(*) AS c
        FROM appointments
        WHERE doctor_id = ?
          AND date(appointment_time) >= date(?)
          AND date(appointment_time) <= date(?)
        GROUP BY substr(appointment_time, 1, 10)
        ORDER BY d ASC
    """, (doctor_id, str(last7_start), str(anchor_date))).fetchall()

    daily_map = {r["d"]: r["c"] for r in daily_rows}
    daily_labels = [(last7_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    daily_values = [daily_map.get(lbl, 0) for lbl in daily_labels]

    # --------------------------
    # WYKRES ROCZNY: 12 miesięcy (done vs no_show)
    # --------------------------
    year_end_month_start = anchor_date.replace(day=1)

    # koniec: 1. dzień następnego miesiąca (exclusive)
    if year_end_month_start.month == 12:
        year_end_next = date(year_end_month_start.year + 1, 1, 1)
    else:
        year_end_next = date(year_end_month_start.year, year_end_month_start.month + 1, 1)

    # start: 11 miesięcy wstecz (1 dzień miesiąca)
    y, m = year_end_month_start.year, year_end_month_start.month
    for _ in range(11):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    year_start = date(y, m, 1)

    # etykiety 12 miesięcy YYYY-MM
    year_labels = []
    y, m = year_start.year, year_start.month
    for _ in range(12):
        year_labels.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1

    year_rows = conn.execute("""
        SELECT
            substr(appointment_time, 1, 7) AS ym,
            status,
            COUNT(*) AS c
        FROM appointments
        WHERE doctor_id = ?
          AND datetime(appointment_time) >= datetime(?)
          AND datetime(appointment_time) < datetime(?)
          AND status IN ('done', 'no_show')
        GROUP BY substr(appointment_time, 1, 7), status
    """, (doctor_id, f"{year_start} 00:00:00", f"{year_end_next} 00:00:00")).fetchall()

    done_map = {}
    noshow_map = {}
    for r in year_rows:
        if r["status"] == "done":
            done_map[r["ym"]] = r["c"]
        elif r["status"] == "no_show":
            noshow_map[r["ym"]] = r["c"]

    year_done_values = [done_map.get(ym, 0) for ym in year_labels]
    year_noshow_values = [noshow_map.get(ym, 0) for ym in year_labels]

    conn.close()

    return render_template(
        "doctor_dashboard.html",
        # listy
        upcoming_appointments=upcoming_appointments,
        past_appointments=past_appointments,
        next_appointment=next_appointment,
        selected_date=selected_date,

        # statystyki
        stats_day=stats_day,
        stats_week=stats_week,
        stats_month=stats_month,

        # dane do wykresów (JSON)
        daily_labels_json=json.dumps(daily_labels),
        daily_values_json=json.dumps(daily_values),

        year_labels_json=json.dumps(year_labels),
        year_done_values_json=json.dumps(year_done_values),
        year_noshow_values_json=json.dumps(year_noshow_values),

        anchor_date=str(anchor_date)
    )

@app.route("/doctor/start")
def doctor_start():
    if session.get("role") != "doctor":
        return redirect(url_for("index"))

    doctor_id = session.get("doctor_id")

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT 
            a.id,
            a.appointment_time,
            a.symptoms,
            a.status,
            p.first_name,
            p.last_name,
            p.pesel,
            p.phone AS patient_phone,
            p.email AS patient_email
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        WHERE a.doctor_id = ?
        ORDER BY datetime(a.appointment_time) ASC
    """, (doctor_id,)).fetchall()
    conn.close()

    now = datetime.now()

    upcoming = []
    past = []
    for a in rows:
        appt_time = datetime.strptime(a["appointment_time"], "%Y-%m-%d %H:%M")
        if appt_time >= now:
            upcoming.append(a)
        else:
            past.append(a)

    past.reverse()

    next_appointment = upcoming[0] if upcoming else None

    return render_template(
        "doctor_start.html",
        next_appointment=next_appointment,
        upcoming_appointments=upcoming,
        past_appointments=past
    )

@app.route("/patient/start")
def patient_start():
    if session.get("role") != "patient":
        return redirect(url_for("index"))

    patient_id = session.get("patient_id")

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT
            a.id,
            a.appointment_time,
            a.symptoms,
            a.status,
            d.name AS doctor_name,
            d.specialization
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ?
        ORDER BY datetime(a.appointment_time) ASC
    """, (patient_id,)).fetchall()
    conn.close()

    now = datetime.now()

    upcoming = []
    past = []

    for a in rows:
        appt_time = datetime.strptime(a["appointment_time"], "%Y-%m-%d %H:%M")
        if appt_time >= now:
            upcoming.append(a)
        else:
            past.append(a)

    past.reverse()

    next_appointment = upcoming[0] if upcoming else None

    return render_template(
        "patient_start.html",
        next_appointment=next_appointment,
        upcoming_appointments=upcoming,
        past_appointments=past
    )

@app.route("/doctor/appointments/<int:appointment_id>/status", methods=["POST"])
def doctor_set_appointment_status(appointment_id):
    # ---- AUTORYZACJA ----
    if session.get("role") != "doctor":
        return redirect(url_for("index"))

    doctor_id = session.get("doctor_id")

    # ---- DANE Z FORMULARZA ----
    new_status = (request.form.get("status") or "").strip()
    selected_date = request.form.get("date")  # YYYY-MM-DD albo None

    ALLOWED_STATUSES = {"scheduled", "done", "no_show"}
    if new_status not in ALLOWED_STATUSES:
        flash("Nieprawidłowy status wizyty.", "danger")
        return redirect(url_for("doctor_dashboard"))

    # ---- DB ----
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE appointments
        SET status = ?
        WHERE id = ?
          AND doctor_id = ?
    """, (new_status, appointment_id, doctor_id))

    conn.commit()

    if cur.rowcount == 0:
        conn.close()
        flash("Nie znaleziono wizyty lub brak uprawnień.", "warning")
        return redirect(url_for("doctor_dashboard"))

    conn.close()

    # ---- REDIRECT (ważne dla statystyk) ----
    if selected_date:
        return redirect(url_for("doctor_dashboard", date=selected_date))

    return redirect(url_for("doctor_dashboard"))


@app.route("/check-appointment", methods=["GET", "POST"])
def check_appointment():
    if session.get("role") != "doctor":
        return redirect(url_for("index"))

    appointments = []
    search_performed = False
    identifier = ""

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        search_performed = True

        if not identifier:
            flash("Wpisz PESEL lub e-mail.", "warning")
            return render_template(
                "check_appointment.html",
                appointments=[],
                search_performed=True,
                identifier=identifier
            )

        conn = get_db_connection()

        # 1) znajdź pacjenta
        if identifier.isdigit() and len(identifier) == 11:
            patient = conn.execute(
                "SELECT id FROM patients WHERE pesel = ?",
                (identifier,)
            ).fetchone()
        else:
            patient = conn.execute(
                "SELECT id FROM patients WHERE lower(email) = ?",
                (identifier,)
            ).fetchone()

        if patient:
            # 2) pobierz wizyty pacjenta (wraz z danymi lekarza)
            appointments = conn.execute("""
                SELECT
                    a.appointment_time,
                    a.status,
                    d.name AS doctor_name,
                    d.room_number,
                    d.specialization
                FROM appointments a
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.patient_id = ?
                ORDER BY datetime(a.appointment_time) ASC
            """, (patient["id"],)).fetchall()

        conn.close()

        if not patient:
            flash("Nie znaleziono pacjenta o podanym PESEL/e-mail.", "warning")

    return render_template(
        "check_appointment.html",
        appointments=appointments,
        search_performed=search_performed,
        identifier=identifier
    )

@app.route("/api/doctor/<int:doctor_id>/taken")
def api_taken_slots(doctor_id):
    # dostęp tylko dla zalogowanego pacjenta (opcjonalnie)
    if session.get("role") != "patient":
        return jsonify({"times": []}), 403

    date = request.args.get("date")  # YYYY-MM-DD
    if not date:
        return jsonify({"times": []})

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT appointment_time
        FROM appointments
        WHERE doctor_id = ?
          AND appointment_time LIKE ?
    """, (doctor_id, f"{date} %")).fetchall()
    conn.close()

    # zakładam format "YYYY-MM-DD HH:MM"
    taken = [r["appointment_time"].split(" ")[1][:5] for r in rows]
    return jsonify({"times": taken})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
