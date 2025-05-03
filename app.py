from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    conn = get_db_connection()
    events = conn.execute('''
        SELECT e.*, MAX(d.date) as latest_date
        FROM events e
        LEFT JOIN event_dates d ON e.event_id = d.event_id
        GROUP BY e.event_id
        ORDER BY latest_date DESC
        LIMIT 5
    ''').fetchall()
    conn.close()
    return render_template('index.html', events=events)

@app.route('/all_events')
def all_events():
    conn = get_db_connection()
    events = conn.execute('''
        SELECT e.*, MAX(d.date) as latest_date
        FROM events e
        LEFT JOIN event_dates d ON e.event_id = d.event_id
        GROUP BY e.event_id
        ORDER BY latest_date DESC
    ''').fetchall()
    conn.close()
    return render_template('all_events.html', events=events)

@app.route('/event/<int:event_id>')
def event_detail(event_id):
    conn = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE event_id = ?', (event_id,)).fetchone()
    guests = conn.execute('SELECT name FROM guests JOIN event_guests ON guests.guest_id = event_guests.guest_id WHERE event_id = ?', (event_id,)).fetchall()
    organizers = conn.execute('SELECT name FROM organizers JOIN event_organizers ON organizers.organizer_id = event_organizers.organizer_id WHERE event_id = ?', (event_id,)).fetchall()
    images = conn.execute('SELECT image_path FROM images WHERE event_id = ?', (event_id,)).fetchall()
    dates = conn.execute('SELECT date FROM event_dates WHERE event_id = ?', (event_id,)).fetchall()
    conn.close()
    return render_template('event_detail.html', event=event, guests=guests, organizers=organizers, images=images, dates=dates)


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'icsb2024':
            session['admin'] = True
            return redirect(url_for('index'))

        else:
            flash('Invalid credentials')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/add_event', methods=['GET', 'POST'])
def add_event():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        title = request.form['title']
        venue = request.form['venue']
        type = request.form['type']
        report = request.form['report']
        guest_names = request.form['guests'].split(',')
        organizer_names = request.form['organizers'].split(',')
        main_image_name = request.form['main_image_name']
        dates = [d.strip() for d in request.form['dates'].split(',') if d.strip()]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('INSERT INTO events (title, event_date, venue, type, report, main_image) VALUES (?, NULL, ?, ?, ?, NULL)',
                       (title, venue, type, report))
        event_id = cursor.lastrowid

        main_image_path = None
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(save_path)
                    cursor.execute('INSERT INTO images (event_id, image_path) VALUES (?, ?)', (event_id, save_path))
                    if filename == main_image_name:
                        main_image_path = save_path

        if main_image_path:
            cursor.execute('UPDATE events SET main_image = ? WHERE event_id = ?', (main_image_path, event_id))

        for guest in guest_names:
            guest = guest.strip()
            if guest:
                cursor.execute('INSERT OR IGNORE INTO guests (name) VALUES (?)', (guest,))
                guest_id = cursor.execute('SELECT guest_id FROM guests WHERE name = ?', (guest,)).fetchone()[0]
                cursor.execute('INSERT INTO event_guests (event_id, guest_id) VALUES (?, ?)', (event_id, guest_id))

        for organizer in organizer_names:
            organizer = organizer.strip()
            if organizer:
                cursor.execute('INSERT OR IGNORE INTO organizers (name) VALUES (?)', (organizer,))
                organizer_id = cursor.execute('SELECT organizer_id FROM organizers WHERE name = ?', (organizer,)).fetchone()[0]
                cursor.execute('INSERT INTO event_organizers (event_id, organizer_id) VALUES (?, ?)', (event_id, organizer_id))

        for date in dates:
            cursor.execute('INSERT INTO event_dates (event_id, date) VALUES (?, ?)', (event_id, date))

        conn.commit()
        conn.close()
        flash('Event added successfully!')
        return redirect(url_for('index'))

    return render_template('add_event.html')


@app.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        venue = request.form['venue']
        type = request.form['type']
        report = request.form['report']
        guest_names = request.form['guests'].split(',')
        organizer_names = request.form['organizers'].split(',')
        main_image_name = request.form['main_image_name']
        dates = [d.strip() for d in request.form['dates'].split(',') if d.strip()]

        cursor.execute('UPDATE events SET title = ?, event_date = NULL, venue = ?, type = ?, report = ?, main_image = NULL WHERE event_id = ?',
                       (title, venue, type, report, event_id))

        cursor.execute('DELETE FROM event_guests WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM event_organizers WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM event_dates WHERE event_id = ?', (event_id,))

        for guest in guest_names:
            guest = guest.strip()
            if guest:
                cursor.execute('INSERT OR IGNORE INTO guests (name) VALUES (?)', (guest,))
                guest_id = cursor.execute('SELECT guest_id FROM guests WHERE name = ?', (guest,)).fetchone()[0]
                cursor.execute('INSERT INTO event_guests (event_id, guest_id) VALUES (?, ?)', (event_id, guest_id))

        for organizer in organizer_names:
            organizer = organizer.strip()
            if organizer:
                cursor.execute('INSERT OR IGNORE INTO organizers (name) VALUES (?)', (organizer,))
                organizer_id = cursor.execute('SELECT organizer_id FROM organizers WHERE name = ?', (organizer,)).fetchone()[0]
                cursor.execute('INSERT INTO event_organizers (event_id, organizer_id) VALUES (?, ?)', (event_id, organizer_id))

        for date in dates:
            cursor.execute('INSERT INTO event_dates (event_id, date) VALUES (?, ?)', (event_id, date))

        main_image_path = None
        if 'images' in request.files:
            files = request.files.getlist('images')
            cursor.execute('DELETE FROM images WHERE event_id = ?', (event_id,))
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(save_path)
                    cursor.execute('INSERT INTO images (event_id, image_path) VALUES (?, ?)', (event_id, save_path))
                    if filename == main_image_name:
                        main_image_path = save_path

        if main_image_path:
            cursor.execute('UPDATE events SET main_image = ? WHERE event_id = ?', (main_image_path, event_id))

        conn.commit()
        conn.close()
        flash('Event updated successfully!')
        return redirect(url_for('event_detail', event_id=event_id))

    event = cursor.execute('SELECT * FROM events WHERE event_id = ?', (event_id,)).fetchone()
    guests = cursor.execute('SELECT name FROM guests JOIN event_guests ON guests.guest_id = event_guests.guest_id WHERE event_id = ?', (event_id,)).fetchall()
    organizers = cursor.execute('SELECT name FROM organizers JOIN event_organizers ON organizers.organizer_id = event_organizers.organizer_id WHERE event_id = ?', (event_id,)).fetchall()
    dates = cursor.execute('SELECT date FROM event_dates WHERE event_id = ?', (event_id,)).fetchall()

    guest_list = ', '.join([g['name'] for g in guests])
    organizer_list = ', '.join([o['name'] for o in organizers])
    date_list = ', '.join([d['date'] for d in dates])

    conn.close()
    return render_template('edit_event.html', event=event, guests=guest_list, organizers=organizer_list, dates=date_list)


@app.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    if 'admin' not in session:
        flash('Unauthorized')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM images WHERE event_id = ?', (event_id,))
    cursor.execute('DELETE FROM event_guests WHERE event_id = ?', (event_id,))
    cursor.execute('DELETE FROM event_organizers WHERE event_id = ?', (event_id,))
    cursor.execute('DELETE FROM events WHERE event_id = ?', (event_id,))
    conn.commit()
    conn.close()
    flash('Event deleted successfully!')
    return redirect(url_for('index'))

if __name__ == '__main__':
    if not os.path.exists('static/uploads'):
        os.makedirs('static/uploads')
    app.run(debug=True)

