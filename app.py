from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit, join_room
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "being_connected_secret"

socketio = SocketIO(app, async_mode="eventlet")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# =========================
# MONGODB CONNECTION
# =========================

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["being_connected"]

users_collection = db["users"]
profiles_collection = db["profiles"]
messages_collection = db["messages"]

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

        existing_user = users_collection.find_one({
            "application_number": app_no
        })

        if existing_user:
            return "Application number already exists!"

        result = users_collection.insert_one({
            "name": name,
            "application_number": app_no,
            "password": password
        })

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

        user = users_collection.find_one({
            "application_number": app_no,
            "password": password
        })

        if user:
            session["user_id"] = str(user["_id"])
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

    user_id = session["user_id"]

    my_profile = profiles_collection.find_one({
        "user_id": user_id
    })

    suggestions = []

    if my_profile:
        my_teach = (my_profile.get("skills_teach", "")).lower()
        my_learn = (my_profile.get("skills_learn", "")).lower()

        other_profiles = profiles_collection.find({
            "user_id": {"$ne": user_id}
        })

        for profile in other_profiles:
            other_teach = profile.get("skills_teach", "").lower()
            other_learn = profile.get("skills_learn", "").lower()

            if (my_learn and my_learn in other_teach) or \
               (my_teach and my_teach in other_learn):

                user_data = users_collection.find_one({
                    "_id": ObjectId(profile["user_id"])
                })

                suggestions.append({
                    "id": profile["user_id"],
                    "name": user_data["name"],
                    "skills_teach": profile.get("skills_teach"),
                    "skills_learn": profile.get("skills_learn"),
                    "profile_pic": profile.get("profile_pic")
                })

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

    user_id = session["user_id"]

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

        update_data = {
            "about": about,
            "skills_teach": skills_teach,
            "skills_learn": skills_learn,
            "linkedin": linkedin,
            "github": github,
            "leetcode": leetcode
        }

        if profile_pic:
            update_data["profile_pic"] = profile_pic

        profiles_collection.update_one(
            {"user_id": user_id},
            {"$set": update_data},
            upsert=True
        )

    profile_data = profiles_collection.find_one({
        "user_id": user_id
    })

    return render_template("profile.html",
                           name=session["name"],
                           profile=profile_data)

# =========================
# VIEW OTHER PROFILE
# =========================

@app.route("/profile/<user_id>")
def view_profile(user_id):
    if "user_id" not in session:
        return redirect("/login")

    user = users_collection.find_one({
        "_id": ObjectId(user_id)
    })

    profile = profiles_collection.find_one({
        "user_id": user_id
    })

    return render_template("view_profile.html",
                           user=user,
                           profile=profile)

# =========================
# CHAT
# =========================

@app.route("/chat/<receiver_id>")
def chat(receiver_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    receiver = users_collection.find_one({
        "_id": ObjectId(receiver_id)
    })

    messages = list(messages_collection.find({
        "$or": [
            {"sender_id": user_id, "receiver_id": receiver_id},
            {"sender_id": receiver_id, "receiver_id": user_id}
        ]
    }))

    room = f"{min(user_id, receiver_id)}_{max(user_id, receiver_id)}"

    return render_template("chat.html",
                           messages=messages,
                           user_id=user_id,
                           receiver=receiver,
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

    messages_collection.insert_one({
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "message": message
    })

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
# RUN (RENDER READY)
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
