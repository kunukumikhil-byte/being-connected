from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# =========================
# CONFIG
# =========================

app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

DATABASE_URL = os.environ.get("DATABASE_URL")

# Fix for Supabase SSL
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# DATABASE MODELS
# =========================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    application_number = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    about = db.Column(db.Text)
    skills_teach = db.Column(db.String(200))
    skills_learn = db.Column(db.String(200))
    linkedin = db.Column(db.String(200))
    github = db.Column(db.String(200))
    leetcode = db.Column(db.String(200))
    profile_pic = db.Column(db.String(200))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer)
    receiver_id = db.Column(db.Integer)
    message = db.Column(db.Text)

# Create tables
with app.app_context():
    db.create_all()

# =========================
# ROUTES
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

        if User.query.filter_by(application_number=app_no).first():
            return "Application number already exists!"

        new_user = User(
            name=name,
            application_number=app_no,
            password=password
        )

        db.session.add(new_user)
        db.session.commit()

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

        user = User.query.filter_by(
            application_number=app_no,
            password=password
        ).first()

        if user:
            session["user_id"] = user.id
            session["name"] = user.name
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

    user_id = session["user_id"]
    my_profile = Profile.query.filter_by(user_id=user_id).first()

    suggestions = []

    if my_profile:
        profiles = Profile.query.filter(Profile.user_id != user_id).all()

        for profile in profiles:
            if (my_profile.skills_learn and profile.skills_teach and
                my_profile.skills_learn.lower() in profile.skills_teach.lower()):

                user = User.query.get(profile.user_id)
                suggestions.append(user)

    return render_template(
        "dashboard.html",
        name=session["name"],
        suggestions=suggestions,
        my_profile=my_profile
    )

# =========================
# PROFILE
# =========================

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    profile = Profile.query.filter_by(user_id=user_id).first()

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

        if not profile:
            profile = Profile(user_id=user_id)

        profile.about = about
        profile.skills_teach = skills_teach
        profile.skills_learn = skills_learn
        profile.linkedin = linkedin
        profile.github = github
        profile.leetcode = leetcode

        if profile_pic:
            profile.profile_pic = profile_pic

        db.session.add(profile)
        db.session.commit()

    return render_template("profile.html", profile=profile)

# =========================
# CHAT
# =========================

@app.route("/chat/<int:receiver_id>")
def chat(receiver_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    messages = Message.query.filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == receiver_id)) |
        ((Message.sender_id == receiver_id) & (Message.receiver_id == user_id))
    ).all()

    room = f"{min(user_id, receiver_id)}_{max(user_id, receiver_id)}"

    return render_template(
        "chat.html",
        messages=messages,
        user_id=user_id,
        receiver_id=receiver_id,
        room=room
    )

@socketio.on("join_room")
def handle_join(data):
    join_room(data["room"])

@socketio.on("send_message")
def handle_message(data):
    sender_id = data["sender_id"]
    receiver_id = data["receiver_id"]
    message = data["message"]
    room = data["room"]

    new_message = Message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        message=message
    )

    db.session.add(new_message)
    db.session.commit()

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
    return redirect("/")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
