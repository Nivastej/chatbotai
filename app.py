from flask import Flask, request, jsonify, render_template, redirect, session
import sqlite3, json, requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

HF_API_KEY = "YOUR_HF_API_KEY"
HF_URL = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"

def db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init():
    d = db()
    d.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT,password_hash TEXT)")
    d.execute("CREATE TABLE IF NOT EXISTS chatbots(id INTEGER PRIMARY KEY,user_id INTEGER,name TEXT,business_name TEXT,faq_data TEXT)")
    d.commit()
init()

@app.route("/")
def home(): return render_template("index.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        d=db()
        d.execute("INSERT INTO users(email,password_hash) VALUES(?,?)",
                  (request.form["email"], generate_password_hash(request.form["password"])))
        d.commit()
        return redirect("/login")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        d=db()
        u=d.execute("SELECT * FROM users WHERE email=?",(request.form["email"],)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session["user_id"]=u["id"]
            return redirect("/dashboard")
    return render_template("login.html")

@app.route("/dashboard")
def dash():
    if "user_id" not in session: return redirect("/login")
    bots=db().execute("SELECT * FROM chatbots WHERE user_id=?",(session["user_id"],)).fetchall()
    return render_template("dashboard.html", bots=bots)

@app.route("/create-bot", methods=["POST"])
def create():
    d=db()
    data=request.json
    d.execute("INSERT INTO chatbots(user_id,name,business_name,faq_data) VALUES(?,?,?,?)",
              (session["user_id"], data["name"], data["business_name"], json.dumps(data["faqs"])))
    d.commit()
    return jsonify({"ok":True})

@app.route("/get-bots")
def bots():
    d=db()
    rows=d.execute("SELECT * FROM chatbots WHERE user_id=?",(session.get("user_id"),)).fetchall()
    return jsonify([dict(r) for r in rows])

def faq_match(msg, faqs):
    for f in faqs:
        if f["question"].lower() in msg.lower():
            return f["answer"]
    return None

@app.route("/chat", methods=["POST"])
def chat():
    data=request.json
    bot=db().execute("SELECT * FROM chatbots WHERE id=?",(data["chatbot_id"],)).fetchone()
    faqs=json.loads(bot["faq_data"])
    ans=faq_match(data["message"], faqs)
    if not ans:
        r=requests.post(HF_URL, headers={"Authorization":f"Bearer {HF_API_KEY}"}, json={"inputs":data["message"]})
        ans=r.json()[0]["generated_text"]
    return jsonify({"reply":ans})

if __name__=="__main__":
    app.run()
