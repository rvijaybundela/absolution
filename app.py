from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import uuid
import hashlib
import os
import re

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None

app = Flask(__name__)

# ============================================================
# AB SOLUTION FINANCE SERVICE
# Single-file Flask + Inline HTML + Tailwind + Alpine.js
# ============================================================

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

GOOGLE_SHEET_ID = "1-f0APmTnQ8Ncgo9ABj24HvyDwc_eV2cjHKaMTv8_DWA"
GOOGLE_SHEET_WORKSHEET = os.getenv("GOOGLE_SHEET_WORKSHEET", "Leads")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "credentials.json"
)
GOOGLE_SHEET_HEADERS = [
    "event_id",
    "submitted_at",
    "service",
    "legal_name",
    "mobile",
    "email",
    "loan_amount",
    "loan_tenure",
    "employment",
    "risk_type",
    "medical_conditions",
    "premium_budget",
    "message",
]


def append_lead_to_google_sheet(form_data):
    """Append a lead when Google Sheets credentials are configured."""
    if gspread is None or Credentials is None:
        app.logger.warning("Google Sheets dependencies are not installed.")
        return False

    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        app.logger.warning(
            "Google Sheets credentials file is missing: %s",
            GOOGLE_CREDENTIALS_FILE
        )
        return False

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=scopes
    )
    spreadsheet = gspread.authorize(credentials).open_by_key(GOOGLE_SHEET_ID)
    try:
        sheet = spreadsheet.worksheet(GOOGLE_SHEET_WORKSHEET)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(
            title=GOOGLE_SHEET_WORKSHEET,
            rows=1000,
            cols=len(GOOGLE_SHEET_HEADERS)
        )

    if not sheet.get_all_values():
        sheet.append_row(GOOGLE_SHEET_HEADERS, value_input_option="USER_ENTERED")

    sheet.append_row(
        [form_data[column] for column in GOOGLE_SHEET_HEADERS],
        value_input_option="USER_ENTERED"
    )
    return True


# ============================================================
# GOOGLE SHEETS CONFIGURATION
# ============================================================
#
# INSTALL:
#   pip install flask gspread google-auth
#
# STEP 1:
# Create a Google Cloud service account.
#
# STEP 2:
# Download the service-account JSON credentials.
#
# STEP 3:
# Share your Google Sheet with the service-account email.
#
# STEP 4:
# Uncomment the following imports:
#
# import gspread
# from google.oauth2.service_account import Credentials
#
# STEP 5:
# Configure:
#
# GOOGLE_SHEET_ID = "YOUR_GOOGLE_SHEET_ID"
# GOOGLE_CREDENTIALS_FILE = "credentials.json"
#
# STEP 6:
# Authenticate:
#
# scopes = [
#     "https://www.googleapis.com/auth/spreadsheets",
#     "https://www.googleapis.com/auth/drive",
# ]
#
# credentials = Credentials.from_service_account_file(
#     GOOGLE_CREDENTIALS_FILE,
#     scopes=scopes
# )
#
# gc = gspread.authorize(credentials)
# sheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("Leads")
#
# STEP 7:
# Inside /submit-lead, after collecting form_data:
#
# sheet.append_row([
#     form_data["event_id"],
#     form_data["submitted_at"],
#     form_data["service"],
#     form_data["legal_name"],
#     form_data["mobile"],
#     form_data["email"],
#     form_data["loan_amount"],
#     form_data["loan_tenure"],
#     form_data["employment"],
#     form_data["risk_type"],
#     form_data["medical_conditions"],
#     form_data["premium_budget"],
#     form_data["message"],
# ], value_input_option="USER_ENTERED")
#
# ============================================================


def clean_text(value, max_length=500):
    """Basic server-side input sanitization."""
    if value is None:
        return ""

    value = str(value).strip()

    # Remove control characters.
    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", value)

    return value[:max_length]


def clean_phone(value):
    """Keep only safe phone characters."""
    value = clean_text(value, 20)
    value = re.sub(r"[^\d+\-\s()]", "", value)
    return value


def generate_event_id():
    """
    Creates a short confirmation identifier.

    The ID is not intended to be a cryptographic secret.
    It simply avoids exposing the raw internal UUID.
    """
    raw = f"{uuid.uuid4()}-{datetime.utcnow().isoformat()}"

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest().upper()

    return f"ABS-{digest[:4]}-{digest[4:10]}"


# ============================================================
# SINGLE UNIFIED LEAD PROCESSING ROUTE
# ============================================================

@app.post("/submit-lead")
def submit_lead():

    if not request.is_json:
        return jsonify({
            "success": False,
            "message": "Invalid request format."
        }), 400

    data = request.get_json(silent=True) or {}

    service = clean_text(data.get("service"), 100)
    legal_name = clean_text(data.get("legal_name"), 120)
    mobile = clean_phone(data.get("mobile"))
    email = clean_text(data.get("email"), 150)
    loan_amount = clean_text(data.get("loan_amount"), 50)
    loan_tenure = clean_text(data.get("loan_tenure"), 30)
    employment = clean_text(data.get("employment"), 100)

    risk_type = clean_text(data.get("risk_type"), 100)
    medical_conditions = clean_text(
        data.get("medical_conditions"),
        1000
    )
    premium_budget = clean_text(
        data.get("premium_budget"),
        50
    )

    message = clean_text(data.get("message"), 1000)

    # --------------------------------------------------------
    # Server-side validation
    # --------------------------------------------------------

    errors = []

    if not legal_name:
        errors.append("Legal name is required.")

    if not mobile:
        errors.append("Mobile number is required.")

    if mobile:
        digits_only = re.sub(r"\D", "", mobile)

        if len(digits_only) < 10 or len(digits_only) > 15:
            errors.append("Please provide a valid mobile number.")

    if email:
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.match(email_pattern, email):
            errors.append("Please provide a valid email address.")

    if not service:
        service = "General Enquiry"

    if errors:
        return jsonify({
            "success": False,
            "message": "Please correct the submitted information.",
            "errors": errors
        }), 400

    # --------------------------------------------------------
    # Generate confirmation event ID
    # --------------------------------------------------------

    event_id = generate_event_id()

    submitted_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------------
    # Final structured lead record
    # --------------------------------------------------------

    form_data = {
        "event_id": event_id,
        "submitted_at": submitted_at,
        "service": service,
        "legal_name": legal_name,
        "mobile": mobile,
        "email": email,
        "loan_amount": loan_amount,
        "loan_tenure": loan_tenure,
        "employment": employment,
        "risk_type": risk_type,
        "medical_conditions": medical_conditions,
        "premium_budget": premium_budget,
        "message": message,
    }

    sheet_saved = False
    try:
        sheet_saved = append_lead_to_google_sheet(form_data)
    except Exception:
        app.logger.exception("Google Sheets lead append failed.")

    # --------------------------------------------------------
    # GOOGLE SHEETS APPEND EXAMPLE
    # --------------------------------------------------------
    #
    # After configuring gspread above, use:
    #
    # sheet.append_row([
    #     form_data["event_id"],
    #     form_data["submitted_at"],
    #     form_data["service"],
    #     form_data["legal_name"],
    #     form_data["mobile"],
    #     form_data["email"],
    #     form_data["loan_amount"],
    #     form_data["loan_tenure"],
    #     form_data["employment"],
    #     form_data["risk_type"],
    #     form_data["medical_conditions"],
    #     form_data["premium_budget"],
    #     form_data["message"],
    # ], value_input_option="USER_ENTERED")
    #
    # --------------------------------------------------------

    # Production logging should use a proper logger/database.
    app.logger.info(
        "New lead received: %s | %s | %s",
        event_id,
        service,
        mobile
    )

    return jsonify({
        "success": True,
        "event_id": event_id,
        "message": "Your enquiry has been received successfully.",
        "sla": "Our financial desk will review your enquiry and contact you shortly.",
        "sheet_saved": sheet_saved
    })


# ============================================================
# FRONTEND
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<meta
    name="description"
    content="AB Solution Finance Service — professional financial assistance, loan solutions and insurance services."
>

<title>AB Solution Finance Service | Financial Solutions</title>


<!-- Tailwind CDN -->
<script src="https://cdn.tailwindcss.com"></script>

<script>
tailwind.config = {
    theme: {
        extend: {
            colors: {
                navy: "#0A192F",
                gold: "#D4AF37",
                slatebg: "#F4F6F9",
                charcoal: "#172033"
            },

            fontFamily: {
                sans: [
                    "Inter",
                    "ui-sans-serif",
                    "system-ui",
                    "sans-serif"
                ]
            },

            boxShadow: {
                luxury:
                    "0 25px 70px rgba(10,25,47,.13)",

                gold:
                    "0 15px 40px rgba(212,175,55,.22)"
            }
        }
    }
}
</script>


<!-- Alpine.js -->
<script
    defer
    src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"
></script>


<!-- Google Fonts -->
<link
    rel="preconnect"
    href="https://fonts.googleapis.com"
>

<link
    rel="preconnect"
    href="https://fonts.gstatic.com"
    crossorigin
>

<link
    href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap"
    rel="stylesheet"
>


<style>

:root {
    --navy: #0A192F;
    --gold: #D4AF37;
    --slate: #F4F6F9;
    --charcoal: #172033;
    --white: #ffffff;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    font-family: "DM Sans", sans-serif;
    background: var(--slate);
    color: var(--charcoal);
}

h1,
h2,
h3,
h4,
h5,
h6 {
    font-family: "Manrope", sans-serif;
}


/* ============================================================
   BACKGROUND MOTION
   ============================================================ */

.mesh {
    position: fixed;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
    z-index: -1;
}

.mesh::before,
.mesh::after {
    content: "";
    position: absolute;
    width: 500px;
    height: 500px;
    border-radius: 50%;
    filter: blur(100px);
    opacity: .10;
}

.mesh::before {
    background: #D4AF37;
    top: 10%;
    left: -200px;
    animation: floatOne 14s ease-in-out infinite;
}

.mesh::after {
    background: #0A192F;
    right: -200px;
    bottom: 5%;
    animation: floatTwo 18s ease-in-out infinite;
}

@keyframes floatOne {
    0%, 100% {
        transform: translate(0, 0);
    }

    50% {
        transform: translate(150px, 70px);
    }
}

@keyframes floatTwo {
    0%, 100% {
        transform: translate(0, 0);
    }

    50% {
        transform: translate(-130px, -80px);
    }
}


/* ============================================================
   NAVIGATION
   ============================================================ */

.nav-glass {
    background: rgba(10, 25, 47, .84);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
}

.nav-link {
    position: relative;
}

.nav-link::after {
    content: "";
    position: absolute;
    height: 2px;
    left: 50%;
    right: 50%;
    bottom: -7px;
    background: var(--gold);
    transition: .3s ease;
}

.nav-link:hover::after {
    left: 0;
    right: 0;
}


/* ============================================================
   HERO
   ============================================================ */

.hero-overlay {
    background:
        linear-gradient(
            90deg,
            rgba(10,25,47,.96) 0%,
            rgba(10,25,47,.78) 42%,
            rgba(10,25,47,.30) 100%
        );
}

.hero-glow {
    animation: heroGlow 4s ease-in-out infinite;
}

@keyframes heroGlow {

    0%, 100% {
        box-shadow:
            0 0 0 rgba(212,175,55,0);
    }

    50% {
        box-shadow:
            0 0 55px rgba(212,175,55,.20);
    }
}


/* ============================================================
   CARDS
   ============================================================ */

.service-card {
    transition:
        transform .35s ease,
        box-shadow .35s ease,
        border-color .35s ease;
}

.service-card:hover {
    transform: translateY(-10px);
    box-shadow:
        0 30px 70px rgba(10,25,47,.15);
    border-color: rgba(212,175,55,.65);
}

.service-icon {
    transition: transform .35s ease;
}

.service-card:hover .service-icon {
    transform: scale(1.08) rotate(-3deg);
}


/* ============================================================
   BUTTONS
   ============================================================ */

.gold-button {
    transition:
        transform .25s ease,
        box-shadow .25s ease;
}

.gold-button:hover {
    transform: translateY(-2px);
    box-shadow:
        0 15px 35px rgba(212,175,55,.28);
}


/* ============================================================
   MODAL
   ============================================================ */

.modal-backdrop {
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
}

.modal-panel {
    animation: modalIn .35s ease forwards;
}

@keyframes modalIn {

    from {
        opacity: 0;
        transform: translateY(25px) scale(.97);
    }

    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}


/* ============================================================
   INPUTS
   ============================================================ */

.form-input {
    width: 100%;
    border: 1px solid #DCE2EA;
    background: #F8FAFC;
    border-radius: 14px;
    padding: 13px 15px;
    outline: none;
    transition: .25s ease;
    color: #172033;
}

.form-input:focus {
    border-color: var(--gold);
    background: white;
    box-shadow:
        0 0 0 4px rgba(212,175,55,.10);
}


/* ============================================================
   MAP
   ============================================================ */

.map-frame {
    min-height: 450px;
    filter: saturate(.85);
}


/* ============================================================
   SCROLL REVEAL
   ============================================================ */

.reveal {
    animation: revealUp .9s ease both;
}

@keyframes revealUp {

    from {
        opacity: 0;
        transform: translateY(25px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}


/* ============================================================
   CUSTOM SCROLLBAR
   ============================================================ */

::-webkit-scrollbar {
    width: 9px;
}

::-webkit-scrollbar-track {
    background: #eef1f5;
}

::-webkit-scrollbar-thumb {
    background: #b7a15b;
    border-radius: 20px;
}

/* ============================================================
   AB SOLUTION LIGHT THEME
   ============================================================ */

:root {
    --ink: #17324d;
    --blue: #2f8fdb;
    --blue-soft: #eaf5ff;
    --mint: #dff7ef;
    --orange: #e59a55;
    --line: #dbe8f2;
}

body {
    background: #f7fbfe;
    color: var(--ink);
}

.nav-glass {
    background: rgba(255, 255, 255, .94);
    border-color: var(--line);
    box-shadow: 0 8px 30px rgba(23, 50, 77, .08);
}

header .text-white {
    color: var(--ink) !important;
}

.hero-overlay {
    background:
        linear-gradient(90deg, rgba(247,251,254,.98) 0%, rgba(247,251,254,.91) 42%, rgba(247,251,254,.20) 100%);
}

#home h1 {
    color: var(--ink) !important;
    letter-spacing: -.035em;
}

#home h1 .text-gold {
    color: var(--blue) !important;
}

#home h1 .text-white\/70 {
    color: #6f8498 !important;
}

#home p {
    color: #5f7488 !important;
}

.hero-company {
    animation: companyReveal 1.1s cubic-bezier(.2,.8,.2,1) both;
}

@keyframes companyReveal {
    from { opacity: 0; transform: translateY(18px); letter-spacing: .08em; }
    to { opacity: 1; transform: translateY(0); letter-spacing: -.035em; }
}

.bg-slatebg {
    background: #f1f7fb !important;
}

.service-card {
    border-color: var(--line) !important;
    border-radius: 18px !important;
    box-shadow: 0 12px 32px rgba(42, 92, 126, .06);
}

.service-card:hover {
    box-shadow: 0 22px 44px rgba(42, 92, 126, .14);
}

.service-card h3,
#services h2,
#emi h2,
#about h2,
#contact h2 {
    color: var(--ink) !important;
}

.service-card button {
    border-color: var(--blue) !important;
    color: var(--blue) !important;
}

.service-card button:hover {
    background: var(--blue) !important;
    color: white !important;
}

.partner-wall {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 26px;
}

.partner-mark {
    border: 1px solid var(--line);
    background: white;
    color: #6c8293;
    min-height: 64px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    letter-spacing: .08em;
    border-radius: 10px;
}

.contact-card {
    background: linear-gradient(145deg, #e7f4ff, #ffffff) !important;
    color: var(--ink) !important;
    border: 1px solid var(--line);
    box-shadow: 0 18px 46px rgba(42, 92, 126, .10);
}

.contact-card h3,
.contact-card .text-white\/55,
.contact-card .text-white\/80 {
    color: var(--ink) !important;
}

.contact-card .border-white\/15 {
    border-color: #b8d3e5;
    color: var(--blue);
}

.map-card {
    border-color: var(--line) !important;
    box-shadow: 0 18px 46px rgba(42, 92, 126, .10) !important;
}

.insurance-banner {
    background: linear-gradient(135deg, rgba(30,58,138,.92), rgba(15,23,42,.96)) !important;
}

.modal-panel {
    border: 1px solid var(--line);
}

.modal-panel form {
    background: #ffffff;
}

.gold-button {
    background: var(--orange) !important;
    color: white !important;
}

@media (min-width: 768px) {
    .partner-wall {
        grid-template-columns: repeat(6, minmax(0, 1fr));
    }
}

/* ============================================================
   REFERENCE-LED REDESIGN
   ============================================================ */

body {
    background: #ffffff;
}

.mesh {
    display: none;
}

.reference-hero {
    min-height: 760px !important;
    background: #126cc0 !important;
}

.reference-hero .hero-overlay {
    background:
        linear-gradient(90deg, rgba(11, 91, 169, .96), rgba(20, 117, 194, .72) 56%, rgba(18, 108, 192, .28)),
        linear-gradient(180deg, rgba(4, 45, 91, .15), rgba(4, 45, 91, .35));
}

.reference-hero > div:nth-child(2) {
    max-width: 1240px;
}

.reference-hero .hero-company {
    max-width: 960px;
    color: #ffffff !important;
    font-size: clamp(3.2rem, 8vw, 7.6rem) !important;
    line-height: .92 !important;
    text-transform: uppercase;
    text-shadow: 0 10px 30px rgba(2, 40, 82, .24);
}

.reference-hero .hero-company .text-gold {
    display: block;
    color: #ffffff !important;
}

.reference-hero .hero-company::after {
    content: "Financial assistance, structured with clarity.";
    display: block;
    max-width: 650px;
    margin-top: 28px;
    color: rgba(255,255,255,.84);
    font-family: "DM Sans", sans-serif;
    font-size: clamp(1rem, 1.7vw, 1.35rem);
    font-weight: 500;
    line-height: 1.55;
    letter-spacing: 0;
    text-transform: none;
}

.reference-hero .border-gold\/40 {
    border-color: rgba(255,255,255,.5);
    background: rgba(255,255,255,.08);
}

.reference-hero .text-gold {
    color: #ffffff !important;
}

.reference-hero .bg-gold {
    background: #29c77a !important;
    color: #ffffff !important;
}

.reference-hero .border-white\/20 {
    border-color: rgba(255,255,255,.55);
    background: rgba(255,255,255,.08);
}

#services,
#emi,
#about,
#contact {
    position: relative;
}

#services::before,
#emi::before,
#about::before,
#contact::before {
    content: "";
    display: block;
    width: 58px;
    height: 5px;
    margin-bottom: 24px;
    background: var(--blue);
}

#services > div,
#emi > div,
#about > div,
#contact > div {
    max-width: 1240px;
}

#services h2,
#emi h2,
#about h2,
#contact h2 {
    font-size: clamp(2rem, 4vw, 4rem);
    line-height: 1.05;
    letter-spacing: -.04em;
}

#services .service-card {
    min-height: 330px;
    padding: 34px;
    border: 0 !important;
    border-top: 5px solid var(--blue) !important;
    border-radius: 4px !important;
    box-shadow: 0 18px 45px rgba(27, 76, 116, .11);
}

#services .service-card:nth-child(2) {
    border-top-color: #26c27a !important;
}

#services .service-card:nth-child(3) {
    border-top-color: #e39a59 !important;
}

#services .service-card:nth-child(4) {
    border-top-color: #5964c8 !important;
}

#services .service-icon {
    width: 72px;
    height: 72px;
    border-radius: 50%;
    background: var(--blue-soft) !important;
    color: var(--blue) !important;
}

#services .service-card:nth-child(2) .service-icon {
    background: #e2f8ee !important;
    color: #20a96e !important;
}

#services .service-card:nth-child(3) .service-icon {
    background: #fff0e2 !important;
    color: #d77f31 !important;
}

#services .service-card:nth-child(4) .service-icon {
    background: #edeefe !important;
    color: #5964c8 !important;
}

#services .mt-7.bg-navy {
    border-radius: 5px;
    background: linear-gradient(90deg, rgba(14, 80, 143, .97), rgba(25, 130, 204, .80)) !important;
}

#contact {
    background: #edf5fa !important;
}

#contact .contact-card,
#contact .map-card {
    border-radius: 5px !important;
}

#contact .contact-card {
    padding: 42px !important;
}

#contact .map-card {
    min-height: 520px;
}

footer {
    background: #17324d !important;
}

@media (max-width: 640px) {
    .reference-hero {
        min-height: 700px !important;
    }

    #services .service-card {
        min-height: auto;
    }
}

/* ============================================================
   FINAL GLASSMORPHIC CORPORATE SYSTEM
   ============================================================ */

:root {
    --executive-blue: #0f172a;
    --executive-indigo: #1e3a8a;
    --slate-grey: #64748b;
    --ice-white: #f8fafc;
    --glass-line: rgba(255, 255, 255, .16);
    --glass-fill: rgba(255, 255, 255, .075);
    --glass-blue: #60a5fa;
}

body {
    color: var(--ice-white) !important;
    background:
        radial-gradient(circle at 12% 8%, rgba(96,165,250,.20), transparent 30%),
        radial-gradient(circle at 88% 28%, rgba(148,163,184,.13), transparent 28%),
        linear-gradient(135deg, #0f172a 0%, #172554 52%, #111827 100%) !important;
}

.mesh {
    display: block !important;
    opacity: .65;
}

.mesh::before,
.mesh::after {
    background: #60a5fa;
    filter: blur(120px);
    opacity: .13;
}

.mesh::after {
    background: #e2e8f0;
}

.nav-glass {
    background: rgba(15, 23, 42, .78) !important;
    border-color: var(--glass-line) !important;
    box-shadow: 0 12px 40px rgba(2, 6, 23, .25);
}

header .text-white {
    color: #ffffff !important;
}

.reference-hero {
    background: #0f172a !important;
}

.reference-hero .hero-overlay {
    background:
        linear-gradient(90deg, rgba(15,23,42,.94), rgba(30,58,138,.66) 58%, rgba(15,23,42,.18)),
        linear-gradient(180deg, rgba(15,23,42,.20), rgba(15,23,42,.72));
}

.reference-hero .hero-company {
    color: #fff !important;
}

.reference-hero .hero-company .text-gold {
    color: #bfdbfe !important;
}

.reference-hero .bg-gold,
.gold-button {
    background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important;
    border: 1px solid rgba(191,219,254,.45);
    box-shadow: 0 12px 30px rgba(37,99,235,.28);
}

#services,
#emi,
#about,
#contact,
.bg-white,
.bg-slatebg {
    background: transparent !important;
}

#services h2,
#emi h2,
#about h2,
#contact h2,
#services .service-card h3,
#emi label,
#emi strong {
    color: #ffffff !important;
}

#services p,
#emi p,
#about p,
#contact p,
#services .text-slate-500,
#emi .text-slate-500 {
    color: #cbd5e1 !important;
}

#services::before,
#emi::before,
#about::before,
#contact::before {
    background: #60a5fa;
}

.service-card,
#emi > div > div:last-child,
.partner-mark,
.contact-card,
.map-card,
#emi .bg-slatebg,
#about .bg-slatebg {
    background: var(--glass-fill) !important;
    border: 1px solid var(--glass-line) !important;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: 0 20px 60px rgba(2, 6, 23, .20) !important;
}

#services .service-card {
    border-top: 1px solid var(--glass-line) !important;
    border-radius: 22px !important;
}

#services .service-icon {
    background: rgba(96,165,250,.16) !important;
    color: #bfdbfe !important;
    border: 1px solid rgba(147,197,253,.30);
}

#services .service-card button {
    border-color: rgba(147,197,253,.5) !important;
    color: #dbeafe !important;
    background: rgba(96,165,250,.08);
}

#services .service-card button:hover {
    background: rgba(96,165,250,.24) !important;
}

.partner-mark {
    color: #e2e8f0;
}

#services .insurance-banner {
    border: 1px solid var(--glass-line);
    box-shadow: 0 20px 60px rgba(2,6,23,.22);
}

#emi input[type="range"] {
    accent-color: #60a5fa;
}

#emi .text-gold {
    color: #bfdbfe !important;
}

#emi .mt-9.bg-navy {
    background: linear-gradient(145deg, rgba(30,58,138,.86), rgba(15,23,42,.96)) !important;
    border: 1px solid rgba(147,197,253,.23);
}

#contact {
    background: rgba(2,6,23,.22) !important;
}

#contact .contact-card {
    color: #f8fafc !important;
}

#contact .contact-card h3,
#contact .contact-card .text-white\/55,
#contact .contact-card .text-white\/80 {
    color: #f8fafc !important;
}

#contact .contact-card .text-gold {
    color: #93c5fd !important;
}

footer {
    background: rgba(2,6,23,.72) !important;
    border-top: 1px solid var(--glass-line);
}

.modal-backdrop {
    background: rgba(2,6,23,.78) !important;
}

.modal-panel {
    background: rgba(248,250,252,.97) !important;
    border: 1px solid rgba(255,255,255,.25) !important;
    box-shadow: 0 30px 100px rgba(2,6,23,.5);
}

.form-input {
    border-color: #cbd5e1;
    background: #f8fafc;
}

@media (max-width: 640px) {
    .partner-wall {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

.service-marquee {
    overflow: hidden;
    margin-top: 34px;
    padding: 8px 0 18px;
    mask-image: linear-gradient(90deg, transparent, #000 7%, #000 93%, transparent);
}

.service-marquee-track {
    display: flex;
    width: max-content;
    gap: 18px;
    animation: servicesRight 38s linear infinite;
}

.service-marquee:hover .service-marquee-track {
    animation-play-state: paused;
}

.service-marquee-card {
    width: min(330px, 76vw);
    min-height: 178px;
    padding: 22px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 14px;
    align-items: start;
    border: 1px solid rgba(255,255,255,.17);
    border-radius: 20px;
    background: rgba(255,255,255,.08);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    box-shadow: 0 18px 42px rgba(2,6,23,.18);
}

.service-marquee-icon {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    color: #bfdbfe;
    background: rgba(96,165,250,.18);
}

.service-marquee-icon svg {
    width: 24px;
    height: 24px;
}

.service-marquee-card h3 {
    margin: 0;
    color: #fff;
    font: 800 1rem/1.2 "Manrope", sans-serif;
}

.service-marquee-card p {
    margin: 7px 0 0;
    color: #cbd5e1;
    font-size: .82rem;
    line-height: 1.45;
}

.service-marquee-card button {
    grid-column: 1 / -1;
    justify-self: start;
    border: 1px solid rgba(147,197,253,.45);
    border-radius: 999px;
    padding: 8px 13px;
    color: #dbeafe;
    background: rgba(59,130,246,.16);
    font-size: .78rem;
    font-weight: 800;
}

@keyframes servicesRight {
    from { transform: translateX(-50%); }
    to { transform: translateX(0); }
}

.services-grid {
    display: none !important;
}

#home h1,
#home h1 span,
#home .hero-company::after,
.partner-section h2,
.partner-section p,
#about h2,
#about h3,
#about p,
#contact h2,
#contact h3,
#emi h2,
#emi p {
    color: #f8fafc !important;
}

.partner-section {
    background: rgba(15,23,42,.35) !important;
    border-top: 1px solid rgba(255,255,255,.12);
    border-bottom: 1px solid rgba(255,255,255,.12);
}

.partner-section .text-slate-500,
.partner-section .text-slate-400 {
    color: #94a3b8 !important;
}

.partner-mark {
    min-height: 78px;
    color: #e2e8f0 !important;
    background: rgba(255,255,255,.10) !important;
    border-color: rgba(255,255,255,.18) !important;
    letter-spacing: .06em;
    transition: transform .25s ease, border-color .25s ease, background .25s ease;
}

.partner-mark:hover {
    transform: translateY(-4px);
    border-color: rgba(147,197,253,.65) !important;
    background: rgba(96,165,250,.18) !important;
}

#about .bg-white,
#about .bg-slatebg,
#contact .bg-white {
    color: #e2e8f0;
}

#about .text-slate-500,
#contact .text-slate-500 {
    color: #cbd5e1 !important;
}

.partner-section {
    position: relative;
    overflow: hidden;
}

.partner-section::after {
    content: "";
    position: absolute;
    left: -20%;
    right: -20%;
    bottom: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #facc15, #60a5fa, transparent);
    animation: networkLine 5s linear infinite;
}

@keyframes networkLine {
    from { transform: translateX(-24%); }
    to { transform: translateX(24%); }
}

.partner-mark:nth-child(1) { background: linear-gradient(135deg, rgba(190,24,93,.34), rgba(255,255,255,.08)) !important; }
.partner-mark:nth-child(2) { background: linear-gradient(135deg, rgba(5,150,105,.34), rgba(255,255,255,.08)) !important; }
.partner-mark:nth-child(3) { background: linear-gradient(135deg, rgba(14,165,233,.34), rgba(255,255,255,.08)) !important; }
.partner-mark:nth-child(4) { background: linear-gradient(135deg, rgba(14,116,144,.34), rgba(255,255,255,.08)) !important; }
.partner-mark:nth-child(5) { background: linear-gradient(135deg, rgba(239,68,68,.28), rgba(255,255,255,.08)) !important; }
.partner-mark:nth-child(6) { background: linear-gradient(135deg, rgba(37,99,235,.34), rgba(255,255,255,.08)) !important; }

.emi-card {
    max-width: 560px;
    justify-self: end;
    padding: 24px !important;
    border-radius: 22px !important;
}

.emi-card > div {
    margin-top: 20px !important;
}

.emi-card input[type="range"] {
    height: 4px;
    margin-top: 12px !important;
}

.emi-card .mt-9 {
    margin-top: 22px !important;
    padding: 20px !important;
    border-radius: 18px !important;
}

.emi-card .text-4xl {
    font-size: 2rem;
}

.heritage-proof {
    position: relative;
    gap: 14px !important;
}

.heritage-proof::before {
    content: "";
    position: absolute;
    top: 50%;
    left: 12%;
    right: 12%;
    height: 1px;
    background: linear-gradient(90deg, #facc15, #60a5fa, #facc15);
    opacity: .62;
    animation: heritageFlow 4s ease-in-out infinite alternate;
}

.heritage-proof > div {
    position: relative;
    z-index: 1;
    min-height: 168px;
    padding: 24px !important;
    border-radius: 22px !important;
    border-color: rgba(255,255,255,.24) !important;
    background: rgba(255,255,255,.08) !important;
}

.heritage-proof > div:nth-child(2),
.heritage-proof > div:nth-child(3) {
    transform: translateY(14px);
}

@keyframes heritageFlow {
    from { transform: scaleX(.78); opacity: .35; }
    to { transform: scaleX(1); opacity: .9; }
}

section {
    animation: sectionOpen .75s ease both;
}

@keyframes sectionOpen {
    from { opacity: .2; transform: translateY(16px); }
    to { opacity: 1; transform: translateY(0); }
}

.theme-switcher {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px;
    border: 1px solid rgba(255,255,255,.16);
    border-radius: 999px;
    background: rgba(255,255,255,.07);
}

.theme-switcher button {
    border: 0;
    border-radius: 999px;
    padding: 6px 9px;
    color: #cbd5e1;
    background: transparent;
    font-size: .68rem;
    font-weight: 800;
    cursor: pointer;
}

.theme-switcher button.active,
.theme-switcher button:hover {
    color: #0f172a;
    background: #f8fafc;
}

.partner-story {
    display: block;
    align-items: center;
    margin: 26px 0 18px;
    min-height: 70px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,.16);
    border-radius: 18px;
    background: rgba(255,255,255,.06);
}

.partner-quote-track {
    display: flex;
    width: max-content;
    gap: 48px;
    color: #dbeafe;
    font-size: .92rem;
    font-weight: 700;
    white-space: nowrap;
    animation: quoteRun 22s linear infinite;
}

.partner-story:hover .partner-quote-track {
    animation-play-state: paused;
}

@keyframes quoteRun {
    from { transform: translateX(0); }
    to { transform: translateX(-50%); }
}

.heritage-line {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 28px 0;
    padding: 20px 14px;
    overflow-x: auto;
    border: 1px solid rgba(255,255,255,.17);
    border-radius: 18px;
    background: rgba(255,255,255,.06);
}

.heritage-step {
    min-width: 132px;
    display: grid;
    gap: 4px;
}

.heritage-step span {
    color: #facc15;
    font-size: .72rem;
    font-weight: 900;
    letter-spacing: .14em;
}

.heritage-step strong {
    color: #f8fafc;
    font: 800 1rem/1.2 "Manrope", sans-serif;
}

.heritage-step small {
    color: #94a3b8;
    font-size: .72rem;
}

.heritage-connector {
    position: relative;
    flex: 1 0 32px;
    height: 2px;
    min-width: 32px;
    background: linear-gradient(90deg, #facc15, #60a5fa);
    animation: heritageConnector 1.8s ease-in-out infinite alternate;
}

.heritage-connector::after {
    content: "";
    position: absolute;
    right: 0;
    top: -3px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #60a5fa;
}

.contact-card .flex.gap-3 a {
    width: auto;
    min-width: 96px;
    padding: 0 14px;
    border-radius: 999px;
    color: #bfdbfe !important;
    font-size: .78rem;
    font-weight: 800;
}

.contact-detail {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #e2e8f0;
    text-decoration: none;
}

.contact-detail:hover {
    color: #facc15;
}

.contact-detail svg {
    width: 16px;
    height: 16px;
    flex: 0 0 auto;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
}

.footer-credit {
    color: #94a3b8;
    font-size: .75rem;
    letter-spacing: .04em;
}

@keyframes heritageConnector {
    from { opacity: .45; transform: scaleX(.78); transform-origin: left; }
    to { opacity: 1; transform: scaleX(1); transform-origin: left; }
}

body.theme-light {
    color: #0f172a !important;
    background: #f8fafc !important;
}

body.theme-light .nav-glass {
    background: rgba(248,250,252,.92) !important;
}

body.theme-light #services h2,
body.theme-light #emi h2,
body.theme-light #about h2,
body.theme-light #contact h2,
body.theme-light #services .service-card h3,
body.theme-light .partner-section h2,
body.theme-light .partner-section p {
    color: #0f172a !important;
}

body.theme-light #services p,
body.theme-light #emi p,
body.theme-light #about p,
body.theme-light #contact p,
body.theme-light .partner-section .text-slate-500 {
    color: #475569 !important;
}

body.theme-light .partner-section,
body.theme-light #contact {
    background: #eaf2fb !important;
}

body.theme-light .partner-story,
body.theme-light .heritage-line,
body.theme-light .heritage-proof > div,
body.theme-light .service-marquee-card {
    background: rgba(255,255,255,.82) !important;
    border-color: #cbd5e1 !important;
}

body.theme-light .partner-quote-track,
body.theme-light .service-marquee-card h3,
body.theme-light .heritage-step strong {
    color: #0f172a !important;
}

body.theme-light .service-marquee-card p,
body.theme-light .heritage-step small {
    color: #475569 !important;
}

body.theme-light .partner-mark {
    color: #0f172a !important;
}

body.theme-ocean .partner-quote-track,
body.theme-ocean .heritage-step strong,
body.theme-sunset .partner-quote-track,
body.theme-sunset .heritage-step strong {
    color: #f8fafc !important;
}

/* Requested removals from the public page. */
.partner-section,
.insurance-banner,
#emi .emi-intro,
.heritage-proof {
    display: none !important;
}

.top-banks {
    padding: 44px 0;
    background: rgba(15,23,42,.34);
    border-top: 1px solid rgba(255,255,255,.12);
    border-bottom: 1px solid rgba(255,255,255,.12);
}

.top-banks .section-kicker {
    color: #facc15;
    font-size: .72rem;
    font-weight: 900;
    letter-spacing: .22em;
}

.top-banks h2 {
    margin: 8px 0 22px;
    color: #f8fafc;
    font: 800 clamp(1.8rem, 3.5vw, 3rem)/1.1 "Manrope", sans-serif;
}

.top-bank-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
}

.top-bank {
    min-height: 72px;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px;
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 14px;
    background: rgba(255,255,255,.08);
    color: #e2e8f0;
    transition: transform .25s ease, background .25s ease;
}

.top-bank:hover {
    transform: translateY(-3px);
    background: rgba(96,165,250,.18);
}

.bank-initial {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    border-radius: 10px;
    color: #0f172a;
    background: #bfdbfe;
    font-size: .72rem;
    font-weight: 900;
}

#emi:not([style*="display: none"]) {
    padding: 44px 0 !important;
}

#emi > div > .grid {
    display: block;
}

#emi .emi-card {
    margin: 0 auto;
}

body.theme-light .top-banks {
    background: #eaf2fb;
}

body.theme-light .top-banks h2,
body.theme-light .top-bank {
    color: #0f172a;
}

body.theme-light .top-bank {
    background: rgba(255,255,255,.78);
    border-color: #cbd5e1;
}

@media (max-width: 760px) {
    .top-bank-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

body.theme-light .theme-switcher button.active,
body.theme-light .theme-switcher button:hover {
    color: #fff;
    background: #2563eb;
}

body.theme-ocean {
    background: linear-gradient(135deg, #042f2e, #075985 55%, #164e63) !important;
}

body.theme-ocean .reference-hero .hero-overlay {
    background: linear-gradient(90deg, rgba(4,47,46,.96), rgba(7,89,133,.68), rgba(8,47,73,.2));
}

body.theme-ocean .partner-section::after,
body.theme-ocean .heritage-proof::before {
    background: linear-gradient(90deg, transparent, #2dd4bf, #67e8f9, transparent);
}

body.theme-sunset {
    background: linear-gradient(135deg, #2b1224, #4c1d3d 54%, #312e81) !important;
}

body.theme-sunset .reference-hero .hero-overlay {
    background: linear-gradient(90deg, rgba(43,18,36,.96), rgba(124,45,80,.67), rgba(49,46,129,.2));
}

body.theme-sunset .partner-section::after,
body.theme-sunset .heritage-proof::before {
    background: linear-gradient(90deg, transparent, #fb923c, #f472b6, transparent);
}

body.theme-yellow {
    background: linear-gradient(135deg, #1c1917, #422006 52%, #713f12) !important;
}

body.theme-yellow .reference-hero .hero-overlay {
    background: linear-gradient(90deg, rgba(28,25,23,.96), rgba(113,63,18,.76), rgba(30,41,59,.22));
}

body.theme-yellow .partner-section::after,
body.theme-yellow .heritage-proof::before,
body.theme-yellow .heritage-connector {
    background: linear-gradient(90deg, transparent, #facc15, #fde68a, transparent);
}

body.theme-yellow .gold-button,
body.theme-yellow .theme-switcher button.active,
body.theme-yellow .theme-switcher button:hover {
    color: #422006;
    background: linear-gradient(135deg, #facc15, #f59e0b) !important;
}

body.theme-yellow .top-banks {
    background: rgba(66,32,6,.42);
}

body.theme-yellow .bank-initial {
    background: #fde68a;
}

.emi-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 14px;
    overflow-x: auto;
}

.emi-card-title {
    margin-bottom: 12px;
    color: #f8fafc;
    font: 800 clamp(1.35rem, 2.5vw, 1.8rem)/1.1 "Manrope", sans-serif;
    letter-spacing: -.02em;
}

.emi-tabs button {
    flex: 1 0 auto;
    padding: 10px 13px;
    border: 1px solid rgba(255,255,255,.16);
    border-radius: 10px 10px 0 0;
    color: #cbd5e1;
    background: rgba(255,255,255,.06);
    font-size: .78rem;
    font-weight: 800;
}

.emi-tabs button.active,
.emi-tabs button:hover {
    color: #0f172a;
    background: #f8fafc;
}

.emi-type-label {
    margin-bottom: 12px;
    color: #facc15;
    font-size: .68rem;
    font-weight: 900;
    letter-spacing: .16em;
    text-transform: uppercase;
}

.emi-number {
    width: 112px;
    margin-left: auto;
    padding: 7px 9px;
    border: 1px solid rgba(148,163,184,.42);
    border-radius: 7px;
    color: #e2e8f0;
    background: rgba(15,23,42,.42);
    font-size: .8rem;
    font-weight: 800;
    text-align: right;
}

.emi-total-card {
    padding: 16px;
    border-radius: 14px;
    background: rgba(255,255,255,.05);
}

.emi-card .grid-cols-2 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
}

.emi-breakup {
    height: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 18px;
    padding: 0 10px;
    border-radius: 999px;
    color: #cbd5e1;
    background: linear-gradient(90deg, #84cc16 var(--principal-share), #f97316 var(--principal-share));
    font-size: .66rem;
    font-weight: 900;
}

.emi-breakup span {
    transform: translateY(18px);
}

body.theme-yellow .emi-tabs button.active,
body.theme-yellow .emi-tabs button:hover {
    color: #422006;
    background: #fde68a;
}

body.theme-light .emi-number {
    color: #0f172a;
    background: #ffffff;
    border-color: #cbd5e1;
}

body.theme-light .emi-card-title {
    color: #0f172a;
}

@media (max-width: 1100px) {
    .theme-switcher {
        gap: 0;
    }

    .theme-switcher button {
        padding: 5px 6px;
        font-size: .58rem;
    }
}

@media (max-width: 560px) {
    .emi-card .grid-cols-2 {
        grid-template-columns: 1fr;
    }

    .emi-number {
        width: 92px;
    }
}

</style>

</head>


<body
    x-data="financeApp()"
    x-init="startHero()"
    :class="theme"
>

<div class="mesh"></div>


<!-- ============================================================
     NAVIGATION
     ============================================================ -->

<header
    class="fixed top-0 left-0 right-0 z-50 nav-glass border-b border-white/10"
>

<div class="max-w-7xl mx-auto px-5">

<div class="h-[76px] flex items-center justify-between">

    <!-- BRAND -->

    <a
        href="#home"
        class="flex items-center gap-3"
    >

        <div>

            <div
                class="
                    text-white
                    font-extrabold
                    tracking-wide
                    text-sm
                "
            >
                AB SOLUTION
            </div>

            <div
                class="
                    text-gold
                    text-[10px]
                    tracking-[.25em]
                    font-bold
                "
            >
                FINANCE SERVICE
            </div>

        </div>

    </a>


    <!-- DESKTOP NAV -->

    <nav
        class="
            hidden
            lg:flex
            items-center
            gap-8
        "
    >

        <a
            href="#home"
            class="nav-link text-white/80 hover:text-white text-sm font-semibold"
        >
            Home
        </a>

        <a
            href="#services"
            class="nav-link text-white/80 hover:text-white text-sm font-semibold"
        >
            Solutions
        </a>

        <a
            href="#emi"
            class="nav-link text-white/80 hover:text-white text-sm font-semibold"
        >
            EMI
        </a>

        <a
            href="#about"
            class="nav-link text-white/80 hover:text-white text-sm font-semibold"
        >
            About
        </a>

        <a
            href="#contact"
            class="nav-link text-white/80 hover:text-white text-sm font-semibold"
        >
            Contact
        </a>

    </nav>


    <!-- CTA -->

    <a
        href="#services"
        class="
            hidden
            sm:inline-flex
            items-center
            gap-2
            bg-gold
            text-navy
            px-5
            py-3
            rounded-full
            font-bold
            text-sm
            gold-button
        "
    >
        Product Desk
        <span>↗</span>
    </a>

    <div class="theme-switcher" aria-label="Choose colour theme">
        <button @click="theme = 'theme-executive'" :class="{ 'active': theme === 'theme-executive' }">Executive</button>
        <button @click="theme = 'theme-yellow'" :class="{ 'active': theme === 'theme-yellow' }">Yellow</button>
        <button @click="theme = 'theme-ocean'" :class="{ 'active': theme === 'theme-ocean' }">Ocean</button>
        <button @click="theme = 'theme-sunset'" :class="{ 'active': theme === 'theme-sunset' }">Sunset</button>
    </div>

</div>

</div>

</header>


<!-- ============================================================
     HERO
     ============================================================ -->

<section
    id="home"
    class="
        reference-hero
        relative
        min-h-screen
        flex
        items-center
        overflow-hidden
        bg-navy
    "
>

    <div class="absolute inset-0">
        <div class="absolute inset-0 hero-overlay"></div>

    </div>


    <div
        class="
            relative
            z-10
            w-full
            max-w-7xl
            mx-auto
            px-5
            pt-32
            pb-20
        "
    >

        <div class="max-w-3xl reveal">

            <div
                class="
                    inline-flex
                    items-center
                    gap-2
                    rounded-full
                    border
                    border-gold/40
                    bg-white/5
                    px-4
                    py-2
                    mb-7
                "
            >

                <span
                    class="
                        w-2
                        h-2
                        rounded-full
                        bg-gold
                        animate-pulse
                    "
                ></span>

                <span
                    class="
                        text-gold
                        text-xs
                        font-bold
                        tracking-[.2em]
                        uppercase
                    "
                >
                    Strategic Financial Assistance
                </span>

            </div>


            <h1
                class="
                    hero-company
                    text-white
                    text-5xl
                    sm:text-6xl
                    lg:text-8xl
                    font-black
                    leading-[.95]
                    tracking-[-.045em]
                "
            >
                <span x-text="heroHeadline"></span>
            </h1>


            <p
                class="
                    mt-7
                    text-white/70
                    text-lg
                    sm:text-xl
                    max-w-2xl
                    leading-relaxed
                "
            >
                Explore structured financial solutions across
                loans, business capital, personal credit,
                premium cards and insurance assistance.
            </p>


            <div
                class="
                    mt-9
                    flex
                    flex-col
                    sm:flex-row
                    gap-4
                "
            >

                <a
                    href="#services"
                    class="
                        gold-button
                        inline-flex
                        justify-center
                        items-center
                        gap-3
                        px-7
                        py-4
                        rounded-full
                        bg-gold
                        text-navy
                        font-extrabold
                    "
                >
                    Explore Solutions
                    <span>→</span>
                </a>

                <a
                    href="#emi"
                    class="
                        inline-flex
                        justify-center
                        items-center
                        px-7
                        py-4
                        rounded-full
                        border
                        border-white/20
                        bg-white/5
                        text-white
                        font-bold
                        hover:bg-white/10
                        transition
                    "
                >
                    Calculate EMI
                </a>

            </div>


            <!-- TRUST POINTS -->

            <div
                class="
                    mt-12
                    grid
                    grid-cols-2
                    sm:grid-cols-4
                    gap-5
                "
            >

                <div>
                    <div class="text-2xl font-black text-white">
                        10+
                    </div>

                    <div class="text-xs text-white/50 mt-1">
                        Years Experience
                    </div>
                </div>

                <div>
                    <div class="text-2xl font-black text-white">
                        4+
                    </div>

                    <div class="text-xs text-white/50 mt-1">
                        Solution Areas
                    </div>
                </div>

                <div>
                    <div class="text-2xl font-black text-white">
                        24/7
                    </div>

                    <div class="text-xs text-white/50 mt-1">
                        Digital Enquiry
                    </div>
                </div>

                <div>
                    <div class="text-2xl font-black text-white">
                        PAN
                    </div>

                    <div class="text-xs text-white/50 mt-1">
                        Service Assistance
                    </div>
                </div>

            </div>

        </div>

    </div>


</section>


<section
    class="
        partner-section
        bg-white
        py-10
        border-b
        border-slate-200
    "
>

<div class="max-w-7xl mx-auto px-5">

    <div class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">

        <div>
            <span class="text-gold text-xs font-black tracking-[.25em] uppercase">
                Trusted Network
            </span>

            <h2 class="text-navy text-2xl sm:text-3xl font-black mt-2">
                Banking partners for every objective.
            </h2>
        </div>

        <p class="text-slate-500 text-sm max-w-md">
            We help you organise product information before you approach the right financial institution.
        </p>

    </div>

    <div class="partner-story">
        <div class="partner-quote-track">
            <span>One requirement. The right conversation. A clearer financial next step.</span>
            <span aria-hidden="true">One requirement. The right conversation. A clearer financial next step.</span>
        </div>
    </div>

    <div class="partner-wall">
        <div class="partner-mark">AXIS BANK</div>
        <div class="partner-mark">IDBI BANK</div>
        <div class="partner-mark">BANK OF INDIA</div>
        <div class="partner-mark">CANARA BANK</div>
        <div class="partner-mark">ICICI BANK</div>
        <div class="partner-mark">HDFC BANK</div>
    </div>

</div>

</section>


<!-- ============================================================
     SERVICES
     ============================================================ -->

<section
    id="services"
    class="
        py-24
        sm:py-32
        bg-slatebg
    "
>

<div class="max-w-7xl mx-auto px-5">

    <div class="max-w-2xl mb-14">

        <span
            class="
                text-gold
                text-xs
                font-black
                tracking-[.25em]
                uppercase
            "
        >
            Product Desk
        </span>

        <h2
            class="
                text-navy
                text-4xl
                sm:text-5xl
                font-black
                mt-4
                tracking-tight
            "
        >
            Solutions built around
            <span class="text-gold">
                your objective.
            </span>
        </h2>

        <p
            class="
                text-slate-500
                mt-5
                text-lg
                leading-relaxed
            "
        >
            Select a financial category to start an enquiry.
            Eligibility, pricing and final approval remain
            subject to the respective financial institution's
            policies and assessment.
        </p>

    </div>


    <div class="service-marquee" aria-label="Financial services">
        <div class="service-marquee-track">
            <template x-for="service in serviceOffers" :key="service.title">
                <article class="service-marquee-card">
                    <div class="service-marquee-icon" x-html="service.icon"></div>
                    <div>
                        <h3 x-text="service.title"></h3>
                        <p x-text="service.description"></p>
                    </div>
                    <button @click="openLoan(service.enquiry)">Enquire Now <span aria-hidden="true">&#8594;</span></button>
                </article>
            </template>
            <template x-for="service in serviceOffers" :key="'copy-' + service.title">
                <article class="service-marquee-card" aria-hidden="true">
                    <div class="service-marquee-icon" x-html="service.icon"></div>
                    <div>
                        <h3 x-text="service.title"></h3>
                        <p x-text="service.description"></p>
                    </div>
                    <button tabindex="-1">Enquire Now <span aria-hidden="true">&#8594;</span></button>
                </article>
            </template>
        </div>
    </div>


    <div
        class="
            services-grid
            grid
            md:grid-cols-2
            lg:grid-cols-4
            gap-6
        "
    >

        <!-- HOME LOAN -->

        <article
            class="
                service-card
                bg-white
                rounded-[28px]
                p-7
                border
                border-slate-200
            "
        >

            <div
                class="
                    service-icon
                    w-14
                    h-14
                    rounded-2xl
                    bg-navy
                    text-gold
                    flex
                    items-center
                    justify-center
                    text-2xl
                "
            >
                <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z"/>
                    <path d="M8 21v-7h8v7"/>
                </svg>
            </div>

            <h3
                class="
                    text-navy
                    text-xl
                    font-extrabold
                    mt-7
                "
            >
                Home Loans
            </h3>

            <p
                class="
                    text-slate-500
                    text-sm
                    leading-relaxed
                    mt-3
                "
            >
                Explore financing pathways for residential
                property purchase and related requirements.
            </p>

            <button
                @click="openLoan('Home Loan')"
                class="
                    mt-7
                    w-full
                    rounded-xl
                    border
                    border-navy
                    py-3
                    text-navy
                    font-bold
                    hover:bg-navy
                    hover:text-white
                    transition
                "
            >
                Start Enquiry
            </button>

        </article>


        <!-- BUSINESS -->

        <article
            class="
                service-card
                bg-white
                rounded-[28px]
                p-7
                border
                border-slate-200
            "
        >

            <div
                class="
                    service-icon
                    w-14
                    h-14
                    rounded-2xl
                    bg-gold/15
                    text-gold
                    flex
                    items-center
                    justify-center
                    text-2xl
                "
            >
                <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path d="M4 19V5m0 14h16"/><path d="m6 15 4-5 3 3 5-7"/>
                    <path d="M17 6h1v1"/>
                </svg>
            </div>

            <h3
                class="
                    text-navy
                    text-xl
                    font-extrabold
                    mt-7
                "
            >
                Business Capital
            </h3>

            <p
                class="
                    text-slate-500
                    text-sm
                    leading-relaxed
                    mt-3
                "
            >
                Explore structured capital requirements for
                growing businesses and working-capital needs.
            </p>

            <button
                @click="openLoan('Business Capital')"
                class="
                    mt-7
                    w-full
                    rounded-xl
                    border
                    border-navy
                    py-3
                    text-navy
                    font-bold
                    hover:bg-navy
                    hover:text-white
                    transition
                "
            >
                Start Enquiry
            </button>

        </article>


        <!-- PERSONAL -->

        <article
            class="
                service-card
                bg-white
                rounded-[28px]
                p-7
                border
                border-slate-200
            "
        >

            <div
                class="
                    service-icon
                    w-14
                    h-14
                    rounded-2xl
                    bg-navy
                    text-gold
                    flex
                    items-center
                    justify-center
                    text-2xl
                "
            >
                <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <circle cx="12" cy="8" r="3"/><path d="M5 21a7 7 0 0 1 14 0"/>
                </svg>
            </div>

            <h3
                class="
                    text-navy
                    text-xl
                    font-extrabold
                    mt-7
                "
            >
                Personal Credit
            </h3>

            <p
                class="
                    text-slate-500
                    text-sm
                    leading-relaxed
                    mt-3
                "
            >
                Submit a personal finance requirement and
                discuss available lending options.
            </p>

            <button
                @click="openLoan('Personal Credit')"
                class="
                    mt-7
                    w-full
                    rounded-xl
                    border
                    border-navy
                    py-3
                    text-navy
                    font-bold
                    hover:bg-navy
                    hover:text-white
                    transition
                "
            >
                Start Enquiry
            </button>

        </article>


        <!-- CARDS -->

        <article
            class="
                service-card
                bg-white
                rounded-[28px]
                p-7
                border
                border-slate-200
            "
        >

            <div
                class="
                    service-icon
                    w-14
                    h-14
                    rounded-2xl
                    bg-gold/15
                    text-gold
                    flex
                    items-center
                    justify-center
                    text-2xl
                "
            >
                <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/>
                </svg>
            </div>

            <h3
                class="
                    text-navy
                    text-xl
                    font-extrabold
                    mt-7
                "
            >
                Premium Cards
            </h3>

            <p
                class="
                    text-slate-500
                    text-sm
                    leading-relaxed
                    mt-3
                "
            >
                Explore premium card-related financial product
                assistance based on eligibility.
            </p>

            <button
                @click="openLoan('Premium Cards')"
                class="
                    mt-7
                    w-full
                    rounded-xl
                    border
                    border-navy
                    py-3
                    text-navy
                    font-bold
                    hover:bg-navy
                    hover:text-white
                    transition
                "
            >
                Start Enquiry
            </button>

        </article>

    </div>


    <!-- INSURANCE -->

    <div
        class="
            insurance-banner
            mt-7
            bg-navy
            rounded-[32px]
            p-8
            sm:p-10
            flex
            flex-col
            lg:flex-row
            gap-8
            items-center
            justify-between
            overflow-hidden
            relative
        "
    >

        <div class="relative z-10">

            <span
                class="
                    text-gold
                    text-xs
                    font-black
                    tracking-[.25em]
                    uppercase
                "
            >
                Protection Desk
            </span>

            <h3
                class="
                    text-white
                    text-3xl
                    sm:text-4xl
                    font-black
                    mt-3
                "
            >
                Insurance planning,
                <span class="text-gold">
                    tailored.
                </span>
            </h3>

            <p
                class="
                    text-white/60
                    mt-3
                    max-w-xl
                "
            >
                Share your broad protection requirement and
                budget so the appropriate insurance enquiry
                can be reviewed.
            </p>

        </div>

        <button
            @click="openInsurance()"
            class="
                relative
                z-10
                shrink-0
                bg-gold
                text-navy
                px-7
                py-4
                rounded-full
                font-black
                gold-button
            "
        >
            Open Insurance Desk →
        </button>

    </div>

</div>

</section>


<section class="top-banks" aria-labelledby="top-banks-title">
<div class="max-w-7xl mx-auto px-5">
    <span class="section-kicker">TOP BANKING PARTNERS</span>
    <h2 id="top-banks-title">Trusted names for your next move.</h2>
    <div class="top-bank-grid">
        <div class="top-bank"><span class="bank-initial">H</span><strong>HDFC Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">IC</span><strong>ICICI Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">A</span><strong>Axis Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">S</span><strong>State Bank of India</strong></div>
        <div class="top-bank"><span class="bank-initial">C</span><strong>Canara Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">B</span><strong>Bank of India</strong></div>
        <div class="top-bank"><span class="bank-initial">ID</span><strong>IDBI Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">K</span><strong>Kotak Mahindra Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">PNB</span><strong>Punjab National Bank</strong></div>
        <div class="top-bank"><span class="bank-initial">BOB</span><strong>Bank of Baroda</strong></div>
        <div class="top-bank"><span class="bank-initial">U</span><strong>Union Bank of India</strong></div>
        <div class="top-bank"><span class="bank-initial">I</span><strong>IndusInd Bank</strong></div>
    </div>
</div>
</section>


<!-- ============================================================
     EMI CALCULATOR
     ============================================================ -->

<section
    id="emi"
    class="
        py-24
        sm:py-32
        bg-white
    "
>

<div class="max-w-7xl mx-auto px-5">

    <div class="grid lg:grid-cols-2 gap-14 items-center">

        <div class="emi-intro">

            <span
                class="
                    text-gold
                    text-xs
                    font-black
                    tracking-[.25em]
                    uppercase
                "
            >
                EMI Simulator
            </span>

            <h2
                class="
                    text-navy
                    text-4xl
                    sm:text-5xl
                    font-black
                    mt-4
                "
            >
                Understand the
                <span class="text-gold">
                    numbers.
                </span>
            </h2>

            <p
                class="
                    mt-5
                    text-slate-500
                    text-lg
                    leading-relaxed
                "
            >
                Adjust the sliders to see an indicative
                monthly instalment, principal component and
                total interest.
            </p>

            <div
                class="
                    mt-8
                    p-5
                    rounded-2xl
                    bg-slatebg
                    border
                    border-slate-200
                    text-sm
                    text-slate-500
                "
            >
                <strong class="text-navy">
                    Important:
                </strong>
                This calculator is illustrative only.
                Actual rates, fees, tenure, eligibility and
                repayment amounts depend on the applicable
                lender/product terms.
            </div>

        </div>


        <!-- CALCULATOR -->

        <div
            class="
                emi-card
                bg-slatebg
                rounded-[32px]
                p-7
                sm:p-9
                border
                border-slate-200
                shadow-luxury
            "
        >

            <div class="emi-card-title">EMI Calculator</div>

            <div class="emi-tabs" role="tablist" aria-label="Loan type">
                <button @click="calculatorType = 'Home Loan'" :class="{ 'active': calculatorType === 'Home Loan' }">Home Loan</button>
                <button @click="calculatorType = 'Personal Loan'" :class="{ 'active': calculatorType === 'Personal Loan' }">Personal Loan</button>
                <button @click="calculatorType = 'Business Loan'" :class="{ 'active': calculatorType === 'Business Loan' }">Business Loan</button>
            </div>

            <div class="emi-type-label" x-text="calculatorType"></div>

            <!-- LOAN -->

            <div>

                <div class="flex justify-between items-center">

                    <label
                        class="
                            font-bold
                            text-navy
                        "
                    >
                        Loan Balance
                    </label>

                    <span
                        class="
                            font-black
                            text-gold
                        "
                        x-text="formatCurrency(loanAmount)"
                    ></span>

                    <input
                        type="number"
                        min="100000"
                        max="10000000"
                        step="50000"
                        x-model.number="loanAmount"
                        class="emi-number"
                        aria-label="Loan amount"
                    >

                </div>

                <input
                    type="range"
                    min="100000"
                    max="10000000"
                    step="50000"
                    x-model.number="loanAmount"
                    class="w-full mt-5 accent-[#D4AF37]"
                >

            </div>


            <!-- RATE -->

            <div class="mt-8">

                <div class="flex justify-between">

                    <label
                        class="
                            font-bold
                            text-navy
                        "
                    >
                        Interest Rate
                    </label>

                    <span
                        class="font-black text-gold"
                        x-text="rate + '%'"
                    ></span>

                    <input
                        type="number"
                        min="5"
                        max="20"
                        step=".1"
                        x-model.number="rate"
                        class="emi-number"
                        aria-label="Interest rate"
                    >

                </div>

                <input
                    type="range"
                    min="5"
                    max="20"
                    step=".1"
                    x-model.number="rate"
                    class="w-full mt-5 accent-[#D4AF37]"
                >

            </div>


            <!-- TENURE -->

            <div class="mt-8">

                <div class="flex justify-between">

                    <label
                        class="font-bold text-navy"
                    >
                        Duration
                    </label>

                    <span
                        class="font-black text-gold"
                        x-text="tenure + ' Years'"
                    ></span>

                    <input
                        type="number"
                        min="1"
                        max="30"
                        step="1"
                        x-model.number="tenure"
                        class="emi-number"
                        aria-label="Loan tenure"
                    >

                </div>

                <input
                    type="range"
                    min="1"
                    max="30"
                    step="1"
                    x-model.number="tenure"
                    class="w-full mt-5 accent-[#D4AF37]"
                >

            </div>


            <!-- OUTPUT -->

            <div
                class="
                    mt-9
                    bg-navy
                    rounded-[26px]
                    p-6
                    text-white
                "
            >

                <div class="text-white/50 text-xs uppercase tracking-widest">
                    Indicative Monthly Outflow
                </div>

                <div
                    class="
                        text-4xl
                        font-black
                        text-gold
                        mt-2
                    "
                    x-text="formatCurrency(emi)"
                ></div>


                <div
                    class="
                        grid
                        grid-cols-2
                        gap-4
                        mt-7
                    "
                >

                    <div
                        class="
                            p-4
                            rounded-2xl
                            bg-white/5
                        "
                    >

                        <div class="text-white/40 text-xs">
                            Principal
                        </div>

                        <div
                            class="
                                font-bold
                                mt-1
                            "
                            x-text="formatCurrency(loanAmount)"
                        ></div>

                    </div>


                    <div
                        class="
                            p-4
                            rounded-2xl
                            bg-white/5
                        "
                    >

                        <div class="text-white/40 text-xs">
                            Total Interest
                        </div>

                        <div
                            class="
                                font-bold
                                mt-1
                            "
                            x-text="formatCurrency(totalInterest)"
                        ></div>

                    </div>

                    <div class="emi-total-card">
                        <div class="text-white/40 text-xs">Total Payment</div>
                        <div class="font-bold mt-1" x-text="formatCurrency(totalPayment)"></div>
                    </div>

                </div>

                <div class="emi-breakup" :style="'--principal-share:' + principalShare + '%'">
                    <span>Principal</span>
                    <span>Interest</span>
                </div>

            </div>

        </div>

    </div>

</div>

</section>


<!-- ============================================================
     ABOUT
     ============================================================ -->

<section
    id="about"
    class="
        py-24
        sm:py-32
        bg-slatebg
    "
>

<div class="max-w-7xl mx-auto px-5">

<div class="grid lg:grid-cols-2 gap-16 items-center">

    <div>

        <span
            class="
                text-gold
                text-xs
                font-black
                tracking-[.25em]
                uppercase
            "
        >
            Corporate Heritage
        </span>

        <h2
            class="
                text-navy
                text-4xl
                sm:text-5xl
                font-black
                mt-4
            "
        >
            A decade of
            <span class="text-gold">
                market execution.
            </span>
        </h2>

        <p
            class="
                text-slate-500
                text-lg
                leading-relaxed
                mt-6
            "
        >
            AB Solution Finance Service is positioned as a
            financial assistance and DSA platform connecting
            customers with relevant financial product
            opportunities.
        </p>

        <p
            class="
                text-slate-500
                leading-relaxed
                mt-4
            "
        >
            Our approach focuses on requirement discovery,
            documentation guidance and structured
            communication with applicable financial
            institutions.
        </p>


        <div
            class="
                mt-8
                flex
                items-center
                gap-4
            "
        >

            <div
                class="
                    w-14
                    h-14
                    rounded-2xl
                    bg-navy
                    text-gold
                    flex
                    items-center
                    justify-center
                    font-black
                    text-lg
                "
            >
                10+
            </div>

            <div>

                <div
                    class="
                        font-black
                        text-navy
                    "
                >
                    Years of Strategic Market Execution
                </div>

                <div
                    class="
                        text-sm
                        text-slate-500
                    "
                >
                    Experience milestone
                </div>

            </div>

        </div>

    </div>


    <div class="heritage-line" aria-label="AB Solution process">
        <div class="heritage-step"><span>01</span><strong>Start</strong><small>Requirement</small></div>
        <div class="heritage-connector"></div>
        <div class="heritage-step"><span>02</span><strong>Review</strong><small>Documentation</small></div>
        <div class="heritage-connector"></div>
        <div class="heritage-step"><span>03</span><strong>Direction</strong><small>Product pathway</small></div>
        <div class="heritage-connector"></div>
        <div class="heritage-step"><span>04</span><strong>Next step</strong><small>Clear follow-up</small></div>
    </div>


    <!-- PROOF CARDS -->

    <div
        class="
            heritage-proof
            grid
            sm:grid-cols-2
            gap-5
        "
    >

        <div
            class="
                bg-white
                p-7
                rounded-[28px]
                border
                border-slate-200
            "
        >

            <div class="text-gold text-2xl">
                ◈
            </div>

            <h3
                class="
                    text-navy
                    font-extrabold
                    mt-5
                "
            >
                Requirement First
            </h3>

            <p
                class="
                    text-sm
                    text-slate-500
                    mt-2
                    leading-relaxed
                "
            >
                Understand the requirement before discussing
                applicable product pathways.
            </p>

        </div>


        <div
            class="
                bg-navy
                p-7
                rounded-[28px]
                text-white
            "
        >

            <div class="text-gold text-2xl">
                ✓
            </div>

            <h3
                class="
                    font-extrabold
                    mt-5
                "
            >
                Structured Process
            </h3>

            <p
                class="
                    text-sm
                    text-white/55
                    mt-2
                    leading-relaxed
                "
            >
                Capture enquiry information clearly for
                appropriate follow-up.
            </p>

        </div>


        <div
            class="
                bg-white
                p-7
                rounded-[28px]
                border
                border-slate-200
            "
        >

            <div class="text-gold text-2xl">
                ◉
            </div>

            <h3
                class="
                    text-navy
                    font-extrabold
                    mt-5
                "
            >
                Clear Communication
            </h3>

            <p
                class="
                    text-sm
                    text-slate-500
                    mt-2
                    leading-relaxed
                "
            >
                Transparent communication around requirements,
                documentation and next steps.
            </p>

        </div>


        <div
            class="
                bg-white
                p-7
                rounded-[28px]
                border
                border-slate-200
            "
        >

            <div class="text-gold text-2xl">
                +
            </div>

            <h3
                class="
                    text-navy
                    font-extrabold
                    mt-5
                "
            >
                Multi-Product Desk
            </h3>

            <p
                class="
                    text-sm
                    text-slate-500
                    mt-2
                    leading-relaxed
                "
            >
                Multiple financial categories accessible from
                one enquiry interface.
            </p>

        </div>

    </div>

</div>

</div>

</section>


<!-- ============================================================
     CONTACT / DISPATCH HUB
     ============================================================ -->

<section
    id="contact"
    class="
        py-24
        sm:py-32
        bg-white
    "
>

<div class="max-w-7xl mx-auto px-5">

    <div class="mb-12">

        <span
            class="
                text-gold
                text-xs
                font-black
                tracking-[.25em]
                uppercase
            "
        >
            Dispatch Hub
        </span>

        <h2
            class="
                text-navy
                text-4xl
                sm:text-5xl
                font-black
                mt-4
            "
        >
            Start a conversation.
        </h2>

    </div>


    <div
        class="
            grid
            lg:grid-cols-5
            gap-7
        "
    >

        <!-- CONTACT INFO -->

        <div
            class="
                contact-card
                lg:col-span-2
                bg-navy
                rounded-[32px]
                p-8
                sm:p-10
                text-white
            "
        >

            <h3
                class="
                    text-2xl
                    font-black
                "
            >
                AB Solution Finance Service
            </h3>

            <p
                class="
                    text-white/55
                    mt-3
                    leading-relaxed
                "
            >
                Financial assistance and DSA services for
                customers seeking structured product
                information.
            </p>

            <button
                @click="openLoan('General Enquiry')"
                class="
                    mt-7
                    inline-flex
                    items-center
                    gap-2
                    rounded-full
                    bg-gold
                    px-5
                    py-3
                    text-sm
                    font-black
                    text-navy
                    gold-button
                "
            >
                Send an enquiry
                <span aria-hidden="true">→</span>
            </button>


            <div class="mt-9 space-y-7">

                <div>

                    <div
                        class="
                            text-gold
                            text-xs
                            font-bold
                            uppercase
                            tracking-widest
                        "
                    >
                        Office
                    </div>

                    <div
                        class="
                            mt-2
                            text-white/80
                            leading-relaxed
                        "
                    >
                        <span class="contact-detail">
                            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s7-6.1 7-12a7 7 0 1 0-14 0c0 5.9 7 12 7 12Z"/><circle cx="12" cy="9" r="2.2"/></svg>
                            <span>126 Bansi Trade Centre, MG Road,<br>Indore, Madhya Pradesh, India</span>
                        </span>
                        <br>
                        <a href="tel:+917869536698" class="contact-detail">
                            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h3l2 5-2 2a14 14 0 0 0 4 4l2-2 5 2v3c0 1.1-.9 2-2 2C10.4 19 5 13.6 5 7a2 2 0 0 1 2-2Z"/></svg>
                            +91 78695 36698
                        </a><br>
                        <a href="tel:+919755958612" class="contact-detail">
                            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h3l2 5-2 2a14 14 0 0 0 4 4l2-2 5 2v3c0 1.1-.9 2-2 2C10.4 19 5 13.6 5 7a2 2 0 0 1 2-2Z"/></svg>
                            +91 97559 58612
                        </a><br>
                        <a href="mailto:absolution1403@gmail.com" class="contact-detail">
                            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v12H4z"/><path d="m4 7 8 6 8-6"/></svg>
                            absolution1403@gmail.com
                        </a>
                    </div>

                </div>


                <div>

                    <div
                        class="
                            text-gold
                            text-xs
                            font-bold
                            uppercase
                            tracking-widest
                        "
                    >
                        Digital Desk
                    </div>

                    <div
                        class="
                            mt-2
                            text-white/80
                        "
                    >
                        Connect through the enquiry
                        form on this page.
                    </div>

                </div>


                <div>

                    <div
                        class="
                            text-gold
                            text-xs
                            font-bold
                            uppercase
                            tracking-widest
                        "
                    >
                        Social
                    </div>

                    <div class="flex gap-3 mt-3">

                        <a
                            href="https://wa.me/919999999999"
                            target="_blank"
                            rel="noopener"
                            class="
                                w-10 h-10
                                rounded-full
                                border
                                border-white/15
                                flex
                                items-center
                                justify-center
                                hover:bg-white/10
                                transition
                            "
                        >
                            WhatsApp
                        </a>

                    </div>

                </div>

            </div>

        </div>


        <!-- MAP -->

        <div
            class="
                map-card
                lg:col-span-3
                rounded-[32px]
                overflow-hidden
                border
                border-slate-200
                shadow-luxury
            "
        >

            <iframe
                class="map-frame w-full h-full"
                src="https://www.google.com/maps?q=Bansi%20Trade%20Centre%2C%20MG%20Road%2C%20Indore%2C%20Madhya%20Pradesh&output=embed"
                loading="lazy"
                referrerpolicy="no-referrer-when-downgrade"
                title="Bansi Trade Centre MG Road Indore map"
            ></iframe>

        </div>

    </div>

</div>

</section>


<!-- ============================================================
     FOOTER
     ============================================================ -->

<footer
    class="
        bg-[#071221]
        text-white
        py-10
    "
>

<div
    class="
        max-w-7xl
        mx-auto
        px-5
        flex
        flex-col
        md:flex-row
        justify-between
        gap-5
        items-center
    "
>

    <div>

        <div class="font-black">
            AB SOLUTION
        </div>

        <div
            class="
                text-gold
                text-[10px]
                tracking-[.25em]
                mt-1
            "
        >
            FINANCE SERVICE
        </div>

    </div>


</div>

</footer>


<!-- ============================================================
     LOAN MODAL
     ============================================================ -->

<div
    x-show="loanModal"
    x-cloak
    class="
        fixed
        inset-0
        z-[100]
        bg-navy/80
        modal-backdrop
        flex
        items-center
        justify-center
        p-4
    "
    @keydown.escape.window="loanModal = false"
    @click.self="loanModal = false"
>

<div
    class="
        modal-panel
        bg-white
        w-full
        max-w-2xl
        max-h-[92vh]
        overflow-y-auto
        rounded-[30px]
        shadow-2xl
    "
>

<div
    class="
        bg-navy
        p-7
        sm:p-8
        text-white
        flex
        justify-between
        gap-5
    "
>

<div>

    <div
        class="
            text-gold
            text-xs
            uppercase
            tracking-widest
            font-bold
        "
    >
        Product Enquiry
    </div>

    <h3
        class="
            text-2xl
            sm:text-3xl
            font-black
            mt-2
        "
        x-text="selectedService"
    ></h3>

</div>

<button
    @click="loanModal = false"
    class="
        w-10
        h-10
        rounded-full
        bg-white/10
        hover:bg-white/20
    "
>
    ×
</button>

</div>


<form
    @submit.prevent="submitForm"
    class="p-7 sm:p-8"
>

<input
    type="hidden"
    x-model="form.service"
>


<div
    class="
        grid
        sm:grid-cols-2
        gap-5
    "
>

    <div class="sm:col-span-2">

        <label class="text-sm font-bold text-navy">
            Legal Name *
        </label>

        <input
            required
            x-model="form.legal_name"
            class="form-input mt-2"
            placeholder="Enter your full legal name"
        >

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Mobile *
        </label>

        <input
            required
            type="tel"
            x-model="form.mobile"
            class="form-input mt-2"
            placeholder="+91 XXXXX XXXXX"
        >

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Email
        </label>

        <input
            type="email"
            x-model="form.email"
            class="form-input mt-2"
            placeholder="name@example.com"
        >

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Approx. Requirement
        </label>

        <input
            x-model="form.loan_amount"
            class="form-input mt-2"
            placeholder="e.g. ₹25,00,000"
        >

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Preferred Duration
        </label>

        <select
            x-model="form.loan_tenure"
            class="form-input mt-2"
        >

            <option value="">
                Select
            </option>

            <option>1 - 3 Years</option>
            <option>3 - 5 Years</option>
            <option>5 - 10 Years</option>
            <option>10+ Years</option>

        </select>

    </div>


    <div class="sm:col-span-2">

        <label class="text-sm font-bold text-navy">
            Employment / Business Profile
        </label>

        <select
            x-model="form.employment"
            class="form-input mt-2"
        >

            <option value="">
                Select profile
            </option>

            <option>Salaried</option>
            <option>Self Employed</option>
            <option>Business Owner</option>
            <option>Professional</option>
            <option>Other</option>

        </select>

    </div>


    <div class="sm:col-span-2">

        <label class="text-sm font-bold text-navy">
            Additional Requirement
        </label>

        <textarea
            x-model="form.message"
            class="form-input mt-2"
            rows="4"
            placeholder="Tell us about your requirement..."
        ></textarea>

    </div>

    <div class="footer-credit md:ml-auto">@rvjbundela</div>

</div>


<div
    x-show="formError"
    class="
        mt-5
        p-4
        rounded-xl
        bg-red-50
        text-red-700
        text-sm
    "
    x-text="formError"
></div>


<button
    type="submit"
    :disabled="loading"
    class="
        mt-7
        w-full
        py-4
        rounded-2xl
        bg-gold
        text-navy
        font-black
        gold-button
        disabled:opacity-60
    "
>

<span
    x-show="!loading"
>
    Submit Secure Enquiry →
</span>

<span
    x-show="loading"
>
    Processing Enquiry...
</span>

</button>


<p
    class="
        text-xs
        text-slate-400
        text-center
        mt-4
    "
>
    By submitting this enquiry, you request contact
    regarding the selected financial service.
</p>

</form>

</div>

</div>


<!-- ============================================================
     INSURANCE MODAL
     ============================================================ -->

<div
    x-show="insuranceModal"
    x-cloak
    class="
        fixed
        inset-0
        z-[100]
        bg-navy/80
        modal-backdrop
        flex
        items-center
        justify-center
        p-4
    "
    @keydown.escape.window="insuranceModal = false"
    @click.self="insuranceModal = false"
>

<div
    class="
        modal-panel
        bg-white
        w-full
        max-w-2xl
        max-h-[92vh]
        overflow-y-auto
        rounded-[30px]
        shadow-2xl
    "
>

<div
    class="
        bg-navy
        p-7
        sm:p-8
        text-white
        flex
        justify-between
    "
>

<div>

    <div
        class="
            text-gold
            text-xs
            uppercase
            tracking-widest
            font-bold
        "
    >
        Protection Desk
    </div>

    <h3
        class="
            text-2xl
            sm:text-3xl
            font-black
            mt-2
        "
    >
        Tailored Insurance Enquiry
    </h3>

</div>

<button
    @click="insuranceModal = false"
    class="
        w-10
        h-10
        rounded-full
        bg-white/10
    "
>
    ×
</button>

</div>


<form
    @submit.prevent="submitInsurance"
    class="p-7 sm:p-8"
>

<div class="space-y-5">

    <div>

        <label class="text-sm font-bold text-navy">
            Legal Name *
        </label>

        <input
            required
            x-model="insurance.legal_name"
            class="form-input mt-2"
            placeholder="Enter legal name"
        >

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Mobile *
        </label>

        <input
            required
            type="tel"
            x-model="insurance.mobile"
            class="form-input mt-2"
            placeholder="+91 XXXXX XXXXX"
        >

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Risk Matrix *
        </label>

        <select
            required
            x-model="insurance.risk_type"
            class="form-input mt-2"
        >

            <option value="">
                Select protection category
            </option>

            <option>Term Life</option>
            <option>Global Health</option>
            <option>Enterprise Cover</option>

        </select>

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Declared Medical Pre-conditions
        </label>

        <textarea
            x-model="insurance.medical_conditions"
            class="form-input mt-2"
            rows="4"
            placeholder="Provide relevant information"
        ></textarea>

    </div>


    <div>

        <label class="text-sm font-bold text-navy">
            Annual Premium Budget
        </label>

        <select
            x-model="insurance.premium_budget"
            class="form-input mt-2"
        >

            <option value="">
                Select budget
            </option>

            <option>Below ₹10,000</option>
            <option>₹10,000 - ₹25,000</option>
            <option>₹25,000 - ₹50,000</option>
            <option>₹50,000 - ₹1,00,000</option>
            <option>Above ₹1,00,000</option>

        </select>

    </div>

</div>


<div
    x-show="formError"
    class="
        mt-5
        p-4
        rounded-xl
        bg-red-50
        text-red-700
        text-sm
    "
    x-text="formError"
></div>


<button
    type="submit"
    :disabled="loading"
    class="
        mt-7
        w-full
        py-4
        rounded-2xl
        bg-gold
        text-navy
        font-black
        disabled:opacity-60
    "
>

<span x-show="!loading">
    Submit Insurance Enquiry →
</span>

<span x-show="loading">
    Processing...
</span>

</button>

</form>

</div>

</div>


<!-- ============================================================
     THANK YOU OVERLAY
     ============================================================ -->

<div
    x-show="successModal"
    x-cloak
    class="
        fixed
        inset-0
        z-[200]
        bg-navy/90
        modal-backdrop
        flex
        items-center
        justify-center
        p-5
    "
>

<div
    class="
        modal-panel
        bg-white
        rounded-[32px]
        w-full
        max-w-lg
        p-8
        sm:p-10
        text-center
        shadow-2xl
    "
>

<div
    class="
        mx-auto
        w-20
        h-20
        rounded-full
        bg-gold/15
        text-gold
        flex
        items-center
        justify-center
        text-4xl
    "
>
    ✓
</div>


<h2
    class="
        text-navy
        text-3xl
        font-black
        mt-7
    "
>
    Thank you!
</h2>


<p
    class="
        text-slate-500
        mt-4
        leading-relaxed
    "
>
    Your enquiry has been securely registered with the
    AB Solution Finance Service desk.
</p>


<div
    class="
        mt-7
        p-5
        rounded-2xl
        bg-navy
        text-left
    "
>

    <div
        class="
            text-white/40
            text-xs
            uppercase
            tracking-widest
        "
    >
        Encrypted Event ID
    </div>

    <div
        class="
            text-gold
            text-xl
            font-black
            tracking-widest
            mt-2
            break-all
        "
        x-text="eventId"
    ></div>

</div>


<div
    class="
        mt-5
        p-4
        rounded-2xl
        bg-slatebg
        text-sm
        text-slate-600
    "
>

    <strong class="text-navy">
        Response SLA:
    </strong>

    Our financial desk will review the enquiry and
    contact you shortly.

</div>


<button
    @click="
        successModal = false;
        window.location.hash = 'home';
    "
    class="
        mt-7
        w-full
        py-4
        rounded-2xl
        bg-navy
        text-white
        font-bold
    "
>
    Return to Website
</button>

</div>

</div>


<script>

function financeApp() {

    return {

        theme: "theme-executive",

        /* =====================================================
           HERO
           ===================================================== */

        heroHeadline: "Financial Assistance, Structured with Clarity",

        headlineIndex: 0,

        heroHeadlines: [
            "Financial Assistance, Structured with Clarity",
            "Loans, Insurance & Investment Solutions",
            "Trusted Partner for Your Financial Growth"
        ],

        serviceOffers: [
            {
                title: "Personal Loan",
                enquiry: "Personal Loan",
                description: "Flexible finance guidance for planned personal goals.",
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="3"/><path d="M5 21a7 7 0 0 1 14 0"/></svg>'
            },
            {
                title: "Business Loan",
                enquiry: "Business Loan",
                description: "Structured capital support for growing enterprises.",
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5m0 14h16"/><path d="m6 15 4-5 3 3 5-7"/></svg>'
            },
            {
                title: "Home Loan",
                enquiry: "Home Loan",
                description: "Clearer pathways for your next property decision.",
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z"/><path d="M8 21v-7h8v7"/></svg>'
            },
            {
                title: "Health Insurance",
                enquiry: "Health Insurance",
                description: "Protection conversations built around your needs.",
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 21s8-4.4 8-10.3A4.7 4.7 0 0 0 12 7a4.7 4.7 0 0 0-8 3.7C4 16.6 12 21 12 21Z"/><path d="M12 10v5m-2.5-2.5h5"/></svg>'
            },
            {
                title: "Investment Plans",
                enquiry: "Investment Plans",
                description: "Organised guidance for long-term financial growth.",
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5m0 14h16"/><path d="M6 15 10 9l3 3 5-6"/></svg>'
            }
        ],

        startHero() {

            setInterval(() => {
                this.headlineIndex =
                    (this.headlineIndex + 1)
                    % this.heroHeadlines.length;

                this.heroHeadline = this.heroHeadlines[this.headlineIndex];
            }, 4200);

        },


        /* =====================================================
           EMI
           ===================================================== */

        loanAmount: 2500000,

        rate: 9.5,

        tenure: 15,

        calculatorType: "Home Loan",


        get emi() {

            const principal =
                Number(this.loanAmount);

            const monthlyRate =
                Number(this.rate) / 12 / 100;

            const months =
                Number(this.tenure) * 12;

            if (
                principal <= 0 ||
                monthlyRate <= 0 ||
                months <= 0
            ) {
                return 0;
            }

            return (
                principal *
                monthlyRate *
                Math.pow(
                    1 + monthlyRate,
                    months
                )
            ) /
            (
                Math.pow(
                    1 + monthlyRate,
                    months
                ) - 1
            );

        },


        get totalInterest() {

            const months =
                Number(this.tenure) * 12;

            return (
                this.emi * months
            ) - Number(this.loanAmount);

        },


        get totalPayment() {
            return this.emi * Number(this.tenure) * 12;
        },


        get principalShare() {
            const total = this.totalPayment;

            if (total <= 0) {
                return 0;
            }

            return Math.round((Number(this.loanAmount) / total) * 100);
        },


        formatCurrency(value) {

            const number =
                Number(value) || 0;

            return new Intl.NumberFormat(
                "en-IN",
                {
                    style: "currency",
                    currency: "INR",
                    maximumFractionDigits: 0
                }
            ).format(number);

        },


        /* =====================================================
           MODALS
           ===================================================== */

        loanModal: false,

        insuranceModal: false,

        successModal: false,

        selectedService: "",

        loading: false,

        formError: "",

        eventId: "",


        form: {

            service: "",

            legal_name: "",

            mobile: "",

            email: "",

            loan_amount: "",

            loan_tenure: "",

            employment: "",

            message: ""

        },


        insurance: {

            legal_name: "",

            mobile: "",

            risk_type: "",

            medical_conditions: "",

            premium_budget: ""

        },


        openLoan(service) {

            this.selectedService = service;

            this.form.service = service;

            this.formError = "";

            this.loanModal = true;

        },


        openInsurance() {

            this.formError = "";

            this.insuranceModal = true;

        },


        resetState() {

            this.formError = "";

            this.loading = false;

        },


        /* =====================================================
           SUBMIT GENERAL FINANCIAL LEAD
           ===================================================== */

        async submitForm() {

            this.formError = "";

            this.loading = true;

            try {

                const response = await fetch(
                    "/submit-lead",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body: JSON.stringify({
                            ...this.form
                        })
                    }
                );


                const result =
                    await response.json();


                if (!response.ok || !result.success) {

                    this.formError =
                        result.errors
                        ? result.errors.join(" ")
                        : (
                            result.message ||
                            "Unable to submit enquiry."
                        );

                    this.loading = false;

                    return;

                }


                this.eventId =
                    result.event_id;

                this.loanModal = false;

                this.successModal = true;

                this.loading = false;


                this.form = {

                    service: "",

                    legal_name: "",

                    mobile: "",

                    email: "",

                    loan_amount: "",

                    loan_tenure: "",

                    employment: "",

                    message: ""

                };

            }

            catch (error) {

                console.error(error);

                this.formError =
                    "Network error. Please try again.";

                this.loading = false;

            }

        },


        /* =====================================================
           SUBMIT INSURANCE LEAD
           ===================================================== */

        async submitInsurance() {

            this.formError = "";

            this.loading = true;


            try {

                const response = await fetch(
                    "/submit-lead",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body: JSON.stringify({

                            service:
                                "Insurance",

                            legal_name:
                                this.insurance.legal_name,

                            mobile:
                                this.insurance.mobile,

                            risk_type:
                                this.insurance.risk_type,

                            medical_conditions:
                                this.insurance.medical_conditions,

                            premium_budget:
                                this.insurance.premium_budget

                        })

                    }
                );


                const result =
                    await response.json();


                if (!response.ok || !result.success) {

                    this.formError =
                        result.errors
                        ? result.errors.join(" ")
                        : (
                            result.message ||
                            "Unable to submit enquiry."
                        );

                    this.loading = false;

                    return;

                }


                this.eventId =
                    result.event_id;

                this.insuranceModal = false;

                this.successModal = true;

                this.loading = false;


                this.insurance = {

                    legal_name: "",

                    mobile: "",

                    risk_type: "",

                    medical_conditions: "",

                    premium_budget: ""

                };

            }

            catch (error) {

                console.error(error);

                this.formError =
                    "Network error. Please try again.";

                this.loading = false;

            }

        }

    };

}

</script>


</body>
</html>
"""


# ============================================================
# MAIN PAGE
# ============================================================

@app.get("/")
def home():
    return render_template_string(HTML)


# ============================================================
# DEVELOPMENT ENTRY POINT
# ============================================================

if __name__ == "__main__":

    # For local development.
    #
    # Production deployment should use a production WSGI
    # server rather than Flask's development server.

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )