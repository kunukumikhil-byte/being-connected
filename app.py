from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "simple_secret"

socketio = SocketIO(app)

# =========================
# DATABASE SETUP (SQLite)
# =========================

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        application_number TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        about TEXT,
        skills_teach TEXT,
        skills_learn TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        message TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# =========================
# HOME
# =========================

@app.route("/")
def home():
    return redirect("/login")

# =========================
# SIGNUP
# =========================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        app_no = request.form["application_number"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (name, application_number, password) VALUES (?, ?, ?)",
                      (name, app_no, password))
            conn.commit()
        except:
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
        app_no = request.form["application_number"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE application_number=? AND password=?",
                  (app_no, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["name"] = user[1]
            return redirect("/dashboard")

        return "Invalid credentials"

    return render_template("login.html")

# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM profiles WHERE user_id != ?", (session["user_id"],))
    profiles = c.fetchall()

    conn.close()

    return render_template("dashboard.html",
                           name=session["name"],
                           profiles=profiles)

# =========================
# PROFILE
# =========================

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":
        about = request.form["about"]
        skills_teach = request.form["skills_teach"]
        skills_learn = request.form["skills_learn"]

        c.execute("DELETE FROM profiles WHERE user_id=?",
                  (session["user_id"],))

        c.execute("INSERT INTO profiles (user_id, about, skills_teach, skills_learn) VALUES (?, ?, ?, ?)",
                  (session["user_id"], about, skills_teach, skills_learn))

        conn.commit()

    c.execute("SELECT * FROM profiles WHERE user_id=?",
              (session["user_id"],))
    profile = c.fetchone()

    conn.close()

    return render_template("profile.html", profile=profile)

# =========================
# CHAT
# =========================

@app.route("/chat/<int:receiver_id>")
def chat(receiver_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        SELECT * FROM messages
        WHERE (sender_id=? AND receiver_id=?)
        OR (sender_id=? AND receiver_id=?)
    """, (session["user_id"], receiver_id,
          receiver_id, session["user_id"]))

    messages = c.fetchall()
    conn.close()

    room = f"{min(session['user_id'], receiver_id)}_{max(session['user_id'], receiver_id)}"

    return render_template("chat.html",
                           messages=messages,
                           user_id=session["user_id"],
                           receiver_id=receiver_id,
                           room=room)

@socketio.on("join_room")
def handle_join(data):
    join_room(data["room"])

@socketio.on("send_message")
def handle_message(data):
    sender_id = data["sender_id"]
    receiver_id = data["receiver_id"]
    message = data["message"]
    room = data["room"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("INSERT INTO messages (sender_id, receiver_id, message) VALUES (?, ?, ?)",
              (sender_id, receiver_id, message))
    conn.commit()
    conn.close()

    emit("receive_message", {
        "sender_id": sender_id,
        "message": message
    }, room=room)

# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    socketio.run(app, debug=True)
