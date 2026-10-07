from flask import Flask, Response, request, jsonify
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
# ASK FINANCIAL SERVICES
# Single-file Flask + Inline HTML + Tailwind + Alpine.js
# ============================================================

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["BRAND_NAME"] = "ASK Financial Services"

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


# ============================================================
# MAIN PAGE
# ============================================================

# ============================================================
# EMBEDDED FRONTEND
# ============================================================

INDEX_HTML = '''
<!DOCTYPE html><html lang="en" data-fh-contract="1"><head><meta data-gneiss-csp http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'none'; object-src 'none'; base-uri 'none'; img-src 'self' https: data: blob:; style-src 'self' 'unsafe-inline' https:; font-src 'self' https: data:; media-src 'self' https: blob:; frame-src https://www.youtube.com https://www.youtube-nocookie.com https://youtu.be https://player.vimeo.com https://vimeo.com; connect-src 'none'; form-action https:"><meta data-gneiss-publish-meta name="robots" content="noindex"><meta property="og:title" content="ASK Group Financial Services — Finance made clearer"><meta property="og:type" content="website"><meta property="og:image" content="https://new.express.adobe.com/webpage/urn:aaid:sc:AP:578508c2-cc34-4e11-9b61-5e2755dc7d1f/resources/1791114284643?asset_id=rendition"><meta property="og:url" content="https://new.express.adobe.com/webpage/urn:aaid:sc:AP:578508c2-cc34-4e11-9b61-5e2755dc7d1f"><meta property="og:image:width" content="1024"><meta property="og:image:height" content="512"><meta property="og:site_name" content="Adobe Express"><meta property="og:description" content="See the story"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="ASK Group Financial Services — Finance made clearer"><meta name="twitter:image:src" content="https://new.express.adobe.com/webpage/urn:aaid:sc:AP:578508c2-cc34-4e11-9b61-5e2755dc7d1f/resources/1791114284643?asset_id=rendition"><meta name="twitter:description" content="See the story"><link rel="apple-touch-icon" href="https://new.express.adobe.com/webpage/urn:aaid:sc:AP:578508c2-cc34-4e11-9b61-5e2755dc7d1f/resources/1791114284643?asset_id=rendition"><link rel="shortcut icon" href="/static/favicon.ico"><style data-gneiss-publish-scroll>html{scroll-behavior:smooth}@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}</style>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ASK Group Financial Services — Finance made clearer</title>
<link rel="stylesheet" href="https://use.typekit.net/dop0nop.css"><style id="ask-brand-theme">
  :root {
    --bg: #f5f1e7;
    --surface: #fffdf8;
    --text: #31351d;
    --fg: #687052;
    --accent: #7b7e1f;
    --muted: #9b9b78;
    --link: #697019;
    --link-hover: #4f5512;
    --primary: #6f741b;
    --border: #dedcc8;
    --surface-strong: #30351c;
    --hero-glow: #7b7e1f;
    --text-display-accent: #70751b;
    --text-on-accent: #fffdf8;
  }
  body { background: var(--bg); color: var(--text); }
  nav { background: rgba(255,253,248,.94); backdrop-filter: blur(14px); }
  .nav-logo-mark { width: 54px; height: 48px; background: transparent url('/static/ask-logo.png') center -22px / 92px 92px no-repeat; border-radius: 0; }
  .nav-logo-mark svg { display: none; }
  .nav-logo-text { color: var(--text); letter-spacing: .02em; }
  .nav-logo-text span { color: var(--accent); }
  .hero { background: linear-gradient(135deg, #fffdf8 0%, #f5f1e7 100%); }
  .hero-img-wrap { box-shadow: 0 24px 64px rgba(77, 82, 18, .18); }
  .service-card, .contact-card, .partner-pill, .testi-card { border-color: var(--border); background: var(--surface); }
  .btn-primary { background: var(--primary); border-color: var(--primary); }
  .btn-primary:hover { background: #555b12; border-color: #555b12; }
  .section-heading em, .hero-title em { color: var(--accent); }
  .footer { background: var(--surface-strong); }
  @media (max-width: 600px) { .nav-logo-mark { width: 46px; background-size: 80px 80px; background-position: center -19px; } }
</style><style id="ask-service-links">.service-card { cursor: pointer; } .service-card:focus-visible { outline: 3px solid var(--accent); outline-offset: 4px; }</style><style id="ask-final-polish">.service-card { color: inherit; text-decoration: none; } .service-card h3, .service-card p, .service-card .service-tag { text-decoration: none; }</style></head>
<body>


<style id="page-theme">
:root {
  --bg:                    #f5f7fa;
  --surface:               #ffffff;
  --text:                  #0d1b2a;
  --fg:                    #4a5568;
  --accent:                #7b7e1f;
  --muted:                 #9aa5b4;
  --link:                  #6f741b;
  --link-hover:            #7b7e1f;
  --text-on-surface-strong:#e8edf4;
  --link-on-strong:        #a8c4e8;
  --link-hover-on-strong:  #7b7e1f;
  --primary:               #6f741b;
  --border:                #d6dce8;
  --text-on-accent:        #ffffff;
  --text-display-accent:   #7b7e1f;
  --surface-strong:        #0d1b2a;
  --hero-glow:             #6f741b;
  --chart-1:               #6f741b;
  --chart-2:               #7b7e1f;
}
</style>

<style>
:root {
  --text-xs:      0.75rem;
  --text-sm:      0.8125rem;
  --text-base:    1rem;
  --text-lg:      1.125rem;
  --text-xl:      1.25rem;
  --text-2xl:     1.5rem;
  --text-3xl:     1.875rem;
  --text-4xl:     2.25rem;
  --text-display: 3.5rem;
  --duration-fast:  150ms;
  --duration-base:  250ms;
  --duration-slow:  400ms;
  --duration-xslow: 600ms;
  --nav-height: 64px;
  --font-display: playfair-display, georgia, serif;
  --font-body: acumin-pro, helvetica-neue, arial, sans-serif;
  --radius-sm:    6px;
  --radius-md:    12px;
  --radius-lg:    20px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { font-size: 16px; }

body {
  font-family: var(--font-body);
  font-size: var(--text-base);
  line-height: 1.65;
  letter-spacing: 0.01em;
  word-spacing: 0.16em;
  background-color: var(--bg);
  color: var(--text);
  overflow-x: hidden;
}

h1, h2, h3, h4 {
  font-family: var(--font-display);
  line-height: 1.1;
  color: var(--text);
}

h1 { font-size: clamp(2.2rem, 5vw, var(--text-display)); }
h2 { font-size: clamp(1.6rem, 3.5vw, var(--text-4xl)); }
h3 { font-size: var(--text-xl); }
h4 { font-size: var(--text-lg); }

p { font-size: var(--text-base); line-height: 1.7; }
p + p { margin-top: 2em; }

a { color: var(--link); text-decoration: underline; text-underline-offset: 0.15em; }
a:hover { color: var(--link-hover); }

.container {
  width: 100%;
  max-width: 1280px;
  margin-inline: auto;
  padding-inline: clamp(1rem, 5vw, 3.5rem);
}

.eyebrow {
  font-family: var(--font-body);
  font-size: var(--text-sm);
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.75rem;
  border-radius: var(--radius-sm);
  font-family: var(--font-body);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  border: 2px solid transparent;
  transition: transform var(--duration-fast) ease,
              background-color var(--duration-base) ease,
              box-shadow var(--duration-base) ease,
              color var(--duration-base) ease;
  min-height: 48px;
}
.btn:active { transform: scale(0.97); }

.btn-primary {
  background-color: var(--primary);
  color: var(--text-on-accent);
  border-color: var(--primary);
}
.btn-primary:hover {
  background-color: var(--accent);
  border-color: var(--accent);
  color: var(--text-on-accent);
  box-shadow: 0 6px 24px color-mix(in srgb, var(--accent) 35%, transparent);
  text-decoration: none;
}

.btn-outline {
  background-color: transparent;
  color: var(--primary);
  border-color: var(--primary);
}
.btn-outline:hover {
  background-color: var(--primary);
  color: var(--text-on-accent);
  text-decoration: none;
}

:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 3px;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}

@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(1.5rem); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes marquee-scroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
@keyframes float-y {
  0%, 100% { transform: translateY(0); }
  50%       { transform: translateY(-10px); }
}
</style>


<style>
nav {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 1000;
  height: var(--nav-height);
  background-color: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 2px 16px color-mix(in srgb, var(--text) 6%, transparent);
}

.nav-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
}

.nav-logo {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
}
.nav-logo-mark {
  width: 36px; height: 36px;
  background-color: var(--primary);
  border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
}
.nav-logo-text {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text);
  text-decoration: none;
}
.nav-logo-text span { color: var(--accent); }

.nav-desktop {
  display: flex;
  align-items: center;
  gap: 2rem;
}
.nav-desktop a {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--fg);
  text-decoration: none;
  letter-spacing: 0.04em;
  transition: color var(--duration-fast) ease;
  min-height: 24px;
  padding: 0.5rem 0;
  display: inline-block;
}
.nav-desktop a:hover { color: var(--accent); }

.nav-mobile { display: none; list-style: none; }
.nav-toggle {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.5rem;
  color: var(--text);
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 44px; min-height: 44px;
}
.nav-toggle svg { pointer-events: none; }
details.nav-mobile .nav-drawer { display: none; }
details.nav-mobile[open] .nav-drawer {
  display: flex;
  flex-direction: column;
  position: absolute;
  top: var(--nav-height);
  left: 0; right: 0;
  background-color: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 1rem 1.5rem 1.5rem;
  gap: 1rem;
  box-shadow: 0 8px 24px color-mix(in srgb, var(--text) 10%, transparent);
}
.nav-drawer a {
  font-size: var(--text-base);
  color: var(--text);
  text-decoration: none;
  font-weight: 500;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}
.nav-drawer a:last-of-type { border-bottom: none; }

@media (max-width: 767px) {
  .nav-desktop { display: none; }
  .nav-mobile  { display: block; }
}
</style>

<nav aria-label="Primary navigation" data-name="Primary nav" analytics-name="header" data-fh-id="fh-1" style="">
  <div class="container nav-inner" data-fh-id="fh-2" data-name="Container" analytics-name="div" data-fh-layout="split">
    <a class="nav-logo" data-name="Logo" analytics-name="button" data-fh-id="fh-3" data-fh-side="image" data-fh-layout="split" href="#">
      <div class="nav-logo-mark" aria-hidden="true" data-fh-id="fh-4" data-name="Nav logo mark" analytics-name="div" data-fh-side="image">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M3 14 L7 8 L11 11 L15 5 L17 7" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
        </svg>
      </div>
      <span class="nav-logo-text" data-fh-id="fh-5" data-name="Nav logo text" data-fh-side="text">ASK<span data-fh-id="fh-6" data-name="Text"> Group Financial Services</span></span>
    </a>

    <div class="nav-desktop" data-name="Desktop nav links" analytics-name="div-container" data-fh-id="fh-7" data-fh-side="text">
      <a data-name="Services link" analytics-name="button" data-fh-id="fh-8" href="#services">Services</a>
      <a data-name="Why us link" analytics-name="button" data-fh-id="fh-9" href="#why-us">Why Us</a>
      <a data-name="Products link" analytics-name="button" data-fh-id="fh-10" href="#products">Products</a>
      <a data-name="Partners link" analytics-name="button" data-fh-id="fh-11" href="#partners">Partners</a>
      <a class="btn btn-primary __freeform_button__" style="padding:0.5rem 1.25rem; min-height:40px;" data-name="Nav CTA" analytics-name="button" data-fh-id="fh-12" href="#contact">Start a conversation</a>
    </div>

    <details class="nav-mobile" data-name="Mobile nav" analytics-name="header" data-fh-id="fh-13">
      <summary class="nav-toggle" aria-label="Open navigation menu" data-fh-id="fh-14" data-name="Nav toggle">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
        </svg>
      </summary>
      <div class="nav-drawer" data-fh-id="fh-15" data-name="Nav drawer" analytics-name="div" data-fh-collection="nav-drawer">
        <a data-fh-id="fh-16" data-name="Link" data-fh-item="" data-fh-field="link" href="#services">Services</a>
        <a data-fh-id="fh-17" data-name="Link" data-fh-item="" data-fh-field="link" href="#why-us">Why Us</a>
        <a data-fh-id="fh-18" data-name="Link" data-fh-item="" data-fh-field="link" href="#products">Products</a>
        <a data-fh-id="fh-19" data-name="Link" data-fh-item="" data-fh-item-template="" data-fh-field="link" href="#partners">Partners</a>
        <a class="btn btn-primary __freeform_button__" style="text-align:center; justify-content:center;" data-fh-id="fh-20" data-name="Btn" href="#contact">Start a conversation</a>
      </div>
    </details>
  </div>
</nav>


<style>
.hero {
  padding-top: calc(var(--nav-height) + 4rem);
  padding-bottom: 5rem;
  background-color: var(--surface);
  position: relative;
  overflow: hidden;
}
.hero::before {
  content: '';
  position: absolute;
  top: -120px; right: -80px;
  width: 600px; height: 600px;
  background: radial-gradient(circle, color-mix(in srgb, var(--hero-glow) 12%, transparent) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}
.hero::after {
  content: '';
  position: absolute;
  bottom: -60px; left: -60px;
  width: 360px; height: 360px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent) 8%, transparent) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

.hero-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4rem;
  align-items: center;
  position: relative;
  z-index: 1;
}

.hero-content { animation: fade-in-up var(--duration-slow) ease both; }

.hero-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
}
.hero-eyebrow-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background-color: var(--accent);
}

.hero-title {
  margin-bottom: 1.25rem;
  color: var(--text);
}
.hero-title em {
  font-style: normal;
  color: var(--text-display-accent);
}

.hero-desc {
  color: var(--fg);
  font-size: var(--text-lg);
  max-width: 48ch;
  margin-bottom: 2rem;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.hero-trust {
  margin-top: 2.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}
.hero-trust-avatars {
  display: flex;
}
.hero-trust-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: 2px solid var(--surface);
  background-color: var(--primary);
  display: flex; align-items: center; justify-content: center;
  font-size: var(--text-xs);
  color: var(--text-on-accent);
  font-weight: 700;
  margin-left: -8px;
}
.hero-trust-avatar:first-child { margin-left: 0; }
.hero-trust-text { font-size: var(--text-sm); color: var(--fg); }
.hero-trust-text strong { color: var(--text); }

.hero-visual {
  position: relative;
  animation: fade-in var(--duration-xslow) ease both 0.2s;
}
.hero-img-wrap {
  border-radius: var(--radius-lg);
  overflow: hidden;
  aspect-ratio: 5/4;
  box-shadow: 0 24px 64px color-mix(in srgb, var(--primary) 18%, transparent);
}
.hero-img-wrap img {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
}

.hero-stat-card {
  position: absolute;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 0.875rem 1.25rem;
  box-shadow: 0 8px 32px color-mix(in srgb, var(--text) 10%, transparent);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  animation: float-y 4s ease-in-out infinite;
}
.hero-stat-card:nth-child(2) {
  bottom: 2rem; left: -2rem;
  animation-delay: 0s;
}
.hero-stat-card:nth-child(3) {
  top: 2rem; right: -2rem;
  animation-delay: 2s;
}
.hero-stat-icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-sm);
  background-color: color-mix(in srgb, var(--primary) 10%, transparent);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.hero-stat-num {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.hero-stat-label { font-size: var(--text-xs); color: var(--fg); }

@media (max-width: 900px) {
  .hero-grid { grid-template-columns: 1fr; gap: 2.5rem; }
  .hero-visual { display: none; }
}
@media (max-width: 600px) {
  .hero { padding-top: calc(var(--nav-height) + 2rem); padding-bottom: 3rem; }
  .hero-title { font-size: 2rem; }
}
</style>

<section class="hero" aria-label="Hero" data-name="Hero section" analytics-name="hero section" data-fh-id="fh-21">
  <div class="container hero-grid" data-fh-id="fh-22" data-name="Container" analytics-name="div">
    <div class="hero-content" data-name="Hero content" analytics-name="2-column section" data-fh-id="fh-23">
      <div class="hero-eyebrow" data-name="Hero eyebrow" analytics-name="text" data-fh-id="fh-24">
        <span class="hero-eyebrow-dot" aria-hidden="true" data-fh-id="fh-25" data-name="Hero eyebrow dot"></span>
        <span class="eyebrow" data-fh-id="fh-26" data-name="Eyebrow">Trusted financial guidance, made personal</span>
      </div>
      <h1 class="hero-title" data-name="Hero title" analytics-name="text" data-fh-id="fh-27">
        Plan with confidence.<br><em>Grow</em> what matters most.
      </h1>
      <p class="hero-desc" data-name="Hero description" analytics-name="text" data-fh-id="fh-28">
        ASK Group Financial Services connects you with the right loans, insurance, investments, and credit guidance — with clear advice and no hidden surprises.
      </p>
      <div class="hero-actions" data-name="Hero CTAs" analytics-name="div-container" data-fh-id="fh-29">
        <a class="btn btn-primary __freeform_button__" data-name="Primary CTA" analytics-name="button" data-fh-id="fh-30" href="#contact">Reach Us</a>
      </div>
      <div class="hero-trust" data-name="Trust signal" analytics-name="div-container" data-fh-id="fh-32">
        <div class="hero-trust-avatars" aria-hidden="true" data-fh-id="fh-33" data-name="Hero trust avatars" analytics-name="div" data-fh-collection="hero-trust-avatars">
          <div class="hero-trust-avatar" data-fh-id="fh-34" data-name="Hero trust avatar" analytics-name="div" data-fh-item="" data-fh-field="hero-trust-avatar">AK</div>
          <div class="hero-trust-avatar" data-fh-id="fh-35" data-name="Hero trust avatar" analytics-name="div" data-fh-item="" data-fh-field="hero-trust-avatar">PR</div>
          <div class="hero-trust-avatar" data-fh-id="fh-36" data-name="Hero trust avatar" analytics-name="div" data-fh-item="" data-fh-field="hero-trust-avatar">SM</div>
          <div class="hero-trust-avatar" data-fh-id="fh-37" data-name="Hero trust avatar" analytics-name="div" data-fh-item="" data-fh-item-template="" data-fh-field="hero-trust-avatar">RJ</div>
        </div>
        <p class="hero-trust-text" data-fh-id="fh-38" data-name="Hero trust text"><strong>12,000+ clients</strong> trust us for smarter finance decisions</p>
      </div>
    </div>

    <div class="hero-visual" aria-hidden="true" data-name="Hero visual" analytics-name="image" data-fh-id="fh-39">
      <div class="hero-img-wrap" data-fh-id="fh-40" data-name="Hero img wrap" analytics-name="div">
        <img alt="Fresh finance team meeting image used in the homepage hero" data-name="Hero image" analytics-name="image" data-fh-id="fh-41" src="/static/fresh-hero.jpg">
      </div>
      <div class="hero-stat-card" data-name="Stat card 1" analytics-name="card" data-fh-id="fh-42" data-fh-layout="split">
        <div class="hero-stat-icon" data-fh-id="fh-43" data-name="Hero stat icon" analytics-name="div" data-fh-side="image">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="var(--primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
          </svg>
        </div>
        <div data-fh-id="fh-44" data-name="Container" analytics-name="div" data-fh-side="text">
          <div class="hero-stat-num" data-fh-id="fh-45" data-name="Hero stat num" analytics-name="div">40+</div>
          <div class="hero-stat-label" data-fh-id="fh-46" data-name="Hero stat label" analytics-name="div">Bank Partners</div>
        </div>
      </div>
      <div class="hero-stat-card" data-name="Stat card 2" analytics-name="card" data-fh-id="fh-47" data-fh-layout="split">
        <div class="hero-stat-icon" data-fh-id="fh-48" data-name="Hero stat icon" analytics-name="div" data-fh-side="image">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
          </svg>
        </div>
        <div data-fh-id="fh-49" data-name="Container" analytics-name="div" data-fh-side="text">
          <div class="hero-stat-num" data-fh-id="fh-50" data-name="Hero stat num" analytics-name="div">98%</div>
          <div class="hero-stat-label" data-fh-id="fh-51" data-name="Hero stat label" analytics-name="div">Approval Rate</div>
        </div>
      </div>
    </div>
  </div>
</section>


<style>
.services {
  padding: 5rem 0;
  background-color: var(--bg);
}
.services-header {
  max-width: 52ch;
  margin-bottom: 3rem;
  animation: fade-in-up var(--duration-slow) ease both;
  animation-timeline: view();
  animation-range: entry 0% entry 30%;
}
.services-header h2 { margin-top: 0.5rem; margin-bottom: 1rem; }
.services-header p { color: var(--fg); }

.services-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}

.service-card {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 2rem 1.75rem;
  position: relative;
  overflow: hidden;
  transition: transform var(--duration-base) ease,
              box-shadow var(--duration-base) ease,
              border-color var(--duration-base) ease;
  animation: fade-in-up var(--duration-slow) ease both;
  animation-timeline: view();
  animation-range: entry 0% entry 35%;
}
.service-card::before {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--primary), var(--accent));
  transform: scaleX(0);
  transform-origin: left;
  transition: transform var(--duration-base) ease;
}
.service-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 16px 48px color-mix(in srgb, var(--primary) 12%, transparent);
  border-color: color-mix(in srgb, var(--primary) 30%, transparent);
}
.service-card:hover::before { transform: scaleX(1); }

.service-icon {
  width: 52px; height: 52px;
  border-radius: var(--radius-sm);
  background-color: color-mix(in srgb, var(--primary) 10%, transparent);
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 1.25rem;
  transition: background-color var(--duration-base) ease;
}
.service-card:hover .service-icon {
  background-color: color-mix(in srgb, var(--accent) 12%, transparent);
}
.service-icon svg { flex-shrink: 0; }

.service-card h3 { margin-bottom: 0.5rem; font-size: var(--text-xl); }
.service-card p  { color: var(--fg); font-size: var(--text-sm); line-height: 1.65; }

.service-tag {
  display: inline-block;
  margin-top: 1.25rem;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--primary);
  background-color: color-mix(in srgb, var(--primary) 10%, transparent);
  padding: 0.3rem 0.7rem;
  border-radius: 100px;
}

@media (max-width: 900px) {
  .services-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 560px) {
  .services-grid { grid-template-columns: 1fr; }
}
</style>

<section class="services" id="services" aria-label="Services" data-name="Services section" analytics-name="section" data-fh-id="fh-52">
  <div class="container" data-fh-id="fh-53" data-name="Container" analytics-name="div">
    <div class="services-header" data-name="Services header" analytics-name="div-container" data-fh-id="fh-54">
      <span class="eyebrow" data-name="Services eyebrow" analytics-name="text" data-fh-id="fh-55">What We Offer</span>
      <h2 data-name="Services heading" analytics-name="text" data-fh-id="fh-56">Financial products that work as hard as you do</h2>
      <p data-name="Services description" analytics-name="text" data-fh-id="fh-57">From first-time home buyers to seasoned investors — our DSA network covers every stage of your financial journey.</p>
    </div>

    <div class="services-grid" data-name="Services grid" analytics-name="div-container" data-fh-id="fh-58">

      <a class="service-card" href="#contact" data-name="Home Loan card" analytics-name="card" data-fh-id="fh-59">
        <div class="service-icon" aria-hidden="true" data-fh-id="fh-60" data-name="Service icon" analytics-name="div">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
            <polyline points="9 22 9 12 15 12 15 22" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></polyline>
          </svg>
        </div>
        <h3 data-name="Home Loan title" analytics-name="text" data-fh-id="fh-61">Home Loans</h3>
        <p data-name="Home Loan desc" analytics-name="text" data-fh-id="fh-62">Rates from 8.4% p.a. with doorstep processing, quick sanctions, and flexible tenures up to 30 years.</p>
        <span class="service-tag" data-fh-id="fh-63" data-name="Service tag">Up to ₹10 Cr</span>
      </a>

      <a class="service-card" href="#contact" data-name="Personal Loan card" analytics-name="card" data-fh-id="fh-64">
        <div class="service-icon" aria-hidden="true" data-fh-id="fh-65" data-name="Service icon" analytics-name="div">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <rect x="2" y="5" width="20" height="14" rx="2" stroke="var(--primary)" stroke-width="1.8"></rect>
            <line x1="2" y1="10" x2="22" y2="10" stroke="var(--primary)" stroke-width="1.8"></line>
          </svg>
        </div>
        <h3 data-name="Personal Loan title" analytics-name="text" data-fh-id="fh-66">Personal Loans</h3>
        <p data-name="Personal Loan desc" analytics-name="text" data-fh-id="fh-67">Paperless approvals in 24 hours, zero collateral required, and competitive rates starting 10.5% p.a.</p>
        <span class="service-tag" data-fh-id="fh-68" data-name="Service tag">Up to ₹50 Lakh</span>
      </a>

      <a class="service-card" href="#contact" data-name="Business Loan card" analytics-name="card" data-fh-id="fh-69">
        <div class="service-icon" aria-hidden="true" data-fh-id="fh-70" data-name="Service icon" analytics-name="div">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" stroke="var(--primary)" stroke-width="1.8"></path>
          </svg>
        </div>
        <h3 data-name="Business Loan title" analytics-name="text" data-fh-id="fh-71">Business Loans</h3>
        <p data-name="Business Loan desc" analytics-name="text" data-fh-id="fh-72">Collateral-free working capital and term loans for MSMEs, with repayment schedules tailored to your cash flow.</p>
        <span class="service-tag" data-fh-id="fh-73" data-name="Service tag">Up to ₹2 Cr</span>
      </a>

      <a class="service-card" href="#contact" data-name="Insurance card" analytics-name="card" data-fh-id="fh-74">
        <div class="service-icon" aria-hidden="true" data-fh-id="fh-75" data-name="Service icon" analytics-name="div">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
          </svg>
        </div>
        <h3 data-name="Insurance title" analytics-name="text" data-fh-id="fh-76">Life &amp; Health Insurance</h3>
        <p data-name="Insurance desc" analytics-name="text" data-fh-id="fh-77">Compare 30+ plans instantly. Term, ULIP, health floaters, and critical illness covers — all in one place.</p>
        <span class="service-tag" data-fh-id="fh-78" data-name="Service tag">Starts ₹499/mo</span>
      </a>

      <a class="service-card" href="#contact" data-name="Investment card" analytics-name="card" data-fh-id="fh-79">
        <div class="service-icon" aria-hidden="true" data-fh-id="fh-80" data-name="Service icon" analytics-name="div">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></polyline>
            <polyline points="17 6 23 6 23 12" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></polyline>
          </svg>
        </div>
        <h3 data-name="Investment title" analytics-name="text" data-fh-id="fh-81">Investments &amp; MFs</h3>
        <p data-name="Investment desc" analytics-name="text" data-fh-id="fh-82">SIPs from ₹500/month, FDs, bonds, and equity guidance — structured around your risk appetite and goals.</p>
        <span class="service-tag" data-fh-id="fh-83" data-name="Service tag">Wealth planning</span>
      </a>

      <a class="service-card" href="#contact" data-name="Credit Score card" analytics-name="card" data-fh-id="fh-84">
        <div class="service-icon" aria-hidden="true" data-fh-id="fh-85" data-name="Service icon" analytics-name="div">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="var(--primary)" stroke-width="1.8"></circle>
            <path d="M12 8v4l3 3" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round"></path>
          </svg>
        </div>
        <h3 data-name="Credit Score title" analytics-name="text" data-fh-id="fh-86">Credit Score Advisory</h3>
        <p data-name="Credit Score desc" analytics-name="text" data-fh-id="fh-87">Free CIBIL check, score improvement roadmap, and dispute resolution support to unlock better loan terms.</p>
        <span class="service-tag" data-fh-id="fh-88" data-name="Service tag">Free check</span>
      </a>

    </div>
  </div>
</section>


<style>
.why-us {
  padding: 5rem 0;
  background-color: var(--surface-strong);
  position: relative;
  overflow: hidden;
}
.why-us::before {
  content: '';
  position: absolute;
  top: -80px; right: -100px;
  width: 480px; height: 480px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent) 8%, transparent), transparent 65%);
  pointer-events: none;
}

.why-us-grid {
  display: grid;
  grid-template-columns: 5fr 7fr;
  gap: 5rem;
  align-items: center;
}

.why-us-image {
  border-radius: var(--radius-lg);
  overflow: hidden;
  aspect-ratio: 4/5;
  box-shadow: 0 32px 80px color-mix(in srgb, var(--text) 40%, transparent);
  animation: fade-in-up var(--duration-slow) ease both;
  animation-timeline: view();
  animation-range: entry 0% entry 30%;
}
.why-us-image img { width: 100%; height: 100%; object-fit: cover; display: block; }

.why-us-content { animation: fade-in-up var(--duration-slow) ease both 0.15s;
  animation-timeline: view();
  animation-range: entry 0% entry 30%;
}
.why-us-content .eyebrow { color: var(--accent); }
.why-us-content h2 { color: var(--text-on-surface-strong); margin-top: 0.5rem; margin-bottom: 1rem; }
.why-us-content > p { color: var(--text-on-surface-strong); opacity: 0.8; margin-bottom: 2.5rem; }

.why-list { list-style: none; display: flex; flex-direction: column; gap: 1.5rem; }
.why-item {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}
.why-item-icon {
  width: 44px; height: 44px;
  border-radius: var(--radius-sm);
  background-color: color-mix(in srgb, var(--accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.why-item-body h4 { color: var(--text-on-surface-strong); margin-bottom: 0.25rem; font-size: var(--text-base); font-weight: 600; }
.why-item-body p  { color: var(--text-on-surface-strong); opacity: 0.7; font-size: var(--text-sm); line-height: 1.6; }

footer { color: var(--text-on-surface-strong); --link: var(--link-on-strong); --link-hover: var(--link-hover-on-strong); }
footer a { color: var(--link); }
footer a:hover { color: var(--link-hover); }

@media (max-width: 900px) {
  .why-us-grid { grid-template-columns: 1fr; gap: 2.5rem; }
  .why-us-image { aspect-ratio: 16/9; }
}
</style>

<section class="why-us" id="why-us" aria-label="Why choose ASK" data-name="Why us section" analytics-name="2-column section" data-fh-id="fh-89">
  <div class="container why-us-grid" data-fh-id="fh-90" data-name="Container" analytics-name="div" data-fh-layout="split">
    <div class="why-us-image" data-name="Why us image" analytics-name="image" data-fh-id="fh-91" data-fh-side="image">
      <img alt="Fresh finance collaboration image used in the company section" data-name="Why us photo" analytics-name="image" data-fh-id="fh-92" src="/static/fresh-story.jpg">
    </div>
    <div class="why-us-content" data-name="Why us content" analytics-name="div-container" data-fh-id="fh-93" data-fh-side="text">
      <span class="eyebrow" data-name="Why us eyebrow" analytics-name="text" data-fh-id="fh-94">Why choose ASK</span>
      <h2 data-name="Why us heading" analytics-name="text" data-fh-id="fh-95">The sharper way to navigate Indian finance</h2>
      <p data-name="Why us description" analytics-name="text" data-fh-id="fh-96">We cut through complexity, negotiate better rates on your behalf, and handle paperwork end-to-end.</p>
      <ul class="why-list" data-name="Why us list" analytics-name="div-container" data-fh-id="fh-97" data-fh-collection="why-us-list">
        <li class="why-item" data-name="Why item 1" analytics-name="card" data-fh-id="fh-98" data-fh-item="" data-fh-layout="split">
          <div class="why-item-icon" aria-hidden="true" data-fh-id="fh-99" data-name="Why item icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"></path>
              <polyline points="22 4 12 14.01 9 11.01" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>
            </svg>
          </div>
          <div class="why-item-body" data-fh-id="fh-100" data-name="Why item body" analytics-name="div" data-fh-side="text">
            <h4 data-name="Why item 1 title" analytics-name="text" data-fh-id="fh-101" data-fh-field="why-item-1-title">Zero brokerage, ever</h4>
            <p data-name="Why item 1 desc" analytics-name="text" data-fh-id="fh-102" data-fh-field="why-item-1-desc">Our fees come from lenders — you pay nothing extra for our guidance or processing support.</p>
          </div>
        </li>
        <li class="why-item" data-name="Why item 2" analytics-name="card" data-fh-id="fh-103" data-fh-item="" data-fh-layout="split">
          <div class="why-item-icon" aria-hidden="true" data-fh-id="fh-104" data-name="Why item icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="var(--accent)" stroke-width="2"></circle>
              <polyline points="12 6 12 12 16 14" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"></polyline>
            </svg>
          </div>
          <div class="why-item-body" data-fh-id="fh-105" data-name="Why item body" analytics-name="div" data-fh-side="text">
            <h4 data-name="Why item 2 title" analytics-name="text" data-fh-id="fh-106" data-fh-field="why-item-2-title">Decisions in 48 hours</h4>
            <p data-name="Why item 2 desc" analytics-name="text" data-fh-id="fh-107" data-fh-field="why-item-2-desc">From document submission to in-principle approval — our digital-first process has no unnecessary delays.</p>
          </div>
        </li>
        <li class="why-item" data-name="Why item 3" analytics-name="card" data-fh-id="fh-108" data-fh-item="" data-fh-layout="split">
          <div class="why-item-icon" aria-hidden="true" data-fh-id="fh-109" data-name="Why item icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"></path>
              <circle cx="9" cy="7" r="4" stroke="var(--accent)" stroke-width="2"></circle>
              <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"></path>
            </svg>
          </div>
          <div class="why-item-body" data-fh-id="fh-110" data-name="Why item body" analytics-name="div" data-fh-side="text">
            <h4 data-name="Why item 3 title" analytics-name="text" data-fh-id="fh-111" data-fh-field="why-item-3-title">Dedicated relationship manager</h4>
            <p data-name="Why item 3 desc" analytics-name="text" data-fh-id="fh-112" data-fh-field="why-item-3-desc">One point of contact through your entire application — no call centers, no repeating your story.</p>
          </div>
        </li>
        <li class="why-item" data-name="Why item 4" analytics-name="card" data-fh-id="fh-113" data-fh-item="" data-fh-item-template="" data-fh-layout="split">
          <div class="why-item-icon" aria-hidden="true" data-fh-id="fh-114" data-name="Why item icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <rect x="2" y="3" width="20" height="14" rx="2" stroke="var(--accent)" stroke-width="2"></rect>
              <path d="M8 21h8M12 17v4" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"></path>
            </svg>
          </div>
          <div class="why-item-body" data-fh-id="fh-115" data-name="Why item body" analytics-name="div" data-fh-side="text">
            <h4 data-name="Why item 4 title" analytics-name="text" data-fh-id="fh-116" data-fh-field="why-item-4-title">Live application tracking</h4>
            <p data-name="Why item 4 desc" analytics-name="text" data-fh-id="fh-117" data-fh-field="why-item-4-desc">SMS and WhatsApp updates at every stage — no chasing banks, no guessing where your file is.</p>
          </div>
        </li>
      </ul>
    </div>
  </div>
</section>


<style>
.partners {
  padding: 4.5rem 0;
  background-color: var(--bg);
}
.partners-header {
  text-align: center;
  max-width: 52ch;
  margin: 0 auto 3rem;
}
.partners-header h2 { margin-top: 0.5rem; }
.partners-header p  { color: var(--fg); margin-top: 0.75rem; }

.marquee-wrap {
  overflow: hidden;
  position: relative;
}
.marquee-wrap::before,
.marquee-wrap::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0;
  width: 80px;
  z-index: 2;
  pointer-events: none;
}
.marquee-wrap::before { left: 0; background: linear-gradient(to right, var(--bg), transparent); }
.marquee-wrap::after  { right: 0; background: linear-gradient(to left,  var(--bg), transparent); }

.marquee-track {
  display: flex;
  gap: 1.5rem;
  animation: marquee-scroll 28s linear infinite;
  width: max-content;
}
.marquee-track:hover,
.marquee-track:focus-within { animation-play-state: paused; }

.partner-pill {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 100px;
  padding: 0.625rem 1.25rem;
  white-space: nowrap;
  transition: border-color var(--duration-base) ease, box-shadow var(--duration-base) ease;
  min-height: 48px;
}
.partner-pill:hover {
  border-color: var(--accent);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--accent) 15%, transparent);
}
.partner-pill-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background-color: var(--primary);
  flex-shrink: 0;
}
.partner-pill span {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
}

.partners-cta {
  text-align: center;
  margin-top: 2.5rem;
}
.partners-cta p { color: var(--fg); font-size: var(--text-sm); margin-bottom: 1rem; }
</style>

<section class="partners" id="partners" aria-label="Partner banks" data-name="Partners section" analytics-name="section" data-fh-id="fh-118">
  <div class="container" data-fh-id="fh-119" data-name="Container" analytics-name="div">
    <div class="partners-header" data-name="Partners header" analytics-name="div-container" data-fh-id="fh-120">
      <span class="eyebrow" data-name="Partners eyebrow" analytics-name="text" data-fh-id="fh-121">Our Banking Network</span>
      <h2 data-name="Partners heading" analytics-name="text" data-fh-id="fh-122">40+ partners, one seamless process</h2>
      <p data-name="Partners description" analytics-name="text" data-fh-id="fh-123">We've built direct relationships with India's leading lenders so you get the best rate, every time.</p>
    </div>

    <div class="marquee-wrap" aria-label="Scrolling partner bank list" data-name="Partner marquee" analytics-name="animated carousel" data-fh-id="fh-124">
      <div class="marquee-track" data-name="Marquee track" analytics-name="div-container" data-fh-id="fh-125">
        <div class="partner-pill" data-name="Partner HDFC" analytics-name="card" data-fh-id="fh-126"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-127" data-name="Partner pill dot"></span><span data-fh-id="fh-128" data-name="Text">HDFC Bank</span></div>
        <div class="partner-pill" data-name="Partner SBI" analytics-name="card" data-fh-id="fh-129"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-130" data-name="Partner pill dot"></span><span data-fh-id="fh-131" data-name="Text">State Bank of India</span></div>
        <div class="partner-pill" data-name="Partner ICICI" analytics-name="card" data-fh-id="fh-132"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-133" data-name="Partner pill dot"></span><span data-fh-id="fh-134" data-name="Text">ICICI Bank</span></div>
        <div class="partner-pill" data-name="Partner Axis" analytics-name="card" data-fh-id="fh-135"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-136" data-name="Partner pill dot"></span><span data-fh-id="fh-137" data-name="Text">Axis Bank</span></div>
        <div class="partner-pill" data-name="Partner Kotak" analytics-name="card" data-fh-id="fh-138"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-139" data-name="Partner pill dot"></span><span data-fh-id="fh-140" data-name="Text">Kotak Mahindra</span></div>
        <div class="partner-pill" data-name="Partner PNB" analytics-name="card" data-fh-id="fh-141"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-142" data-name="Partner pill dot"></span><span data-fh-id="fh-143" data-name="Text">Punjab National Bank</span></div>
        <div class="partner-pill" data-name="Partner IndusInd" analytics-name="card" data-fh-id="fh-144"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-145" data-name="Partner pill dot"></span><span data-fh-id="fh-146" data-name="Text">IndusInd Bank</span></div>
        <div class="partner-pill" data-name="Partner BOB" analytics-name="card" data-fh-id="fh-147"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-148" data-name="Partner pill dot"></span><span data-fh-id="fh-149" data-name="Text">Bank of Baroda</span></div>
        <div class="partner-pill" data-name="Partner Yes" analytics-name="card" data-fh-id="fh-150"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-151" data-name="Partner pill dot"></span><span data-fh-id="fh-152" data-name="Text">Yes Bank</span></div>
        <div class="partner-pill" data-name="Partner Federal" analytics-name="card" data-fh-id="fh-153"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-154" data-name="Partner pill dot"></span><span data-fh-id="fh-155" data-name="Text">Federal Bank</span></div>
        <div class="partner-pill" data-name="Partner LIC" analytics-name="card" data-fh-id="fh-156"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-157" data-name="Partner pill dot"></span><span data-fh-id="fh-158" data-name="Text">LIC Housing Finance</span></div>
        <div class="partner-pill" data-name="Partner Bajaj" analytics-name="card" data-fh-id="fh-159"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-160" data-name="Partner pill dot"></span><span data-fh-id="fh-161" data-name="Text">ASK</span></div>
        
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-162" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-163" data-name="Partner pill dot"></span><span data-fh-id="fh-164" data-name="Text">HDFC Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-165" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-166" data-name="Partner pill dot"></span><span data-fh-id="fh-167" data-name="Text">State Bank of India</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-168" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-169" data-name="Partner pill dot"></span><span data-fh-id="fh-170" data-name="Text">ICICI Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-171" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-172" data-name="Partner pill dot"></span><span data-fh-id="fh-173" data-name="Text">Axis Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-174" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-175" data-name="Partner pill dot"></span><span data-fh-id="fh-176" data-name="Text">Kotak Mahindra</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-177" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-178" data-name="Partner pill dot"></span><span data-fh-id="fh-179" data-name="Text">Punjab National Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-180" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-181" data-name="Partner pill dot"></span><span data-fh-id="fh-182" data-name="Text">IndusInd Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-183" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-184" data-name="Partner pill dot"></span><span data-fh-id="fh-185" data-name="Text">Bank of Baroda</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-186" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-187" data-name="Partner pill dot"></span><span data-fh-id="fh-188" data-name="Text">Yes Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-189" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-190" data-name="Partner pill dot"></span><span data-fh-id="fh-191" data-name="Text">Federal Bank</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-192" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-193" data-name="Partner pill dot"></span><span data-fh-id="fh-194" data-name="Text">LIC Housing Finance</span></div>
        <div class="partner-pill" aria-hidden="true" data-fh-id="fh-195" data-name="Partner pill" analytics-name="div"><span class="partner-pill-dot" aria-hidden="true" data-fh-id="fh-196" data-name="Partner pill dot"></span><span data-fh-id="fh-197" data-name="Text">ASK</span></div>
      </div>
    </div>

    <div class="partners-cta" data-name="Partners CTA" analytics-name="div-container" data-fh-id="fh-198">
      <p data-name="Partners note" analytics-name="text" data-fh-id="fh-199">Can't find your preferred lender? ASK's network spans 40+ banks, NBFCs, co-operative banks, and HFCs — we'll find the right fit for you.</p>
      <a class="btn btn-outline __freeform_button__" data-name="Partners CTA button" analytics-name="button" data-fh-id="fh-200" style="background-color: var(--primary); -webkit-text-fill-color: var(--text-on-accent) !important; color: var(--text-on-accent) !important; border-color: var(--primary);" href="#contact">Explore ASK Group Financial Services</a>
    </div>
  </div>
</section>


<style>
.testimonials {
  padding: 5rem 0;
  background-color: var(--surface);
}
.testimonials-header {
  max-width: 48ch;
  margin-bottom: 3rem;
}
.testimonials-header h2 { margin-top: 0.5rem; }

.testi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}

.testi-card {
  background-color: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 1.75rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  transition: transform var(--duration-base) ease, box-shadow var(--duration-base) ease;
  animation: fade-in-up var(--duration-slow) ease both;
  animation-timeline: view();
  animation-range: entry 0% entry 35%;
}
.testi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 36px color-mix(in srgb, var(--primary) 10%, transparent);
}

.testi-stars {
  display: flex;
  gap: 3px;
}
.testi-star {
  width: 14px; height: 14px;
  background-color: var(--accent);
  clip-path: polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);
}

.testi-quote {
  font-size: var(--text-base);
  color: var(--text);
  line-height: 1.7;
  font-style: italic;
  flex: 1;
}
.testi-quote::before { content: '\201C'; color: var(--accent); font-size: var(--text-3xl); line-height: 0.5; vertical-align: -0.4em; margin-right: 0.1em; }

.testi-author {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}
.testi-avatar {
  width: 42px; height: 42px;
  border-radius: 50%;
  background-color: var(--primary);
  display: flex; align-items: center; justify-content: center;
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-on-accent);
  flex-shrink: 0;
}
.testi-name { font-weight: 600; font-size: var(--text-sm); color: var(--text); }
.testi-meta { font-size: var(--text-xs); color: var(--muted); }

@media (max-width: 900px) { .testi-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .testi-grid { grid-template-columns: 1fr; } }
</style>

<section class="testimonials" id="products" aria-label="Client testimonials" data-name="Testimonials section" analytics-name="section" data-fh-id="fh-201">
  <div class="container" data-fh-id="fh-202" data-name="Container" analytics-name="div">
    <div class="testimonials-header" data-name="Testimonials header" analytics-name="div-container" data-fh-id="fh-203">
      <span class="eyebrow" data-name="Testimonials eyebrow" analytics-name="text" data-fh-id="fh-204">Client Stories</span>
      <h2 data-name="Testimonials heading" analytics-name="text" data-fh-id="fh-205">Numbers on paper. Decisions that changed lives.</h2>
    </div>
    <div class="testi-grid" data-name="Testimonials grid" analytics-name="div-container" data-fh-id="fh-206" data-fh-collection="testimonials-grid">

      <div class="testi-card" data-name="Testimonial 1" analytics-name="card" data-fh-id="fh-207" data-fh-item="">
        <div class="testi-stars" aria-label="5 out of 5 stars" data-fh-id="fh-208" data-name="Testi stars" analytics-name="div" data-fh-collection="testi-stars">
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-209" data-name="Testi star" analytics-name="div" data-fh-item=""></div><div class="testi-star" aria-hidden="true" data-fh-id="fh-210" data-name="Testi star" analytics-name="div" data-fh-item=""></div>
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-211" data-name="Testi star" analytics-name="div" data-fh-item=""></div><div class="testi-star" aria-hidden="true" data-fh-id="fh-212" data-name="Testi star" analytics-name="div" data-fh-item=""></div>
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-213" data-name="Testi star" analytics-name="div" data-fh-item="" data-fh-item-template=""></div>
        </div>
        <p class="testi-quote" data-name="Testimonial 1 quote" analytics-name="text" data-fh-id="fh-214" data-fh-field="testimonial-1-quote">My home loan was sanctioned in 3 days — something I was struggling with for months on my own. The rate ASK negotiated was 0.4% lower than what my bank offered directly.</p>
        <div class="testi-author" data-name="Testimonial 1 author" analytics-name="div-container" data-fh-id="fh-215">
          <div class="testi-avatar" aria-hidden="true" data-fh-id="fh-216" data-name="Testi avatar" analytics-name="div" data-fh-field="testi-avatar">RV</div>
          <div data-fh-id="fh-217" data-name="Container" analytics-name="div">
            <div class="testi-name" data-name="Testimonial 1 name" analytics-name="text" data-fh-id="fh-218" data-fh-field="testimonial-1-name">Ramesh Verma</div>
            <div class="testi-meta" data-name="Testimonial 1 meta" analytics-name="text" data-fh-id="fh-219" data-fh-field="testimonial-1-meta">Software Engineer, Bengaluru — Home Loan ₹68L</div>
          </div>
        </div>
      </div>

      <div class="testi-card" data-name="Testimonial 2" analytics-name="card" data-fh-id="fh-220" data-fh-item="">
        <div class="testi-stars" aria-label="5 out of 5 stars" data-fh-id="fh-221" data-name="Testi stars" analytics-name="div" data-fh-collection="testi-stars">
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-222" data-name="Testi star" analytics-name="div" data-fh-item=""></div><div class="testi-star" aria-hidden="true" data-fh-id="fh-223" data-name="Testi star" analytics-name="div" data-fh-item=""></div>
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-224" data-name="Testi star" analytics-name="div" data-fh-item=""></div><div class="testi-star" aria-hidden="true" data-fh-id="fh-225" data-name="Testi star" analytics-name="div" data-fh-item=""></div>
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-226" data-name="Testi star" analytics-name="div" data-fh-item="" data-fh-item-template=""></div>
        </div>
        <p class="testi-quote" data-name="Testimonial 2 quote" analytics-name="text" data-fh-id="fh-227" data-fh-field="testimonial-2-quote">I needed a business loan urgently for inventory. One call to ASK, and I had the disbursement in under 48 hours. Their process is genuinely paperless — I didn't print a single document.</p>
        <div class="testi-author" data-name="Testimonial 2 author" analytics-name="div-container" data-fh-id="fh-228">
          <div class="testi-avatar" aria-hidden="true" data-fh-id="fh-229" data-name="Testi avatar" analytics-name="div" data-fh-field="testi-avatar">PS</div>
          <div data-fh-id="fh-230" data-name="Container" analytics-name="div">
            <div class="testi-name" data-name="Testimonial 2 name" analytics-name="text" data-fh-id="fh-231" data-fh-field="testimonial-2-name">Priya Sharma</div>
            <div class="testi-meta" data-name="Testimonial 2 meta" analytics-name="text" data-fh-id="fh-232" data-fh-field="testimonial-2-meta">Retail Business Owner, Mumbai — Business Loan ₹25L</div>
          </div>
        </div>
      </div>

      <div class="testi-card" data-name="Testimonial 3" analytics-name="card" data-fh-id="fh-233" data-fh-item="" data-fh-item-template="">
        <div class="testi-stars" aria-label="5 out of 5 stars" data-fh-id="fh-234" data-name="Testi stars" analytics-name="div" data-fh-collection="testi-stars">
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-235" data-name="Testi star" analytics-name="div" data-fh-item=""></div><div class="testi-star" aria-hidden="true" data-fh-id="fh-236" data-name="Testi star" analytics-name="div" data-fh-item=""></div>
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-237" data-name="Testi star" analytics-name="div" data-fh-item=""></div><div class="testi-star" aria-hidden="true" data-fh-id="fh-238" data-name="Testi star" analytics-name="div" data-fh-item=""></div>
          <div class="testi-star" aria-hidden="true" data-fh-id="fh-239" data-name="Testi star" analytics-name="div" data-fh-item="" data-fh-item-template=""></div>
        </div>
        <p class="testi-quote" data-name="Testimonial 3 quote" analytics-name="text" data-fh-id="fh-240" data-fh-field="testimonial-3-quote">My CIBIL score was 680 and I thought no bank would touch me. ASK's advisor spent two months helping me fix it — and then found a lender who approved my personal loan at a fair rate.</p>
        <div class="testi-author" data-name="Testimonial 3 author" analytics-name="div-container" data-fh-id="fh-241">
          <div class="testi-avatar" aria-hidden="true" data-fh-id="fh-242" data-name="Testi avatar" analytics-name="div" data-fh-field="testi-avatar">AK</div>
          <div data-fh-id="fh-243" data-name="Container" analytics-name="div">
            <div class="testi-name" data-name="Testimonial 3 name" analytics-name="text" data-fh-id="fh-244" data-fh-field="testimonial-3-name">Arjun Kapoor</div>
            <div class="testi-meta" data-name="Testimonial 3 meta" analytics-name="text" data-fh-id="fh-245" data-fh-field="testimonial-3-meta">Marketing Manager, Hyderabad — Personal Loan ₹8L</div>
          </div>
        </div>
      </div>

    </div>
  </div>
</section>


<style>
.contact-section {
  padding: 5rem 0;
  background-color: var(--bg);
  position: relative;
  overflow: hidden;
}
.contact-section::before {
  content: '';
  position: absolute;
  bottom: -100px; left: -80px;
  width: 400px; height: 400px;
  background: radial-gradient(circle, color-mix(in srgb, var(--primary) 8%, transparent), transparent 70%);
  pointer-events: none;
}

.contact-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4rem;
  align-items: start;
  position: relative;
  z-index: 1;
}

.contact-info h2 { margin-top: 0.5rem; margin-bottom: 1rem; }
.contact-info > p { color: var(--fg); margin-bottom: 2rem; }

.contact-methods { display: flex; flex-direction: column; gap: 1.25rem; }
.contact-method {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  text-decoration: none;
  transition: border-color var(--duration-base) ease, box-shadow var(--duration-base) ease, transform var(--duration-fast) ease;
  min-height: 48px;
}
.contact-method:hover {
  border-color: var(--accent);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--accent) 12%, transparent);
  transform: translateX(4px);
  text-decoration: none;
}
.contact-method-icon {
  width: 44px; height: 44px;
  border-radius: var(--radius-sm);
  background-color: color-mix(in srgb, var(--primary) 10%, transparent);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.contact-method-label { font-size: var(--text-xs); color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
.contact-method-value { font-size: var(--text-base); font-weight: 600; color: var(--text); }

.contact-cta-card {
  background-color: var(--primary);
  border-radius: var(--radius-lg);
  padding: 2.5rem 2rem;
  position: relative;
  overflow: hidden;
}
.contact-cta-card::before {
  content: '';
  position: absolute;
  top: -60px; right: -60px;
  width: 220px; height: 220px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent) 20%, transparent), transparent 65%);
  pointer-events: none;
}
.contact-cta-card h3 {
  color: var(--text-on-accent);
  margin-bottom: 0.75rem;
  font-size: var(--text-2xl);
}
.contact-cta-card p  { color: var(--text-on-accent); opacity: 0.85; margin-bottom: 1.75rem; font-size: var(--text-base); }

.cta-actions { display: flex; flex-direction: column; gap: 0.875rem; }
.cta-btn-wa {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 0.875rem 1.5rem;
  background-color: #25d366;
  color: #ffffff;
  border-radius: var(--radius-sm);
  font-weight: 600;
  text-decoration: none;
  font-size: var(--text-base);
  transition: filter var(--duration-fast) ease, transform var(--duration-fast) ease;
  min-height: 48px;
}
.cta-btn-wa:hover { filter: brightness(1.1); transform: scale(1.02); text-decoration: none; color: #ffffff; }
.cta-btn-wa:active { transform: scale(0.97); }

.cta-btn-call {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 0.875rem 1.5rem;
  background-color: color-mix(in srgb, var(--accent) 15%, transparent);
  color: var(--text-on-accent);
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--text-on-accent) 30%, transparent);
  font-weight: 600;
  text-decoration: none;
  font-size: var(--text-base);
  transition: background-color var(--duration-fast) ease, transform var(--duration-fast) ease;
  min-height: 48px;
}
.cta-btn-call:hover { background-color: color-mix(in srgb, var(--accent) 25%, transparent); text-decoration: none; color: var(--text-on-accent); }
.cta-btn-call:active { transform: scale(0.97); }

.contact-hours { margin-top: 1.5rem; font-size: var(--text-xs); color: var(--text-on-accent); opacity: 0.65; text-align: center; }

@media (max-width: 900px) {
  .contact-grid { grid-template-columns: 1fr; gap: 2.5rem; }
}
</style>

<section class="contact-section" id="contact" aria-label="Contact ASK" data-name="Contact section" analytics-name="2-column section" data-fh-id="fh-246">
  <div class="container contact-grid" data-fh-id="fh-247" data-name="Container" analytics-name="div" data-fh-layout="split">
    <div class="contact-info" data-name="Contact info" analytics-name="div-container" data-fh-id="fh-248" data-fh-side="text">
      <span class="eyebrow" data-name="Contact eyebrow" analytics-name="text" data-fh-id="fh-249">Reach Us</span>
      <h2 data-name="Contact heading" analytics-name="text" data-fh-id="fh-250">Ready when you are — no appointment needed</h2>
      <p data-name="Contact description" analytics-name="text" data-fh-id="fh-251">Our advisors respond within 2 hours during business hours. Drop a WhatsApp message at any time and we'll pick it up first thing.</p>
      <div class="contact-methods" data-name="Contact methods" analytics-name="div-container" data-fh-id="fh-252">
        <a class="contact-method __freeform_button__" data-name="Phone contact" analytics-name="button" data-fh-id="fh-253" data-fh-layout="split" href="tel:+917869536698">
          <div class="contact-method-icon" aria-hidden="true" data-fh-id="fh-254" data-name="Contact method icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 13.5 19.79 19.79 0 01.5 4.88 2 2 0 012.5 2.7h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L6.91 10.1a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" stroke="var(--primary)" stroke-width="1.8"></path>
            </svg>
          </div>
          <div data-fh-id="fh-255" data-name="Container" analytics-name="div" data-fh-side="text">
            <div class="contact-method-label" data-fh-id="fh-256" data-name="Contact method label" analytics-name="div">Call Us</div>
            <div class="contact-method-value" data-fh-id="fh-257" data-name="Contact method value" analytics-name="div">+91 78695 36698 &nbsp;|&nbsp; +91 87701 35699</div>
          </div>
        </a>
        <a class="contact-method __freeform_button__" data-name="Email contact" analytics-name="button" data-fh-id="fh-258" data-fh-layout="split" href="mailto:askgroupfinance@gmail.com">
          <div class="contact-method-icon" aria-hidden="true" data-fh-id="fh-259" data-name="Contact method icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke="var(--primary)" stroke-width="1.8"></path>
              <polyline points="22,6 12,13 2,6" stroke="var(--primary)" stroke-width="1.8"></polyline>
            </svg>
          </div>
          <div data-fh-id="fh-260" data-name="Container" analytics-name="div" data-fh-side="text">
            <div class="contact-method-label" data-fh-id="fh-261" data-name="Contact method label" analytics-name="div">Email</div>
            <div class="contact-method-value" data-fh-id="fh-262" data-name="Contact method value" analytics-name="div">askgroupfinance@gmail.com</div>
          </div>
        </a>
        <a class="contact-method" data-name="Office location" analytics-name="button" data-fh-id="fh-263" data-fh-layout="split" href="https://www.google.com/maps/search/?api=1&amp;query=126+Bansi+Trade+Center,+Indore,+Madhya+Pradesh+452001" target="_blank" rel="noopener noreferrer">
          <div class="contact-method-icon" aria-hidden="true" data-fh-id="fh-264" data-name="Contact method icon" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" stroke="var(--primary)" stroke-width="1.8"></path>
              <circle cx="12" cy="10" r="3" stroke="var(--primary)" stroke-width="1.8"></circle>
            </svg>
          </div>
          <div data-fh-id="fh-265" data-name="Container" analytics-name="div" data-fh-side="text">
            <div class="contact-method-label" data-fh-id="fh-266" data-name="Contact method label" analytics-name="div">Office</div>
            <div class="contact-method-value" data-fh-id="fh-267" data-name="Contact method value" analytics-name="div">126 Bansi Trade Center, Indore 452001<br><strong>Open in Google Maps</strong></div>
          </div>
        </a>
      </div>
    </div>

    <div class="contact-cta-card" data-name="Contact CTA card" analytics-name="card" data-fh-id="fh-268" data-fh-side="image">
      <h3 data-name="CTA card heading" analytics-name="text" data-fh-id="fh-269">Get your free eligibility check</h3>
      <p data-name="CTA card description" analytics-name="text" data-fh-id="fh-270">Tell us what you need — we'll match you to the right product and lender within hours, with no obligation.</p>
      <div class="cta-actions" data-name="CTA actions" analytics-name="div-container" data-fh-id="fh-271">
        <a class="cta-btn-wa __freeform_button__" target="_blank" rel="noopener noreferrer" data-name="WhatsApp CTA" analytics-name="button" data-fh-id="fh-272" href="https://wa.me/917869536698?text=Hi%2C%20I%20want%20to%20check%20my%20loan%20eligibility">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"></path>
          </svg>
          Message on WhatsApp
        </a>
        <a class="cta-btn-call __freeform_button__" data-name="Call CTA" analytics-name="button" data-fh-id="fh-273" href="tel:+917869536698">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 13.5 19.79 19.79 0 01.5 4.88 2 2 0 012.5 2.7h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L6.91 10.1a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" stroke="currentColor" stroke-width="1.8"></path>
          </svg>
          Call for instant advice
        </a>
      </div>
      <p class="contact-hours" data-name="Office hours" analytics-name="text" data-fh-id="fh-274">Mon – Sat, 9 AM – 7 PM IST &nbsp;|&nbsp; WhatsApp 24/7</p>
    </div>
  </div>
</section>


<style>
.site-footer {
  background-color: var(--surface-strong);
  color: var(--text-on-surface-strong);
  --link: var(--link-on-strong);
  --link-hover: var(--link-hover-on-strong);
  padding: 3.5rem 0 2rem;
}

.footer-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: 3rem;
  margin-bottom: 3rem;
}

.footer-brand .nav-logo-text { color: var(--text-on-surface-strong); }
.footer-brand .nav-logo-text span { color: var(--accent); }
.footer-tagline { color: var(--text-on-surface-strong); opacity: 0.65; font-size: var(--text-sm); margin-top: 0.75rem; line-height: 1.65; max-width: 32ch; }

.footer-reg {
  margin-top: 1.25rem;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background-color: color-mix(in srgb, var(--accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-radius: 100px;
  padding: 0.35rem 0.875rem;
}
.footer-reg span { font-size: var(--text-xs); color: var(--accent); font-weight: 600; letter-spacing: 0.06em; }

.footer-col h5 {
  font-family: var(--font-body);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 1.25rem;
}
.footer-col ul { list-style: none; display: flex; flex-direction: column; gap: 0.625rem; }
.footer-col ul li a {
  font-size: var(--text-sm);
  color: var(--link);
  text-decoration: none;
  opacity: 0.8;
  transition: opacity var(--duration-fast) ease, color var(--duration-fast) ease;
}
.footer-col ul li a:hover { opacity: 1; color: var(--link-hover); }

.footer-divider {
  border: none;
  border-top: 1px solid color-mix(in srgb, var(--text-on-surface-strong) 15%, transparent);
  margin-bottom: 1.5rem;
}

.footer-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}
.footer-legal { font-size: var(--text-xs); color: var(--text-on-surface-strong); opacity: 0.5; }
.footer-disclaimer { font-size: var(--text-xs); color: var(--text-on-surface-strong); opacity: 0.4; max-width: 60ch; text-align: right; line-height: 1.55; }

@media (max-width: 900px) {
  .footer-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 560px) {
  .footer-grid { grid-template-columns: 1fr; gap: 2rem; }
  .footer-bottom { flex-direction: column; align-items: flex-start; }
  .footer-disclaimer { text-align: left; }
}
</style>


<style>
.float-wa {
  position: fixed;
  bottom: 1.75rem;
  right: 1.75rem;
  z-index: 999;
  width: 56px; height: 56px;
  border-radius: 50%;
  background-color: #25d366;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 24px color-mix(in srgb, #25d366 40%, transparent);
  text-decoration: none;
  transition: transform var(--duration-fast) ease, box-shadow var(--duration-fast) ease;
}
.float-wa:hover {
  transform: scale(1.1);
  box-shadow: 0 10px 32px color-mix(in srgb, #25d366 55%, transparent);
  text-decoration: none;
}
.float-wa:active { transform: scale(0.95); }
</style>

<a class="float-wa __freeform_button__" target="_blank" rel="noopener noreferrer" aria-label="Chat with us on WhatsApp" data-name="Floating WhatsApp button" analytics-name="button" data-fh-id="fh-275" href="https://wa.me/917869536698?text=Hi%2C%20I%20need%20help%20with%20a%20loan">
  <svg width="28" height="28" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"></path>
  </svg>
</a>

<footer class="site-footer" aria-label="Site footer" data-name="Site footer" analytics-name="footer" data-fh-id="fh-276">
  <div class="container" data-fh-id="fh-277" data-name="Container" analytics-name="div">
    <div class="footer-grid" data-name="Footer grid" analytics-name="div-container" data-fh-id="fh-278">
      <div class="footer-brand" data-name="Footer brand" analytics-name="div-container" data-fh-id="fh-279">
        <div class="nav-logo" data-name="Footer logo" analytics-name="text" data-fh-id="fh-280" data-fh-layout="split">
          <div class="nav-logo-mark" aria-hidden="true" data-fh-id="fh-281" data-name="Nav logo mark" analytics-name="div" data-fh-side="image">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M3 14 L7 8 L11 11 L15 5 L17 7" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
          </div>
          <span class="nav-logo-text" data-fh-id="fh-282" data-name="Nav logo text" data-fh-side="text">ASK<span data-fh-id="fh-283" data-name="Text"> Group Financial Services</span></span>
        </div>
        <p class="footer-tagline" data-name="Footer tagline" analytics-name="text" data-fh-id="fh-284" style="text-transform: none; font-style: normal;">Personal financial guidance for loans, insurance, and wealth planning. Clear options. Thoughtful advice.</p></div>

      <div class="footer-col" data-name="Footer services links" analytics-name="div-container" data-fh-id="fh-287">
        <h5 data-name="Footer services heading" analytics-name="text" data-fh-id="fh-288">Services</h5>
        <ul data-fh-id="fh-289" data-name="List" data-fh-collection="list">
          <li data-fh-id="fh-290" data-name="List item" data-fh-item=""><a data-name="Footer home loan link" analytics-name="button" data-fh-id="fh-291" data-fh-field="footer-home-loan-link" href="#services">Home Loans</a></li>
          <li data-fh-id="fh-292" data-name="List item" data-fh-item=""><a data-name="Footer personal loan link" analytics-name="button" data-fh-id="fh-293" data-fh-field="footer-personal-loan-link" href="#services">Personal Loans</a></li>
          <li data-fh-id="fh-294" data-name="List item" data-fh-item=""><a data-name="Footer business loan link" analytics-name="button" data-fh-id="fh-295" data-fh-field="footer-business-loan-link" href="#services">Business Loans</a></li>
          <li data-fh-id="fh-296" data-name="List item" data-fh-item=""><a data-name="Footer insurance link" analytics-name="button" data-fh-id="fh-297" data-fh-field="footer-insurance-link" href="#services">Insurance</a></li>
          <li data-fh-id="fh-298" data-name="List item" data-fh-item="" data-fh-item-template=""><a data-name="Footer investment link" analytics-name="button" data-fh-id="fh-299" data-fh-field="footer-investment-link" href="#services">Investments</a></li>
        </ul>
      </div>

      <div class="footer-col" data-name="Footer company links" analytics-name="div-container" data-fh-id="fh-300">
        <h5 data-name="Footer company heading" analytics-name="text" data-fh-id="fh-301">Company</h5>
        <ul data-fh-id="fh-302" data-name="List" data-fh-collection="list">
          <li data-fh-id="fh-303" data-name="List item" data-fh-item=""><a data-name="Footer about link" analytics-name="button" data-fh-id="fh-304" data-fh-field="footer-about-link" href="#why-us">About ASK</a></li>
          <li data-fh-id="fh-305" data-name="List item" data-fh-item=""><a data-name="Footer partners link" analytics-name="button" data-fh-id="fh-306" data-fh-field="footer-partners-link" href="#partners">Our Partners</a></li>
          <li data-fh-id="fh-307" data-name="List item" data-fh-item=""><a data-name="Footer careers link" analytics-name="button" data-fh-id="fh-308" data-fh-field="footer-careers-link" href="#">Careers</a></li>
          <li data-fh-id="fh-309" data-name="List item" data-fh-item="" data-fh-item-template=""><a data-name="Footer blog link" analytics-name="button" data-fh-id="fh-310" data-fh-field="footer-blog-link" href="#">Finance Blog</a></li>
        </ul>
      </div>

      <div class="footer-col" data-name="Footer legal links" analytics-name="div-container" data-fh-id="fh-311">
        <h5 data-name="Footer legal heading" analytics-name="text" data-fh-id="fh-312">Legal</h5>
        <ul data-fh-id="fh-313" data-name="List" data-fh-collection="list">
          <li data-fh-id="fh-314" data-name="List item" data-fh-item=""><a data-name="Footer privacy link" analytics-name="button" data-fh-id="fh-315" data-fh-field="footer-privacy-link" href="#">Privacy Policy</a></li>
          <li data-fh-id="fh-316" data-name="List item" data-fh-item=""><a data-name="Footer terms link" analytics-name="button" data-fh-id="fh-317" data-fh-field="footer-terms-link" href="#">Terms of Use</a></li>
          <li data-fh-id="fh-318" data-name="List item" data-fh-item=""><a data-name="Footer grievance link" analytics-name="button" data-fh-id="fh-319" data-fh-field="footer-grievance-link" href="#">Grievance Policy</a></li>
          <li data-fh-id="fh-320" data-name="List item" data-fh-item="" data-fh-item-template=""><a data-name="Footer disclosure link" analytics-name="button" data-fh-id="fh-321" data-fh-field="footer-disclosure-link" href="#">Fair Disclosure</a></li>
        </ul>
      </div>
    </div>

    <hr class="footer-divider">

    <div class="footer-bottom" data-name="Footer bottom" analytics-name="div-container" data-fh-id="fh-322">
      <p class="footer-legal" data-name="Copyright" analytics-name="text" data-fh-id="fh-323" style="text-transform: none; font-style: normal;">© 2026 ASK Group Financial Services Pvt. Ltd. All rights reserved.</p>

    </div>
  </div>
</footer>


</body></html>'''


@app.get("/")
def home():
    return Response(INDEX_HTML, mimetype="text/html")


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
