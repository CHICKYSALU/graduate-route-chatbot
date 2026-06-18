"""
app.py

Flask app for The Graduate Route. Serves the full website (home, services,
FAQ, about, contact) and the chatbot API the widget calls on every page.

Routes:
  GET  /              Home
  GET  /services       Services
  GET  /faq             FAQ
  GET  /about            About
  GET  /contact            Request a Service form
  POST /contact            Handles form submission (saved locally, see below)
  POST /chat                 Chatbot API used by the widget
  GET  /health
"""

import os
import csv
import json
import math
import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

EMBEDDING_MODEL = "models/embedding-001"
KNOWLEDGE_BASE_PATH = "data/knowledge_base.json"

if not os.path.exists(KNOWLEDGE_BASE_PATH):
    raise RuntimeError(
        f"Could not find {KNOWLEDGE_BASE_PATH}. Run 'python ingest.py' first."
    )

with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
    KNOWLEDGE_BASE = json.load(f)

app = Flask(__name__)
CORS(app)

LEADS_DIR = "data_store"
LEADS_CSV = os.path.join(LEADS_DIR, "leads.csv")
CV_UPLOAD_DIR = os.path.join(LEADS_DIR, "cv_uploads")
os.makedirs(CV_UPLOAD_DIR, exist_ok=True)

LEAD_FIELDS = [
    "timestamp", "full_name", "email", "whatsapp", "country",
    "applying_for", "service", "target_countries", "cv_filename", "notes",
]

SYSTEM_PROMPT = """You are the assistant for The Graduate Route, an admissions and \
scholarship consulting service for students applying to undergraduate and \
postgraduate programmes abroad.

Your job is to help visitors understand what The Graduate Route offers and point \
them to the right service for their situation. Use only the CONTEXT provided below \
to answer. Do not invent services, prices, timelines, or guarantees that are not in \
the context.

Rules:
- If the visitor describes their situation (for example, "I have a scholarship essay \
due" or "I don't know where to start"), recommend the single best-fitting service \
from the context and briefly explain why.
- If a visitor is unsure what they need, recommend starting with the Initial \
Consultation.
- Never claim admissions or scholarships are guaranteed.
- Never state a specific price. All services are paid, and exact pricing is shared \
during consultation or by request. Point visitors to the consultation or contact \
form for that.
- Keep answers conversational and concise. Use short paragraphs rather than long \
lists unless the visitor specifically asks for a breakdown.
- If the context does not contain the answer, say you are not sure and suggest the \
visitor book the Initial Consultation or use the contact form for that question.
"""


def cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_context(query: str, n_results: int = 4) -> str:
    query_embedding = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=query,
        task_type="retrieval_query",
    )["embedding"]

    scored = [
        (cosine_similarity(query_embedding, chunk["embedding"]), chunk)
        for chunk in KNOWLEDGE_BASE
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_chunks = [chunk["content"] for _, chunk in scored[:n_results]]
    return "\n\n---\n\n".join(top_chunks)


# ---------------------------------------------------------------------------
# Website pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", active="home")


@app.route("/services")
def services():
    return render_template("services.html", active="services")


@app.route("/faq")
def faq():
    return render_template("faq.html", active="faq")


@app.route("/about")
def about():
    return render_template("about.html", active="about")


@app.route("/widget/<path:filename>")
def widget(filename):
    return send_from_directory("widget", filename)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html", active="contact", submitted=False)

    form = request.form
    cv_file = request.files.get("cv")
    cv_filename = ""

    if cv_file and cv_file.filename:
        cv_filename = secure_filename(cv_file.filename)
        timestamp_prefix = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        cv_filename = f"{timestamp_prefix}_{cv_filename}"
        cv_file.save(os.path.join(CV_UPLOAD_DIR, cv_filename))

    row = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "full_name": form.get("full_name", ""),
        "email": form.get("email", ""),
        "whatsapp": form.get("whatsapp", ""),
        "country": form.get("country", ""),
        "applying_for": form.get("applying_for", ""),
        "service": form.get("service", ""),
        "target_countries": form.get("target_countries", ""),
        "cv_filename": cv_filename,
        "notes": form.get("notes", ""),
    }

    file_exists = os.path.exists(LEADS_CSV)
    with open(LEADS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LEAD_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return render_template(
        "contact.html", active="contact", submitted=True,
        submitted_name=row["full_name"].split(" ")[0] if row["full_name"] else "there"
    )


# ---------------------------------------------------------------------------
# Chatbot API
# ---------------------------------------------------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history") or []  # [{role: "user"|"bot", text: str}, ...]

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    context = retrieve_context(user_message)

    convo = [SYSTEM_PROMPT, f"CONTEXT:\n{context}\n"]
    for turn in history[-6:]:
        role = "Visitor" if turn.get("role") == "user" else "Assistant"
        convo.append(f"{role}: {turn.get('text', '')}")
    convo.append(f"Visitor: {user_message}")
    convo.append("Assistant:")

    prompt = "\n\n".join(convo)

    try:
        response = model.generate_content(prompt)
        answer = response.text.strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"answer": answer})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
