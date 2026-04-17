from flask import Flask, request, jsonify, render_template, redirect, session
import sqlite3, json, requests, os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_fallback_key")

HF_API_KEY = os.getenv("HF_API_KEY")
MODEL = "google/flan-t5-large"

# ---------------- DB ---------------- #
def db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init():
    d = db()
    d.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        email TEXT,
        password_hash TEXT
    )""")

    d.execute("""CREATE TABLE IF NOT EXISTS chatbots(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        name TEXT,
        business_name TEXT,
        faq_data TEXT
    )""")
    d.commit()

init()

# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template("index.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        d = db()
        d.execute(
            "INSERT INTO users(email,password_hash) VALUES(?,?)",
            (request.form["email"], generate_password_hash(request.form["password"]))
        )
        d.commit()
        return redirect("/login")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        d = db()
        user = d.execute(
            "SELECT * FROM users WHERE email=?",
            (request.form["email"],)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session["user_id"] = user["id"]
            return redirect("/dashboard")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    bots = db().execute(
        "SELECT * FROM chatbots WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    return render_template("dashboard.html", bots=bots)

# ---------------- CHATBOT ---------------- #

@app.route("/create-bot", methods=["POST"])
def create_bot():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json

    db().execute(
        "INSERT INTO chatbots(user_id,name,business_name,faq_data) VALUES(?,?,?,?)",
        (
            session["user_id"],
            data["name"],
            data["business_name"],
            json.dumps(data["faqs"])
        )
    )
    db().commit()

    return jsonify({"status": "success"})

@app.route("/get-bots")
def get_bots():
    if "user_id" not in session:
        return jsonify([])

    bots = db().execute(
        "SELECT * FROM chatbots WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    return jsonify([dict(b) for b in bots])

# ---------------- AI ---------------- #

def match_faq(msg, faqs):
    msg = msg.lower()
    for f in faqs:
        if f["question"].lower() in msg:
            return f["answer"]
    return None

def ask_hf(message):
    url = f"https://api-inference.huggingface.co/models/{MODEL}"

    headers = {
        "Authorization": f"Bearer {HF_API_KEY}"
    }

    payload = {
        "inputs": f"Answer as a helpful business assistant:\n{message}",
        "parameters": {
            "max_new_tokens": 100
        }
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        return res.json()[0]["generated_text"]
    except:
        return "Sorry, I’m having trouble responding right now."

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json

    bot = db().execute(
        "SELECT * FROM chatbots WHERE id=?",
        (data["chatbot_id"],)
    ).fetchone()

    faqs = json.loads(bot["faq_data"])

    reply = match_faq(data["message"], faqs)

    if not reply:
        reply = ask_hf(data["message"])

    return jsonify({"reply": reply})

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    app.run(debug=True)
