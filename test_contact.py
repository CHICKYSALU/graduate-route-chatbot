"""
test_contact.py

Tests for the /contact route.  gspread and smtplib are mocked so no real
credentials are required.  The knowledge_base.json is created temporarily if
it does not exist (it is gitignored but the app refuses to start without it).
"""

import csv
import os
import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ── Bootstrap: configure env vars BEFORE importing app ───────────────────────

os.environ["GEMINI_API_KEY"] = "fake-test-key"
for _k in ("GOOGLE_SHEETS_CREDENTIALS_FILE", "GOOGLE_SHEET_ID",
           "SMTP_EMAIL", "SMTP_APP_PASSWORD"):
    os.environ.pop(_k, None)

# Create a minimal knowledge_base.json so app.py doesn't refuse to start.
# The file is gitignored; run `python ingest.py` to build the real one.
_KB = pathlib.Path("data/knowledge_base.json")
_KB_CREATED_HERE = not _KB.exists()
if _KB_CREATED_HERE:
    _KB.parent.mkdir(parents=True, exist_ok=True)
    _KB.write_text("[]")

import app as _app  # noqa: E402  (must come after env + file setup)

if _KB_CREATED_HERE and _KB.exists():
    _KB.unlink()

# ── Fixtures ──────────────────────────────────────────────────────────────────

_FORM = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "whatsapp": "+44123456789",
    "country": "UK",
    "applying_for": "Postgraduate",
    "service": "Full Application Package",
    "target_countries": "Germany, Netherlands",
    "notes": "Need help with essays",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client with an isolated leads directory."""
    monkeypatch.setattr(_app, "LEADS_DIR", str(tmp_path))
    monkeypatch.setattr(_app, "LEADS_CSV", str(tmp_path / "leads.csv"))
    monkeypatch.setattr(_app, "CV_UPLOAD_DIR", str(tmp_path / "cv_uploads"))
    (tmp_path / "cv_uploads").mkdir()
    _app.app.config["TESTING"] = True
    with _app.app.test_client() as c:
        yield c


# ── Tests: basic route behaviour ─────────────────────────────────────────────

def test_contact_get(client):
    r = client.get("/contact")
    assert r.status_code == 200


def test_contact_saves_to_csv(client, tmp_path):
    r = client.post("/contact", data=_FORM)
    assert r.status_code == 200

    csv_path = tmp_path / "leads.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["email"] == "jane@example.com"
    assert rows[0]["full_name"] == "Jane Doe"


def test_contact_shows_success_message(client):
    r = client.post("/contact", data=_FORM)
    assert r.status_code == 200
    assert b"Jane" in r.data  # submitted_name passed to template


# ── Tests: no integrations ────────────────────────────────────────────────────

def test_contact_no_sheets_no_email(client, monkeypatch):
    """With no credentials, integrations are silently skipped."""
    monkeypatch.setattr(_app, "_sheets_worksheet", None)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "")
    monkeypatch.setattr(_app, "_SMTP_APP_PASSWORD", "")

    r = client.post("/contact", data=_FORM)
    assert r.status_code == 200


# ── Tests: Google Sheets ──────────────────────────────────────────────────────

def test_contact_inserts_header_when_row1_is_empty(client, monkeypatch):
    """Empty sheet (row_values returns []): header inserted at row 1, then data appended."""
    mock_ws = MagicMock()
    mock_ws.row_values.return_value = []          # sheet is blank
    monkeypatch.setattr(_app, "_sheets_worksheet", mock_ws)
    monkeypatch.setattr(_app, "_sheets_headers_written", False)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "")

    r = client.post("/contact", data=_FORM)
    assert r.status_code == 200

    mock_ws.insert_row.assert_called_once_with(_app.LEAD_FIELDS, index=1)
    mock_ws.append_row.assert_called_once()
    assert "jane@example.com" in mock_ws.append_row.call_args[0][0]


def test_contact_inserts_header_when_row1_wrong(client, monkeypatch):
    """Sheet exists but row 1 doesn't match LEAD_FIELDS: header inserted at row 1."""
    mock_ws = MagicMock()
    mock_ws.row_values.return_value = ["wrong", "columns"]
    monkeypatch.setattr(_app, "_sheets_worksheet", mock_ws)
    monkeypatch.setattr(_app, "_sheets_headers_written", False)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "")

    client.post("/contact", data=_FORM)

    mock_ws.insert_row.assert_called_once_with(_app.LEAD_FIELDS, index=1)


def test_contact_skips_header_when_row1_correct(client, monkeypatch):
    """Row 1 already has the right headers: no insert_row call."""
    mock_ws = MagicMock()
    mock_ws.row_values.return_value = _app.LEAD_FIELDS
    monkeypatch.setattr(_app, "_sheets_worksheet", mock_ws)
    monkeypatch.setattr(_app, "_sheets_headers_written", False)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "")

    client.post("/contact", data=_FORM)

    mock_ws.insert_row.assert_not_called()
    mock_ws.append_row.assert_called_once()  # only the data row


def test_contact_skips_header_check_after_first_write(client, monkeypatch):
    """_sheets_headers_written=True suppresses get_all_values on later requests."""
    mock_ws = MagicMock()
    monkeypatch.setattr(_app, "_sheets_worksheet", mock_ws)
    monkeypatch.setattr(_app, "_sheets_headers_written", True)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "")

    client.post("/contact", data=_FORM)

    mock_ws.get_all_values.assert_not_called()
    mock_ws.append_row.assert_called_once()


def test_contact_sheets_error_doesnt_crash(client, monkeypatch):
    """A Sheets exception is caught; the HTTP response still succeeds."""
    mock_ws = MagicMock()
    mock_ws.row_values.side_effect = Exception("network error")
    monkeypatch.setattr(_app, "_sheets_worksheet", mock_ws)
    monkeypatch.setattr(_app, "_sheets_headers_written", False)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "")

    r = client.post("/contact", data=_FORM)
    assert r.status_code == 200


# ── Tests: confirmation email ─────────────────────────────────────────────────

def test_contact_sends_confirmation_email(client, monkeypatch):
    """SMTP credentials set → starttls/login/sendmail are called."""
    monkeypatch.setattr(_app, "_sheets_worksheet", None)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "sender@example.com")
    monkeypatch.setattr(_app, "_SMTP_APP_PASSWORD", "app-password")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        r = client.post("/contact", data=_FORM)

    assert r.status_code == 200
    mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
    instance = mock_smtp_cls.return_value.__enter__.return_value
    instance.starttls.assert_called_once()
    instance.login.assert_called_once_with("sender@example.com", "app-password")
    instance.sendmail.assert_called_once()
    # Destination address contains the visitor's email
    _, send_args, _ = instance.sendmail.mock_calls[0]
    assert "jane@example.com" in send_args[1]


def test_contact_email_not_sent_without_recipient(client, monkeypatch):
    """No email is sent when the form has no email address."""
    monkeypatch.setattr(_app, "_sheets_worksheet", None)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "sender@example.com")
    monkeypatch.setattr(_app, "_SMTP_APP_PASSWORD", "app-password")

    form = dict(_FORM, email="")
    with patch("smtplib.SMTP") as mock_smtp_cls:
        r = client.post("/contact", data=form)

    assert r.status_code == 200
    mock_smtp_cls.assert_not_called()


def test_contact_email_error_doesnt_crash(client, monkeypatch):
    """An SMTP exception is caught; the HTTP response still succeeds."""
    monkeypatch.setattr(_app, "_sheets_worksheet", None)
    monkeypatch.setattr(_app, "_SMTP_EMAIL", "sender@example.com")
    monkeypatch.setattr(_app, "_SMTP_APP_PASSWORD", "app-password")

    with patch("smtplib.SMTP", side_effect=Exception("connection refused")):
        r = client.post("/contact", data=_FORM)

    assert r.status_code == 200
