from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "being_connected_secret"

# SocketIO
socketio = SocketIO(app, async_mode="eventlet")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# =========================
# DATABASE CONNECTION
# =========================

def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# =========================
# CREATE TABLES
# =========================

def create_tables():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            application_number TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            about TEXT,
            skills_teach TEXT,
            skills_learn TEXT,
            linkedin TEXT,
            github TEXT,
            leetcode TEXT,
            profile_pic TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

create_tables()

# =========================
# HOME
# =========================

@app.route("/")
def home():
    return render_template("home.html")

# =========================
# SIGNUP
# =========================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        app_no = request.form.get("application_number")
        password = request.form.get("password")

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (name, application_number, password) VALUES (?, ?, ?)",
                (name, app_no, password)
            )
            conn.commit()
        except:
            conn.close()
            return "Application number already exists!"
        conn.close()

        return redirect("/login")

    return render_template("signup.html")

# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        app_no = request.form.get("application_number")
        password = request.form.get("password")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE application_number=? AND password=?",
            (app_no, password)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect("/dashboard")
        else:
            return "Invalid credentials"

    return render_template("login.html")

# =========================
# DASHBOARD WITH MATCHING
# =========================

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()

    my_profile = conn.execute(
        "SELECT * FROM profiles WHERE user_id=?",
        (session["user_id"],)
    ).fetchone()

    suggestions = []

    if my_profile:
        my_teach = (my_profile["skills_teach"] or "").lower()
        my_learn = (my_profile["skills_learn"] or "").lower()

        other_profiles = conn.execute("""
            SELECT users.id, users.name,
                   profiles.skills_teach,
                   profiles.skills_learn,
                   profiles.profile_pic
            FROM users
            JOIN profiles ON users.id = profiles.user_id
            WHERE users.id != ?
        """, (session["user_id"],)).fetchall()

        for user in other_profiles:
            other_teach = (user["skills_teach"] or "").lower()
            other_learn = (user["skills_learn"] or "").lower()

            if (my_learn and my_learn in other_teach) or \
               (my_teach and my_teach in other_learn):
                suggestions.append(user)

    conn.close()

    return render_template("dashboard.html",
                           name=session["name"],
                           suggestions=suggestions,
                           my_profile=my_profile)

# =========================
# PROFILE (EDIT OWN)
# =========================

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()

    if request.method == "POST":
        about = request.form.get("about")
        skills_teach = request.form.get("skills_teach")
        skills_learn = request.form.get("skills_learn")
        linkedin = request.form.get("linkedin")
        github = request.form.get("github")
        leetcode = request.form.get("leetcode")

        profile_pic = None
        if "profile_pic" in request.files:
            file = request.files["profile_pic"]
            if file.filename != "":
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                profile_pic = filename

        existing = conn.execute(
            "SELECT * FROM profiles WHERE user_id=?",
            (session["user_id"],)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE profiles
                SET about=?, skills_teach=?, skills_learn=?,
                    linkedin=?, github=?, leetcode=?,
                    profile_pic=COALESCE(?, profile_pic)
                WHERE user_id=?
            """, (about, skills_teach, skills_learn,
                  linkedin, github, leetcode,
                  profile_pic, session["user_id"]))
        else:
            conn.execute("""
                INSERT INTO profiles
                (user_id, about, skills_teach, skills_learn,
                 linkedin, github, leetcode, profile_pic)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session["user_id"], about, skills_teach,
                  skills_learn, linkedin, github,
                  leetcode, profile_pic))

        conn.commit()

    profile_data = conn.execute(
        "SELECT * FROM profiles WHERE user_id=?",
        (session["user_id"],)
    ).fetchone()

    conn.close()

    return render_template("profile.html",
                           name=session["name"],
                           profile=profile_data)

# =========================
# CHAT
# =========================

@app.route("/chat/<int:receiver_id>")
def chat(receiver_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()

    receiver = conn.execute(
        "SELECT id, name FROM users WHERE id=?",
        (receiver_id,)
    ).fetchone()

    messages = conn.execute("""
        SELECT * FROM messages
        WHERE (sender_id=? AND receiver_id=?)
        OR (sender_id=? AND receiver_id=?)
        ORDER BY timestamp ASC
    """, (session["user_id"], receiver_id,
          receiver_id, session["user_id"])).fetchall()

    conn.close()

    room = f"{min(session['user_id'], receiver_id)}_{max(session['user_id'], receiver_id)}"

    return render_template("chat.html",
                           messages=messages,
                           user_id=session["user_id"],
                           receiver=receiver,
                           receiver_id=receiver_id,
                           room=room)

@socketio.on("join_room")
def handle_join(data):
    join_room(data["room"])

@socketio.on("send_message")
def handle_message(data):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO messages (sender_id, receiver_id, message)
        VALUES (?, ?, ?)
    """, (data["sender_id"], data["receiver_id"], data["message"]))
    conn.commit()
    conn.close()

    emit("receive_message", {
        "sender_id": data["sender_id"],
        "message": data["message"]
    }, room=data["room"])

# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =========================
# RUN (RENDER READY)
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
