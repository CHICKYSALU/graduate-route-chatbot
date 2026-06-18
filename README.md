# The Graduate Route — Website + Services Chatbot

The full website (Home, Services, FAQ, About, Contact) with a retrieval-augmented
chatbot built into every page. Built with Flask, ChromaDB, and Gemini 2.5 Flash,
styled with the brand's actual logo colors.

## How it works

1. `data/services.md` holds the website copy (services, packages, FAQs, about).
2. `ingest.py` splits that copy into 48 topic-sized chunks, embeds each one
   with Gemini's embedding model, and stores everything in
   `data/knowledge_base.json`. (An earlier version of this project used
   chromadb for this step. It was swapped out because chromadb's dependency
   tree, onnxruntime, grpcio, opentelemetry, a kubernetes client, is hundreds
   of MB for a knowledge base this small, which is too heavy for free hosts
   with tight disk quotas like PythonAnywhere. A JSON file plus in-memory
   cosine similarity does the same job for this scale of data.)
3. `app.py` is a Flask app that serves the website pages and a `/chat` API.
   For every visitor message, it embeds the message, compares it against
   every chunk in `data/knowledge_base.json` with cosine similarity, and
   asks Gemini 2.5 Flash to answer using the closest matches as context.
4. `static/js/chatbot-widget.js` is the floating chat widget, included on
   every page through `templates/base.html`, so it follows visitors across
   the site.
5. The Contact page's "Request a Service" form saves submissions to
   `data_store/leads.csv` and uploaded CVs to `data_store/cv_uploads/`. This
   is local file storage for now, see the note at the bottom about
   connecting it to email or a CRM later.

## Pages

- `/` — Home
- `/services` — full breakdown of every package and focused service
- `/faq` — all FAQs
- `/about` — about the founder and team
- `/contact` — the request-a-service form

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then paste your Gemini API key into .env
python ingest.py                   # builds chroma_db/ from data/services.md
python app.py                      # starts the server on http://localhost:5000
```

If port 5000 is already taken (common on macOS because of AirPlay Receiver),
run on a different port instead:
```bash
PORT=5001 python app.py
```

Open `http://localhost:5000` (or whichever port you used) in a browser to see
the site. Click the chat bubble in the corner to test the bot.

## Updating the knowledge base

Edit `data/services.md`, then re-run `python ingest.py` to rebuild the
collection. Restart `app.py` afterward.

## Checking submitted leads

```bash
cat data_store/leads.csv
ls data_store/cv_uploads/
```

## Optional: Google Sheets lead logging

Every contact form submission can be appended as a new row to a Google Sheet.
Both environment variables must be set; if either is missing the app starts
normally and prints a notice instead of crashing.

**Setup steps:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create or
   select a project.
2. Enable the **Google Sheets API** and the **Google Drive API** for that project.
3. Create a **Service Account**: IAM & Admin → Service Accounts → Create.
   No roles are needed at project level.
4. Under the service account → Keys → Add Key → JSON. Download the file and
   save it somewhere safe (e.g. `secrets/service-account.json`).  
   **Do not commit this file.** It is already covered by `.gitignore` if you
   keep it under `secrets/`.
5. Create a new Google Sheet. Copy its ID from the URL:
   `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`
6. Share the sheet with the service account's email address
   (found in the JSON file as `"client_email"`) with **Editor** access.
7. Add to your `.env`:
   ```
   GOOGLE_SHEETS_CREDENTIALS_FILE=/absolute/path/to/service-account.json
   GOOGLE_SHEET_ID=your_sheet_id_here
   ```

The app writes a header row automatically on the first submission if the sheet
is empty. Subsequent submissions append one row each.

## Optional: Gmail confirmation email

A confirmation email is sent automatically to the address the visitor submits.
Both environment variables must be set; if either is missing the app starts
normally and prints a notice instead of crashing.

**Setup steps:**

1. Use a Gmail account you control (ideally a dedicated one for the site).
2. Enable **2-Step Verification** on the account if not already active:
   Google Account → Security → 2-Step Verification.
3. Create an **App Password**: Google Account → Security → App Passwords.
   Choose "Mail" as the app and "Other" as the device (name it anything).
   Copy the 16-character password shown.
4. Add to your `.env`:
   ```
   SMTP_EMAIL=you@gmail.com
   SMTP_APP_PASSWORD=xxxx_xxxx_xxxx_xxxx
   ```

The email is sent over Gmail's SMTP server (smtp.gmail.com, port 587, STARTTLS).

## Running tests

```bash
pip install -r requirements.txt
pytest test_contact.py -v
```

The tests mock both `gspread` and `smtplib` so no real credentials are needed.

## Deploying

Push this repo to GitHub, then deploy on Render (or similar):

- Build command: `pip install -r requirements.txt && python ingest.py`
- Start command: `gunicorn app:app`
- Environment variable: `GEMINI_API_KEY`

Note: on most hosts, the local filesystem (`data_store/`) is wiped on redeploy.
For a permanent lead list, swap the CSV write in `app.py`'s `/contact` route for
an email send (e.g. via SendGrid) or a write to a real database, once you have
those credentials.

## Standalone widget

The `widget/` folder is a portable copy of just the chat bubble (JS + logo),
for cases where you want to add the chatbot to a different, already-existing
site instead of using this one. Point it at your deployed backend:

```html
<script>
  window.GRADUATE_ROUTE_CHAT_API = "https://your-backend.onrender.com/chat";
</script>
<script src="https://your-backend.onrender.com/widget/chatbot-widget.js"></script>
```
