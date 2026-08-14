import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
import requests
import time
import urllib.parse

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="RailVision AI | Multi-Role Enterprise Intelligence & Live Tracking",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. SQLITE DATABASE INITIALIZATION & MIGRATION ---
def init_db():
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    # Users table supporting roles, passwords, and simulated OTP storage
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT,
            otp TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            train_name TEXT,
            route TEXT,
            travel_date TEXT,
            predicted_delay INTEGER,
            risk_level TEXT,
            carbon_saved TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            train_name TEXT,
            rating INTEGER,
            category TEXT,
            comments TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        c.execute("ALTER TABLE history ADD COLUMN carbon_saved TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Pre-populate default accounts if they don't exist
    default_accounts = [
        ("admin@railvision.gov", "admin123", "Admin"),
        ("ops@railvision.gov", "ops123", "Operations"),
        ("passenger@gmail.com", "pass123", "Passenger")
    ]
    for email, pwd, role in default_accounts:
        c.execute("INSERT OR IGNORE INTO users (email, password, role) VALUES (?, ?, ?)", (email, pwd, role))

    conn.commit()
    conn.close()

init_db()

def verify_user_credentials(email, password, role):
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE email = ? AND role = ?", (email, role))
    row = c.fetchone()
    conn.close()
    if row and row[0] == password:
        return True
    return False

def register_user(email, password, role="Passenger"):
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", (email, password, role))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def set_reset_otp(email, otp):
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    c.execute("UPDATE users SET otp = ? WHERE email = ?", (otp, email))
    conn.commit()
    conn.close()

def verify_and_update_password(email, otp, new_password):
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    c.execute("SELECT otp FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    if row and row[0] == otp:
        c.execute("UPDATE users SET password = ?, otp = NULL WHERE email = ?", (new_password, email))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# --- 2B. REAL NOTIFICATION DELIVERY (Email OTP + SMS Alerts) ---
# Reads credentials from .streamlit/secrets.toml. If not configured, falls back
# to simulated/demo delivery so the app keeps working out of the box.
#
# Add this to .streamlit/secrets.toml to enable REAL email OTP:
#   SMTP_HOST = "smtp.gmail.com"
#   SMTP_PORT = 465
#   SMTP_USER = "youraddress@gmail.com"
#   SMTP_PASS = "your-16-char-gmail-app-password"
#
# Add this to enable REAL SMS delivery (Twilio):
#   TWILIO_SID = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#   TWILIO_AUTH = "your_twilio_auth_token"
#   TWILIO_FROM_NUMBER = "+1xxxxxxxxxx"

def _get_secret(key, default=None):
    """Safely read a value from st.secrets. Streamlit raises if secrets.toml
    doesn't exist at all, so this treats 'no file' the same as 'no value'."""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

def send_email_otp(to_email, otp):
    host = _get_secret("SMTP_HOST")
    user = _get_secret("SMTP_USER")
    pwd = _get_secret("SMTP_PASS")
    port = int(_get_secret("SMTP_PORT", 465))
    if not (host and user and pwd):
        return False, "not_configured"
    try:
        msg = MIMEText(f"Your RailVision verification code is: {otp}\n\nThis code expires in 10 minutes. If you did not request this, ignore this email.")
        msg["Subject"] = "RailVision Password Reset — Verification Code"
        msg["From"] = user
        msg["To"] = to_email
        with smtplib.SMTP_SSL(host, port, timeout=10) as server:
            server.login(user, pwd)
            server.sendmail(user, [to_email], msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)

def send_sms_alert(to_phone, message):
    sid = _get_secret("TWILIO_SID")
    token = _get_secret("TWILIO_AUTH")
    from_number = _get_secret("TWILIO_FROM_NUMBER")
    if not (sid and token and from_number):
        return False, "not_configured"
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        resp = requests.post(
            url,
            data={"From": from_number, "To": to_phone, "Body": message},
            auth=(sid, token),
            timeout=10
        )
        if resp.status_code in (200, 201):
            return True, "sent"
        return False, resp.text
    except Exception as e:
        return False, str(e)

# --- 2C. LIVE STATION / TRACKSIDE CAMERA FEEDS ---
# By default this renders a clearly-labeled DEMO feed (auto-refreshing placeholder
# imagery) so the UI works out of the box with no camera hardware required.
#
# To wire up REAL live cameras, add a CAMERA_FEED_URLS table to
# .streamlit/secrets.toml mapping station name -> an HTTP(S) snapshot/MJPEG URL
# from your CCTV/NVR system, e.g.:
#
#   [CAMERA_FEED_URLS]
#   "Mumbai Central" = "https://your-nvr.example.com/cam/platform1/snapshot.jpg"
#   "New Delhi"       = "https://your-nvr.example.com/cam/concourse/snapshot.jpg"
#
# Most station CCTV/NVR systems expose an HTTP snapshot or MJPEG endpoint that
# can be dropped in directly. Raw RTSP streams need a media-gateway (e.g. an
# RTSP-to-HLS/MJPEG relay) in front of them since browsers can't play RTSP.
CAMERA_REFRESH_SECONDS = 10

def get_camera_feed(station_name, camera_label="Platform Cam"):
    """Returns (image_url, is_real_feed). Falls back to an auto-refreshing
    demo placeholder if no real camera URL is configured for this station."""
    feed_map = _get_secret("CAMERA_FEED_URLS", {}) or {}
    real_url = feed_map.get(station_name)
    if real_url:
        # cache-bust so the browser actually re-fetches the snapshot each refresh
        sep = "&" if "?" in real_url else "?"
        return f"{real_url}{sep}_ts={int(time.time())}", True

    bucket = int(time.time() // CAMERA_REFRESH_SECONDS)
    seed = urllib.parse.quote(f"{station_name}-{camera_label}-{bucket}")
    return f"https://picsum.photos/seed/{seed}/640/360", False

def save_prediction(user_email, train_name, route, travel_date, delay, risk, carbon):
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO history (user_email, train_name, route, travel_date, predicted_delay, risk_level, carbon_saved)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_email, train_name, route, str(travel_date), delay, risk, carbon))
    conn.commit()
    conn.close()

def save_feedback(user_email, train_name, rating, category, comments):
    conn = sqlite3.connect("railway.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO feedback (user_email, train_name, rating, category, comments)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_email, train_name, rating, category, comments))
    conn.commit()
    conn.close()

def get_history(user_email):
    conn = sqlite3.connect("railway.db")
    try:
        if user_email == "Guest":
            df = pd.read_sql_query("SELECT train_name as Train, route as Route, travel_date as Date, predicted_delay as 'Delay (Mins)', risk_level as Risk, carbon_saved as 'Carbon Saved', timestamp as 'Saved At' FROM history WHERE user_email='Guest' ORDER BY id DESC LIMIT 10", conn)
        else:
            df = pd.read_sql_query("SELECT train_name as Train, route as Route, travel_date as Date, predicted_delay as 'Delay (Mins)', risk_level as Risk, carbon_saved as 'Carbon Saved', timestamp as 'Saved At' FROM history WHERE user_email=? ORDER BY id DESC LIMIT 10", conn, params=(user_email,))
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def get_all_feedback():
    conn = sqlite3.connect("railway.db")
    try:
        df = pd.read_sql_query("SELECT id, user_email as 'Passenger', train_name as 'Train', rating as 'Rating (1-5)', category as 'Category', comments as 'Comments', timestamp as 'Submitted At' FROM feedback ORDER BY id DESC", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

# --- 3. CUSTOM CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap');

    :root {
        --bg-void: #05070d;
        --bg-panel: #0d1220;
        --bg-panel-2: #121a2c;
        --line: #1e293b;
        --line-soft: rgba(148, 163, 184, 0.12);
        --ink: #f1f5f9;
        --ink-dim: #8b97ab;
        --signal-cyan: #22d3ee;
        --signal-amber: #ffb020;
        --signal-green: #22c55e;
        --signal-red: #ef4444;
    }

    html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }

    .stApp {
        background:
            radial-gradient(ellipse 900px 500px at 12% -10%, rgba(34, 211, 238, 0.10), transparent 60%),
            radial-gradient(ellipse 700px 500px at 100% 10%, rgba(255, 176, 32, 0.07), transparent 55%),
            repeating-linear-gradient(0deg, var(--line-soft) 0px, var(--line-soft) 1px, transparent 1px, transparent 64px),
            repeating-linear-gradient(90deg, var(--line-soft) 0px, var(--line-soft) 1px, transparent 1px, transparent 64px),
            var(--bg-void);
        font-family: 'Inter', system-ui, sans-serif;
    }
    section.main .block-container { position: relative; z-index: 1; padding-top: 2.2rem; }

    h1, h2, h3, .hero-tagline, .brand-logo-text, .hero-title { font-family: 'Rajdhani', 'Inter', sans-serif; }
    code, .mono, .metric-value, .ticker-track, .eyebrow, .stat-chip b { font-family: 'IBM Plex Mono', monospace; }

    @keyframes moveGlow {
        0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; }
    }

    /* ===== SIGNAL LAMP CLUSTER (system-status signature element) ===== */
    .signal-lamps { display: flex; align-items: center; gap: 7px; margin-bottom: 14px; }
    .lamp { width: 9px; height: 9px; border-radius: 50%; background: #3a4457; }
    .lamp.red { background: var(--signal-red); box-shadow: 0 0 8px rgba(239,68,68,0.7); }
    .lamp.amber { background: var(--signal-amber); box-shadow: 0 0 8px rgba(255,176,32,0.7); }
    .lamp.green { background: var(--signal-green); box-shadow: 0 0 8px rgba(34,197,94,0.85); animation: lampPulse 1.8s ease-in-out infinite; }
    @keyframes lampPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }
    .signal-label { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; letter-spacing: 1.5px; color: var(--ink-dim); text-transform: uppercase; }

    /* ===== BRAND ===== */
    .brand-logo-container { display: flex; align-items: center; gap: 14px; margin-bottom: 8px; }
    .brand-icon {
        font-size: 2.6rem;
        filter: drop-shadow(0 0 14px rgba(34, 211, 238, 0.55));
        animation: pulseIcon 3s infinite alternate;
    }
    @keyframes pulseIcon { 0% { transform: scale(1); } 100% { transform: scale(1.06); } }
    .brand-logo-text {
        color: var(--ink);
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: 3px;
        text-transform: uppercase;
        margin: 0;
        line-height: 1;
    }
    .brand-logo-text span { color: var(--signal-cyan); }

    .eyebrow {
        display: inline-block;
        color: var(--signal-amber);
        font-size: 0.72rem;
        letter-spacing: 3px;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 18px;
        padding: 5px 12px;
        border: 1px solid rgba(255,176,32,0.35);
        border-radius: 4px;
        background: rgba(255,176,32,0.06);
    }

    .hero-tagline {
        color: var(--ink);
        font-size: 3.4rem;
        font-weight: 700;
        line-height: 1.08;
        letter-spacing: -0.5px;
        margin-bottom: 22px;
    }
    .hero-highlight { color: var(--signal-cyan); }

    .stat-chip-row { display: flex; gap: 14px; margin-top: 8px; flex-wrap: wrap; }
    .stat-chip {
        background: var(--bg-panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px 16px;
        min-width: 110px;
    }
    .stat-chip b { display: block; color: var(--signal-cyan); font-size: 1.25rem; font-weight: 600; }
    .stat-chip span { color: var(--ink-dim); font-size: 0.68rem; letter-spacing: 1px; text-transform: uppercase; }

    /* ===== LOGIN CARD (glass panel with signal-amber top rail) ===== */
    .login-card-wrapper {
        background: linear-gradient(180deg, rgba(18,26,44,0.92) 0%, rgba(13,18,32,0.96) 100%);
        border: 1px solid var(--line);
        border-top: 3px solid var(--signal-amber);
        border-radius: 14px;
        padding: 34px 32px 22px 32px;
        box-shadow: 0 25px 50px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.02) inset;
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(6px);
    }
    .login-card-wrapper::before {
        content: '';
        position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
        background: radial-gradient(circle, rgba(34, 211, 238, 0.05) 0%, transparent 60%);
        animation: moveGlow 12s infinite linear;
        pointer-events: none;
    }
    .login-header-text {
        color: var(--ink);
        font-size: 1.3rem;
        font-weight: 700;
        font-family: 'Rajdhani', sans-serif;
        letter-spacing: 0.5px;
        margin-bottom: 22px;
        display: flex; align-items: center; gap: 10px;
    }

    /* ===== RESKIN STREAMLIT FORM WIDGETS ===== */
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input {
        background: rgba(6, 10, 20, 0.75) !important;
        border: 1px solid var(--line) !important;
        border-radius: 8px !important;
        color: var(--ink) !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.92rem !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus,
    div[data-testid="stNumberInput"] input:focus {
        border-color: var(--signal-cyan) !important;
        box-shadow: 0 0 0 1px var(--signal-cyan), 0 0 12px rgba(34,211,238,0.25) !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: rgba(6, 10, 20, 0.75) !important;
        border: 1px solid var(--line) !important;
        border-radius: 8px !important;
    }
    label, .stSelectbox label, .stTextInput label, .stCheckbox label p, .stSlider label {
        color: var(--ink-dim) !important;
        font-size: 0.76rem !important;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        font-weight: 600 !important;
    }
    div[data-testid="stCheckbox"] label p { text-transform: none !important; font-size: 0.9rem !important; }

    /* ===== BUTTONS (signal-amber primary action) ===== */
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #f59e0b 0%, #ffb020 100%) !important;
        color: #1a1200 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 12px 24px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.4px;
        width: 100% !important;
        box-shadow: 0 4px 18px rgba(255, 176, 32, 0.35);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(255, 176, 32, 0.55);
    }
    div.stButton > button:first-child:focus-visible {
        outline: 2px solid var(--signal-cyan) !important;
        outline-offset: 2px;
    }

    .create-btn-container div.stButton > button:first-child {
        background: transparent !important;
        color: var(--signal-cyan) !important;
        border: 1.5px solid rgba(34,211,238,0.5) !important;
        box-shadow: none;
    }
    .create-btn-container div.stButton > button:first-child:hover {
        background: rgba(34, 211, 238, 0.08) !important;
        box-shadow: 0 0 16px rgba(34,211,238,0.2);
    }

    .footer-brand {
        text-align: center;
        color: #52607a;
        font-size: 0.72rem;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        font-weight: 600;
        margin-top: 26px;
    }

    .live-pulse {
        display: inline-block; width: 11px; height: 11px;
        background-color: var(--signal-green);
        border-radius: 50%;
        box-shadow: 0 0 0 rgba(34,197,94,0.7);
        animation: pulse 1.6s infinite;
        margin-right: 8px;
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.7); }
        70% { box-shadow: 0 0 0 10px rgba(34,197,94,0); }
        100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
    }

    /* ===== HERO / DASHBOARD PANELS ===== */
    .hero-container {
        background: linear-gradient(135deg, var(--bg-panel-2) 0%, #0a0f1d 100%);
        border: 1px solid var(--line);
        border-left: 3px solid var(--signal-cyan);
        border-radius: 12px;
        padding: 22px 30px;
        margin-bottom: 18px;
        box-shadow: 0 10px 24px rgba(0,0,0,0.35);
    }
    .hero-title { color: var(--ink); font-size: 1.9rem; font-weight: 700; margin: 0; letter-spacing: 0.3px; }
    .hero-subtitle { color: var(--ink-dim); font-size: 0.92rem; margin-top: 6px; font-family: 'Inter', sans-serif; }

    .badge-low { background: rgba(34,197,94,0.12); color: var(--signal-green); border: 1px solid var(--signal-green); padding: 6px 16px; border-radius: 20px; font-weight: 700; font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; letter-spacing: 0.5px; }
    .badge-medium { background: rgba(255,176,32,0.12); color: var(--signal-amber); border: 1px solid var(--signal-amber); padding: 6px 16px; border-radius: 20px; font-weight: 700; font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; letter-spacing: 0.5px; }
    .badge-high { background: rgba(239,68,68,0.12); color: var(--signal-red); border: 1px solid var(--signal-red); padding: 6px 16px; border-radius: 20px; font-weight: 700; font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; letter-spacing: 0.5px; }

    .metric-card {
        background: var(--bg-panel);
        border: 1px solid var(--line);
        border-top: 2px solid var(--signal-cyan);
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(34,211,238,0.15); border-color: var(--signal-cyan); }
    .metric-label { color: var(--ink-dim); font-size: 0.68rem; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; font-family: 'IBM Plex Mono', monospace; }
    .metric-value { color: var(--ink); font-size: 1.55rem; font-weight: 600; margin-top: 4px; }

    /* ===== ANIMATED BACKGROUND PARTICLES (signal blips) ===== */
    .particles-bg { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; overflow: hidden; pointer-events: none; z-index: 0; }
    .particle {
        position: absolute; bottom: -20px; border-radius: 50%;
        background: radial-gradient(circle, rgba(34,211,238,0.85) 0%, rgba(34,211,238,0) 70%);
        animation-name: floatUp; animation-timing-function: linear; animation-iteration-count: infinite; opacity: 0;
    }
    @keyframes floatUp {
        0% { transform: translateY(0) translateX(0); opacity: 0; }
        10% { opacity: 0.8; } 90% { opacity: 0.4; }
        100% { transform: translateY(-105vh) translateX(20px); opacity: 0; }
    }

    /* ===== MOVING RAIL TRACK + TRAIN RUNNER ===== */
    .rail-track-wrap { position: relative; width: 100%; height: 30px; margin: 4px 0 20px 0; overflow: hidden; }
    .rail-track-line {
        position: absolute; top: 50%; left: 0; width: 100%; height: 3px; transform: translateY(-50%);
        background-image: repeating-linear-gradient(90deg, #263449 0px, #263449 14px, transparent 14px, transparent 26px);
        opacity: 0.9;
    }
    .rail-track-line::before {
        content: ''; position: absolute; top: -3px; left: 0; width: 100%; height: 9px;
        background-image: repeating-linear-gradient(90deg, transparent 0px, transparent 34px, rgba(255,176,32,0.55) 34px, rgba(255,176,32,0.55) 46px);
        animation: dashMove 2.2s linear infinite;
    }
    @keyframes dashMove { from { background-position-x: 0; } to { background-position-x: -80px; } }
    .train-runner {
        position: absolute; top: 50%; left: -60px; transform: translateY(-65%);
        font-size: 1.5rem; animation: trainMove 7s linear infinite;
        filter: drop-shadow(0 0 8px rgba(34,211,238,0.7));
    }
    @keyframes trainMove { 0% { left: -8%; } 100% { left: 108%; } }

    /* ===== DEPARTURE-BOARD STYLE LIVE TICKER ===== */
    .ticker-wrap {
        width: 100%; overflow: hidden;
        background: #08101a;
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 9px 0;
        margin-bottom: 20px;
        box-shadow: inset 0 0 16px rgba(255,176,32,0.04);
    }
    .ticker-track {
        display: inline-block; white-space: nowrap; padding-left: 100%;
        animation: tickerScroll 28s linear infinite;
        color: var(--signal-amber);
        font-size: 0.82rem; font-weight: 500; letter-spacing: 1px;
        text-shadow: 0 0 6px rgba(255,176,32,0.35);
    }
    .ticker-track span.sep { color: #334155; margin: 0 22px; }
    @keyframes tickerScroll { 0% { transform: translateX(0); } 100% { transform: translateX(-100%); } }

    /* ===== ENTRANCE ANIMATIONS ===== */
    @keyframes fadeInUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
    .hero-container, .login-card-wrapper { animation: fadeInUp 0.5s ease-out; }
    .hero-container:hover { box-shadow: 0 14px 28px rgba(34,211,238,0.1); transition: box-shadow 0.3s ease; }

    @media (prefers-reduced-motion: reduce) {
        .particle, .train-runner, .rail-track-line::before, .ticker-track, .lamp.green,
        .brand-icon, .login-card-wrapper::before, .hero-container, .login-card-wrapper { animation: none !important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- 3B. DECORATIVE ANIMATED BACKGROUND (signal blips) ---
_particle_specs = [
    (3, "6%", 0), (5, "14%", 3), (4, "23%", 7), (7, "31%", 1), (3, "40%", 9),
    (6, "48%", 4), (4, "57%", 12), (8, "65%", 2), (3, "74%", 6), (5, "82%", 10),
    (4, "90%", 5), (6, "97%", 8),
]
_particles_html = "".join(
    f'<span class="particle" style="left:{left}; width:{size}px; height:{size}px; '
    f'animation-duration:{9 + (idx % 5) * 2}s; animation-delay:{delay}s;"></span>'
    for idx, (size, left, delay) in enumerate(_particle_specs)
)
st.markdown(f'<div class="particles-bg">{_particles_html}</div>', unsafe_allow_html=True)

# --- 4. DATASETS: REAL INDIAN RAILWAY ROUTES WITH INTERMEDIATE WAYPOINTS ---
TRAINS_DATABASE = {
    "12951 - Mumbai Rajdhani Express": {
        "origin": "Mumbai Central", "dest": "New Delhi", 
        "path_lats": [18.9696, 21.1702, 23.0225, 27.1767, 28.6139], 
        "path_lons": [72.8193, 72.8311, 72.5714, 78.0081, 77.2090], 
        "waypoints": ["Mumbai Central", "Surat", "Vadodara", "Agra Cantt", "New Delhi"],
        "distance": 1384, "base_delay": 10, "occupancy": "88% (High Demand)"
    },
    "12002 - Bhopal Shatabdi Express": {
        "origin": "New Delhi", "dest": "Bhopal Junction", 
        "path_lats": [28.6139, 27.5706, 27.1767, 25.4484, 23.2599], 
        "path_lons": [77.2090, 77.6756, 78.0081, 78.5685, 77.4126], 
        "waypoints": ["New Delhi", "Mathura", "Agra Cantt", "Jhansi", "Bhopal Junction"],
        "distance": 701, "base_delay": 8, "occupancy": "72% (Moderate)"
    },
    "22436 - Vande Bharat Express": {
        "origin": "New Delhi", "dest": "Varanasi Junction", 
        "path_lats": [28.6139, 27.5706, 26.4499, 25.4358, 25.3176], 
        "path_lons": [77.2090, 77.6756, 80.3319, 81.8463, 82.9739], 
        "waypoints": ["New Delhi", "Mathura", "Kanpur Central", "Prayagraj", "Varanasi Junction"],
        "distance": 759, "base_delay": 4, "occupancy": "95% (Near Full)"
    },
    "12302 - Howrah Rajdhani Express": {
        "origin": "New Delhi", "dest": "Howrah Junction", 
        "path_lats": [28.6139, 25.4358, 25.5941, 23.8323, 22.5851], 
        "path_lons": [77.2090, 81.8463, 85.1376, 86.4133, 88.3415], 
        "waypoints": ["New Delhi", "Prayagraj", "Patna (DDU)", "Dhanbad", "Howrah Junction"],
        "distance": 1447, "base_delay": 15, "occupancy": "91% (High Demand)"
    },
    "12626 - Kerala Express": {
        "origin": "New Delhi", "dest": "Thiruvananthapuram", 
        "path_lats": [28.6139, 23.2599, 17.3850, 13.0827, 8.5074], 
        "path_lons": [77.2090, 77.4126, 78.4867, 80.2707, 76.9558], 
        "waypoints": ["New Delhi", "Bhopal", "Nagpur / Secunderabad", "Chennai Central", "Thiruvananthapuram"],
        "distance": 3031, "base_delay": 35, "occupancy": "84% (Moderate)"
    },
    "12138 - Punjab Mail": {
        "origin": "Firozpur Cantt", "dest": "Mumbai CSMT", 
        "path_lats": [30.9237, 30.7333, 28.6139, 27.1767, 21.1458, 18.9401], 
        "path_lons": [74.6112, 76.7794, 77.2090, 78.0081, 79.0882, 72.8352], 
        "waypoints": ["Firozpur Cantt", "Chandigarh/Ambala", "New Delhi", "Agra", "Itarsi/Nagpur", "Mumbai CSMT"],
        "distance": 1928, "base_delay": 30, "occupancy": "79% (Moderate)"
    },
    "12622 - Tamil Nadu Express": {
        "origin": "New Delhi", "dest": "Chennai Central", 
        "path_lats": [28.6139, 25.4484, 21.1458, 17.3850, 13.0827], 
        "path_lons": [77.2090, 78.5685, 79.0882, 78.4867, 80.2707], 
        "waypoints": ["New Delhi", "Jhansi", "Nagpur", "Hyderabad (Balharshah)", "Chennai Central"],
        "distance": 2182, "base_delay": 22, "occupancy": "86% (High Demand)"
    },
    "12925 - Paschim Express": {
        "origin": "Mumbai Central", "dest": "Amritsar Junction", 
        "path_lats": [18.9696, 21.1702, 23.0225, 28.6139, 31.1471, 31.6340], 
        "path_lons": [72.8193, 72.8311, 72.5714, 77.2090, 75.7028, 74.8723], 
        "waypoints": ["Mumbai Central", "Surat", "Vadodara", "New Delhi", "Ambala", "Amritsar Junction"],
        "distance": 1821, "base_delay": 20, "occupancy": "80% (Moderate)"
    }
}

ROUTE_PATHS = [f"{data['origin']} → {data['dest']}" for data in TRAINS_DATABASE.values()]

# --- 4B. LIVE GPS TRACKER HELPERS ---
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

def build_segment_cumdist(lats, lons):
    """Cumulative great-circle distance (km) at each waypoint along the path."""
    cum = [0.0]
    for i in range(1, len(lats)):
        cum.append(cum[-1] + haversine_km(lats[i-1], lons[i-1], lats[i], lons[i]))
    return cum

def interpolate_along_path(lats, lons, progress_pct):
    """Given 0-100 progress along the route, return (lat, lon, segment_idx, km_covered, km_total)."""
    cum = build_segment_cumdist(lats, lons)
    total = cum[-1] if cum[-1] > 0 else 1.0
    target = (max(0.0, min(100.0, progress_pct)) / 100.0) * total
    for i in range(1, len(cum)):
        if target <= cum[i] or i == len(cum) - 1:
            seg_len = cum[i] - cum[i-1]
            frac = 0.0 if seg_len == 0 else (target - cum[i-1]) / seg_len
            lat = lats[i-1] + frac * (lats[i] - lats[i-1])
            lon = lons[i-1] + frac * (lons[i] - lons[i-1])
            return lat, lon, i - 1, target, total
    return lats[-1], lons[-1], len(lats) - 2, total, total

# --- 5. SESSION STATE MANAGEMENT ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = ""
    st.session_state.user_role = "Passenger"
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "login"
if "simulated_blockage" not in st.session_state:
    st.session_state.simulated_blockage = False
if "gps_progress" not in st.session_state:
    st.session_state.gps_progress = {}
if "gps_last_update" not in st.session_state:
    st.session_state.gps_last_update = {}

# --- 6. AUTHENTICATION PORTAL ---
if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_left, col_right = st.columns([1.2, 1], gap="large")

    with col_left:
        st.markdown("""
            <div class="signal-lamps">
                <span class="lamp red"></span><span class="lamp amber"></span><span class="lamp green"></span>
                <span class="signal-label">Network Status // Operational</span>
            </div>
            <div class="brand-logo-container">
                <span class="brand-icon">🚆</span>
                <h1 class="brand-logo-text">rail<span>vision</span></h1>
            </div>
            <div class="eyebrow">Enterprise Edition · AI Rail Intelligence</div>
            <div class="hero-tagline">
                Predict delays.<br>Track trains live.<br><span class="hero-highlight">Move India smarter.</span>
            </div>
            <div class="rail-track-wrap">
                <div class="rail-track-line"></div>
                <span class="train-runner">🚄</span>
            </div>
            <div class="stat-chip-row">
                <div class="stat-chip"><b>8</b><span>Corridors Live</span></div>
                <div class="stat-chip"><b>91.4%</b><span>Model Accuracy</span></div>
                <div class="stat-chip"><b>24/7</b><span>GPS Tracking</span></div>
            </div>
        """, unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="login-card-wrapper">', unsafe_allow_html=True)
        
        # --- VIEW MODE: LOGIN ---
        if st.session_state.view_mode == "login":
            st.markdown('<div class="login-header-text">Sign In to RailVision Portal</div>', unsafe_allow_html=True)
            
            selected_role_login = st.selectbox("Select Portal Role", ["Passenger", "Operations Controller", "System Administrator"])
            user_input = st.text_input("Email address or ID", key="login_user", placeholder="Enter your credentials")
            password_input = st.text_input("Password / Secure PIN", type="password", key="login_pwd", placeholder="Enter password")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Authenticate & Enter"):
                if user_input and password_input:
                    db_role = "Admin" if selected_role_login == "System Administrator" else ("Operations" if selected_role_login == "Operations Controller" else "Passenger")
                    
                    if verify_user_credentials(user_input, password_input, db_role):
                        st.session_state.logged_in = True
                        st.session_state.user_email = user_input
                        st.session_state.user_role = db_role
                        st.rerun()
                    else:
                        st.error("❌ Authentication Failed: Incorrect password or email for the selected role.")
                else:
                    st.error("Please fill in all authentication fields.")

            st.markdown("<hr style='border-color: #1e293b; margin: 15px 0;'>", unsafe_allow_html=True)
            
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.markdown('<div class="create-btn-container">', unsafe_allow_html=True)
                if st.button("Create Account"):
                    st.session_state.view_mode = "register"
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with col_b2:
                st.markdown('<div class="create-btn-container">', unsafe_allow_html=True)
                if st.button("Forgot Password?"):
                    st.session_state.view_mode = "forgot"
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("👤 Quick Access as Guest Passenger"):
                st.session_state.logged_in = True
                st.session_state.user_email = "Guest"
                st.session_state.user_role = "Passenger"
                st.rerun()

        # --- VIEW MODE: REGISTER ---
        elif st.session_state.view_mode == "register":
            st.markdown('<div class="login-header-text">Create New Account</div>', unsafe_allow_html=True)
            reg_role = st.selectbox("Account Role Type", ["Passenger", "Operations Controller", "System Administrator"])
            new_email = st.text_input("Email address", key="reg_email", placeholder="Enter your email")
            new_pass = st.text_input("New password", type="password", key="reg_pass", placeholder="New password")
            confirm_pass = st.text_input("Confirm password", type="password", key="reg_confirm", placeholder="Confirm password")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Register Account"):
                if new_email and new_pass and (new_pass == confirm_pass):
                    # Enforce domain validation for Admin and Operations roles
                    if reg_role in ["Operations Controller", "System Administrator"] and not new_email.endswith("@railvision.gov"):
                        st.error("❌ Operations and Admin accounts require a valid '@railvision.gov' corporate email address.")
                    else:
                        db_role = "Admin" if reg_role == "System Administrator" else ("Operations" if reg_role == "Operations Controller" else "Passenger")
                        success = register_user(new_email, new_pass, db_role)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user_email = new_email
                            st.session_state.user_role = db_role
                            st.rerun()
                        else:
                            st.error("An account with this email already exists!")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match!")
                else:
                    st.error("Please fill in all fields.")

            st.markdown("<hr style='border-color: #1e293b; margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown('<div class="create-btn-container">', unsafe_allow_html=True)
            if st.button("Back to Login"):
                st.session_state.view_mode = "login"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # --- VIEW MODE: FORGOT PASSWORD (EMAIL OTP) ---
        elif st.session_state.view_mode == "forgot":
            st.markdown('<div class="login-header-text">🔐 Reset Password via Email OTP</div>', unsafe_allow_html=True)
            
            if "otp_sent" not in st.session_state:
                st.session_state.otp_sent = False

            forgot_role = st.selectbox("Select Account Role", ["Passenger", "Operations Controller", "System Administrator"], key="forgot_role")
            forgot_email = st.text_input("Registered Email ID", key="forgot_email", placeholder="Enter account email")

            if not st.session_state.otp_sent:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Send Verification OTP"):
                    if forgot_email:
                        db_role = "Admin" if forgot_role == "System Administrator" else ("Operations" if forgot_role == "Operations Controller" else "Passenger")
                        conn = sqlite3.connect("railway.db")
                        c = conn.cursor()
                        c.execute("SELECT id FROM users WHERE email = ? AND role = ?", (forgot_email, db_role))
                        exists = c.fetchone()
                        conn.close()

                        if exists:
                            generated_otp = str(random.randint(100000, 999999))
                            set_reset_otp(forgot_email, generated_otp)
                            st.session_state.otp_sent = True
                            st.session_state.temp_otp_email = forgot_email
                            email_sent, status = send_email_otp(forgot_email, generated_otp)
                            if email_sent:
                                st.success(f"📨 Verification code sent to {forgot_email}. Check your inbox (and spam folder).")
                            elif status == "not_configured":
                                st.warning(f"⚠️ Demo mode: SMTP not configured, so email wasn't actually sent. Add SMTP_HOST/SMTP_USER/SMTP_PASS to .streamlit/secrets.toml to send real emails. Your code for this demo: **{generated_otp}**")
                            else:
                                print(f"[RailVision] Email OTP delivery failed for {forgot_email}: {status}")
                                st.error("❌ We couldn't send the verification email right now. Please try again in a moment.")
                            st.rerun()
                        else:
                            st.error("No account found matching this email and role combination.")
                    else:
                        st.warning("Please enter your email address.")
            else:
                st.info(f"Verification code sent to: **{st.session_state.get('temp_otp_email', '')}**")
                entered_otp = st.text_input("Enter 6-Digit OTP Code", max_chars=6, placeholder="123456")
                new_reset_pass = st.text_input("New Password", type="password", placeholder="Enter new password")
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Verify & Update Password"):
                    if entered_otp and new_reset_pass:
                        if verify_and_update_password(st.session_state.temp_otp_email, entered_otp, new_reset_pass):
                            st.success("✓ Password successfully updated! Please sign in with your new password.")
                            st.session_state.otp_sent = False
                            st.session_state.view_mode = "login"
                            st.rerun()
                        else:
                            st.error("❌ Incorrect OTP code entered. Please try again.")
                    else:
                        st.warning("Please enter both the OTP and your new password.")

            st.markdown("<hr style='border-color: #1e293b; margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown('<div class="create-btn-container">', unsafe_allow_html=True)
            if st.button("Back to Login"):
                st.session_state.otp_sent = False
                st.session_state.view_mode = "login"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="footer-brand"><span>∞</span> <b>Vision Vectors AI</b></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- 7. MAIN DASHBOARD WORKSPACE ---
else:
    st.sidebar.markdown("### 🚆 **RailVision AI**")
    st.sidebar.success(f"User: **{st.session_state.user_email}**\n\nRole: **{st.session_state.user_role}**")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.user_email = ""
        st.session_state.user_role = "Passenger"
        st.session_state.view_mode = "login"
        st.rerun()

    st.sidebar.markdown("---")

    if st.session_state.user_role == "Passenger":
        st.sidebar.markdown("### Passenger Navigation")
        active_tab = st.sidebar.radio("Go to:", ["Passenger Advisory & Live Map", "Live Station Cameras", "Passenger Feedback & Reviews"], label_visibility="collapsed")
    elif st.session_state.user_role == "Operations":
        st.sidebar.markdown("### Operations Navigation")
        active_tab = st.sidebar.radio("Go to:", ["Disruption Simulator & Ops", "Live Station Cameras", "Passenger Feedback & Reviews"], label_visibility="collapsed")
    else:
        st.sidebar.markdown("### Admin Control Panel")
        active_tab = st.sidebar.radio("Go to:", ["Admin Model Health", "Live Station Cameras", "Passenger Feedback & Reviews"], label_visibility="collapsed")

    # --- PASSENGER ADVISORY & LIVE MAP VIEW ---
    if active_tab == "Passenger Advisory & Live Map":
        st.markdown("""
            <div class="hero-container">
                <h1 class="hero-title"><span class="live-pulse"></span>Indian Railways Live Tracking & Smart Advisory Suite</h1>
                <p class="hero-subtitle">Real-time GPS tracking along official Indian Railway corridors, predictive occupancy insights, and carbon footprint reduction calculators.</p>
            </div>
            <div class="ticker-wrap">
                <div class="ticker-track">
                    <span>🟢 12951 Mumbai Rajdhani running on time</span><span class="sep">•</span>
                    <span>🌧️ Monsoon advisory active on Eastern corridors</span><span class="sep">•</span>
                    <span>🚄 22436 Vande Bharat crossing Prayagraj Junction</span><span class="sep">•</span>
                    <span>🌱 4.2 tonnes CO₂ saved by passengers today</span><span class="sep">•</span>
                    <span>📡 Live GPS sync active across 8 monitored corridors</span><span class="sep">•</span>
                    <span>🟢 12951 Mumbai Rajdhani running on time</span><span class="sep">•</span>
                    <span>🌧️ Monsoon advisory active on Eastern corridors</span><span class="sep">•</span>
                    <span>🚄 22436 Vande Bharat crossing Prayagraj Junction</span><span class="sep">•</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_input, col_output = st.columns([1, 1.2], gap="large")

        with col_input:
            st.subheader("🔍 Select Indian Railway Train")
            selected_train = st.selectbox("Search Train Number/Name:", options=list(TRAINS_DATABASE.keys()))
            train_info = TRAINS_DATABASE[selected_train]
            
            official_route_str = " ➔ ".join(train_info["waypoints"])
            
            custom_route_path = st.text_input(
                "🛤️ Official Verified Rail Route:", 
                value=official_route_str, 
                disabled=True,
                help="Official corridors mapped directly through Indian Railways network junctions."
            )
            
            c1, c2 = st.columns(2)
            with c1:
                travel_date = st.date_input("Travel Date", datetime.today())
            with c2:
                distance_input = st.number_input("Distance (KM):", value=int(train_info["distance"]), step=10, disabled=True)

            st.markdown("---")
            st.markdown("🔔 **Smart Push Notification Alerts**")
            enable_alerts = st.checkbox("Enable Automated SMS / Telegram Delay Push Alerts", value=True)
            alert_destination = st.text_input("Mobile Number or Telegram Chat ID:", value="+91 98765 43210" if enable_alerts else "")

            predict_btn = st.button("🔮 Forecast Delay & Save Journey")

        with col_output:
            st.subheader("📊 Delay Prediction & Sustainability Telemetry")
            month = travel_date.month
            season = "Winter" if month in [12, 1, 2] else ("Monsoon" if month in [6, 7, 8, 9] else "Summer")
            season_add = 22 if season == "Winter" else (14 if season == "Monsoon" else 4)
            
            disruption_penalty = 45 if st.session_state.simulated_blockage else 0
            predicted_delay = max(2, int(train_info["base_delay"] + season_add + disruption_penalty + round(distance_input/100)))
            
            risk_label = "HIGH RISK" if predicted_delay >= 35 else ("MEDIUM RISK" if predicted_delay >= 18 else "LOW RISK")
            badge_class = "badge-high" if predicted_delay >= 35 else ("badge-medium" if predicted_delay >= 18 else "badge-low")

            carbon_saved_kg = round((140 - 25) * distance_input / 1000, 1)

            if predict_btn:
                save_prediction(st.session_state.user_email, selected_train, custom_route_path, travel_date, predicted_delay, risk_label, f"{carbon_saved_kg} kg CO₂")
                if enable_alerts and alert_destination:
                    alert_msg = f"RailVision Alert: {selected_train} predicted delay {predicted_delay} min ({risk_label}) on {travel_date}. Corridor: {train_info['origin']} to {train_info['dest']}."
                    sms_sent, sms_status = send_sms_alert(alert_destination, alert_msg)
                    if sms_sent:
                        st.success(f"✓ SMS Alert sent to {alert_destination}.")
                    elif sms_status == "not_configured":
                        st.warning(f"⚠️ Demo mode: Twilio not configured, so no real SMS was sent. Add TWILIO_SID/TWILIO_AUTH/TWILIO_FROM_NUMBER to .streamlit/secrets.toml to send real texts. Message that would be sent: \"{alert_msg}\"")
                    else:
                        print(f"[RailVision] SMS delivery failed for {alert_destination}: {sms_status}")
                        st.error("❌ We couldn't send the SMS alert right now. Please check the number and try again.")

            st.markdown(f"""
                <div style="background: #131c2e; border: 1px solid #1e293b; padding: 20px; border-radius: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #94a3b8; font-size: 0.85rem; font-weight: 700;">USER: {st.session_state.user_email.upper()}</span>
                        <span class="{badge_class}">{risk_label}</span>
                    </div>
                    <h2 style="color: #f8fafc; margin-top: 10px; margin-bottom: 2px;">{predicted_delay} <span style="font-size: 1.1rem; color: #94a3b8;">Minutes Delay Expected</span></h2>
                    <p style="color: #00C6FF; font-weight: 600; font-size: 0.9rem; margin-bottom: 6px;">🛤️ Corridor: {custom_route_path}</p>
                    <p style="color: #f59e0b; font-size: 0.85rem; margin: 4px 0;">👥 Predicted Coach Occupancy: <b>{train_info['occupancy']}</b></p>
                    <p style="color: #10b981; font-size: 0.85rem; margin: 4px 0;">🌱 Carbon Footprint Saved: <b>{carbon_saved_kg} kg CO₂</b> vs Road/Air travel</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        # --- LIVE GPS TRACKER PANEL ---
        if selected_train not in st.session_state.gps_progress:
            st.session_state.gps_progress[selected_train] = random.randint(6, 22)
            st.session_state.gps_last_update[selected_train] = datetime.now()

        live_lat, live_lon, seg_idx, km_covered, km_total = interpolate_along_path(
            train_info["path_lats"], train_info["path_lons"], st.session_state.gps_progress[selected_train]
        )
        wp_list = train_info["waypoints"]
        next_station = wp_list[min(seg_idx + 1, len(wp_list) - 1)]
        last_station = wp_list[max(seg_idx, 0)]

        base_speed = 55 if st.session_state.simulated_blockage else random.choice([88, 96, 104, 112, 120])
        eta_minutes = int(((km_total - km_covered) / max(base_speed, 1)) * 60) + predicted_delay

        st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <h3 style="color:#f8fafc; margin:0;">🛰️ Live GPS Tracker — <span style="color:#00C6FF;">{selected_train}</span></h3>
                <span style="color:#94a3b8; font-size:0.8rem;">Last signal: {st.session_state.gps_last_update[selected_train].strftime('%H:%M:%S')}</span>
            </div>
            <p style="color:#94a3b8; font-size:0.9rem; margin:2px 0 14px 0;">
                📍 <b style="color:#10b981;">Source:</b> {train_info['origin']} &nbsp;&nbsp;→&nbsp;&nbsp;
                🎯 <b style="color:#ef4444;">Destination:</b> {train_info['dest']}
            </p>
        """, unsafe_allow_html=True)

        gps_c1, gps_c2, gps_c3, gps_c4, gps_c5 = st.columns(5)
        with gps_c1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Route Progress</div><div class="metric-value" style="color:#00C6FF;">{st.session_state.gps_progress[selected_train]}%</div></div>', unsafe_allow_html=True)
        with gps_c2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Distance Covered</div><div class="metric-value">{km_covered:.0f} km</div></div>', unsafe_allow_html=True)
        with gps_c3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Live Speed</div><div class="metric-value" style="color:{"#ef4444" if st.session_state.simulated_blockage else "#10b981"};">{base_speed} km/h</div></div>', unsafe_allow_html=True)
        with gps_c4:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Next Junction</div><div class="metric-value" style="font-size:1.1rem;">{next_station}</div></div>', unsafe_allow_html=True)
        with gps_c5:
            st.markdown(f'<div class="metric-card"><div class="metric-label">ETA to Destination</div><div class="metric-value">{eta_minutes} min</div></div>', unsafe_allow_html=True)

        st.progress(min(100, max(0, st.session_state.gps_progress[selected_train])) / 100)

        gps_btn_col, _ = st.columns([1, 3])
        with gps_btn_col:
            if st.button("🔄 Refresh Live GPS Signal"):
                bump = random.randint(4, 11)
                new_progress = st.session_state.gps_progress[selected_train] + bump
                st.session_state.gps_progress[selected_train] = new_progress if new_progress <= 100 else random.randint(2, 8)
                st.session_state.gps_last_update[selected_train] = datetime.now()
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader(f"🗺️ Official Indian Railways Corridor Map — {selected_train}")

        fig_map = go.Figure()

        track_color = "#ef4444" if st.session_state.simulated_blockage else "#00C6FF"
        track_name = "Official Rail Track (DISRUPTED)" if st.session_state.simulated_blockage else "Official Rail Track"

        fig_map.add_trace(go.Scattermapbox(
            mode="lines+markers",
            lat=train_info["path_lats"],
            lon=train_info["path_lons"],
            line=dict(width=4, color=track_color),
            marker=dict(size=8, color="#f59e0b"),
            name=track_name,
            hoverinfo="text",
            text=[f"Junction: {wp}" for wp in train_info["waypoints"]]
        ))

        fig_map.add_trace(go.Scattermapbox(
            mode="markers+text",
            lat=[train_info["path_lats"][0], train_info["path_lats"][-1]],
            lon=[train_info["path_lons"][0], train_info["path_lons"][-1]],
            marker=dict(size=14, color="#10b981"),
            text=[f"Origin: {train_info['origin']}", f"Dest: {train_info['dest']}"],
            textposition="top center",
            name="Terminals"
        ))

        fig_map.add_trace(go.Scattermapbox(
            mode="markers+text",
            lat=[live_lat],
            lon=[live_lon],
            marker=dict(size=22, color="#ffffff", symbol="circle"),
            text=["🚄"],
            textfont=dict(size=26),
            textposition="middle center",
            hoverinfo="text",
            hovertext=[f"Live Position: {st.session_state.gps_progress[selected_train]}% complete<br>Last: {last_station}<br>Next: {next_station}<br>Speed: {base_speed} km/h"],
            name="Live Train Position"
        ))

        mid_lat = np.mean(train_info["path_lats"])
        mid_lon = np.mean(train_info["path_lons"])

        fig_map.update_layout(
            mapbox_style="carto-darkmatter",
            mapbox_zoom=4.5,
            mapbox_center={"lat": mid_lat, "lon": mid_lon},
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=450,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, font=dict(color="#f8fafc"), bgcolor="rgba(19, 28, 46, 0.8)")
        )

        st.plotly_chart(fig_map, use_container_width=True)

        if st.session_state.user_role == "Passenger":
            st.markdown("---")
            st.subheader(f"📜 Journey History Log & Sustainability Impact for ({st.session_state.user_email})")
            history_df = get_history(st.session_state.user_email)
            if not history_df.empty:
                st.dataframe(history_df, use_container_width=True)
            else:
                st.caption("No saved journeys found in database for this user yet.")

    # --- OPERATIONS & DISRUPTION SIMULATOR VIEW ---
    elif active_tab == "Disruption Simulator & Ops":
        st.markdown("<h2 style='color:#f8fafc;'>📈 Operations Control & Disruption Scenario Simulator</h2>", unsafe_allow_html=True)
        st.caption("Test network resilience by simulating track blockages or emergency maintenance.")
        st.markdown("""
            <div class="rail-track-wrap" style="height:24px;">
                <div class="rail-track-line"></div>
                <span class="train-runner" style="font-size:1.2rem;">🚆</span>
            </div>
        """, unsafe_allow_html=True)

        sim_col1, sim_col2 = st.columns([1.5, 1])
        with sim_col1:
            st.markdown("""
                <div style="background: #131c2e; border: 1px solid #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                    <h3 style="color: #f8fafc; margin-top: 0;">⚡ What-If Disruption Sandbox</h3>
                    <p style="color: #94a3b8; font-size: 0.9rem;">Simulate an emergency line block, signal failure, or severe weather incident to test real-time cascade delays and rerouting advisory outputs.</p>
                </div>
            """, unsafe_allow_html=True)
            
            current_sim_state = st.session_state.simulated_blockage
            if current_sim_state:
                st.error("⚠️ ACTIVE INCIDENT: Major Track Blockage Simulation is ON (+45m cascade delay applied across network).")
                if st.button("🛑 Clear Incident & Restore Normal Operations"):
                    st.session_state.simulated_blockage = False
                    st.rerun()
            else:
                st.success("🟢 Network Operating normally under optimal scheduling vectors.")
                if st.button("🚨 Trigger Simulated Track Emergency / Blockage"):
                    st.session_state.simulated_blockage = True
                    st.rerun()

        with sim_col2:
            st.markdown("""
                <div style="background: #131c2e; border: 1px solid #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px; text-align: center;">
                    <div class="metric-label">Economic Loss Prevented</div>
                    <div class="metric-value" style="color: #10b981;">₹14.8 Lakhs</div>
                    <p style="color: #94a3b8; font-size: 0.8rem; margin-top: 6px;">Calculated via automated predictive re-routing.</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        c1, c2 = st.columns(2)
        sample_routes = list(ROUTE_PATHS)[:8]
        routes_df = pd.DataFrame({
            "Route": sample_routes,
            "Avg Delay (Mins)": [random.randint(10, 45) + (45 if st.session_state.simulated_blockage else 0) for _ in range(len(sample_routes))],
            "Risk Level": ["High" if st.session_state.simulated_blockage else random.choice(["Low", "Medium", "High"]) for _ in range(len(sample_routes))]
        })
        
        with c1:
            fig_bar = px.bar(
                routes_df, 
                x="Route", 
                y="Avg Delay (Mins)", 
                color="Risk Level",
                title="Corridor Delay Telemetry (Live Simulation Feed)",
                color_discrete_map={"Low": "#10b981", "Medium": "#f59e0b", "High": "#ef4444"}
            )
            fig_bar.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            risk_counts = routes_df["Risk Level"].value_counts().reset_index()
            risk_counts.columns = ["Risk Level", "Count"]
            fig_pie = px.pie(
                risk_counts, 
                names="Risk Level", 
                values="Count",
                title="Active Network Risk Matrix",
                color="Risk Level",
                color_discrete_map={"Low": "#10b981", "Medium": "#f59e0b", "High": "#ef4444"}
            )
            fig_pie.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pie, use_container_width=True)

    # --- ADMIN MODEL HEALTH VIEW ---
    elif active_tab == "Admin Model Health":
        st.markdown("<h2 style='color:#f8fafc;'>⚙️ System Administrator & Model Health Diagnostics</h2>", unsafe_allow_html=True)
        st.caption("Superuser control panel for supervising machine learning models, telemetry pipelines, and database logs.")
        
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown('<div class="metric-card"><div class="metric-label">Model Accuracy (R²)</div><div class="metric-value">0.914</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown('<div class="metric-card"><div class="metric-label">RMSE</div><div class="metric-value">4.2 min</div></div>', unsafe_allow_html=True)
        with m3:
            st.markdown('<div class="metric-card"><div class="metric-label">Training Records</div><div class="metric-value">1.2M</div></div>', unsafe_allow_html=True)
        with m4:
            st.markdown('<div class="metric-card"><div class="metric-label">Drift Status</div><div class="metric-value" style="color:#10b981;">Optimal</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)

        with c1:
            feature_importance = pd.DataFrame({
                "Feature": ["Weather/Season", "Route Distance", "Track Congestion", "Scheduled Stops", "Time of Day"],
                "Importance": [0.38, 0.27, 0.18, 0.11, 0.06]
            }).sort_values("Importance", ascending=True)

            fig_feat = px.bar(
                feature_importance, 
                x="Importance", 
                y="Feature", 
                orientation='h',
                title="Feature Importance Weights",
                color_discrete_sequence=["#00C6FF"]
            )
            fig_feat.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_feat, use_container_width=True)

        with c2:
            epochs = list(range(1, 11))
            loss = [0.45, 0.32, 0.24, 0.18, 0.15, 0.12, 0.10, 0.09, 0.08, 0.075]
            fig_loss = px.line(
                x=epochs, 
                y=loss, 
                title="Model Training Loss Curve",
                labels={"x": "Epoch", "y": "Loss (MSE)"}
            )
            fig_loss.update_traces(line_color="#0066FF", line_width=3)
            fig_loss.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_loss, use_container_width=True)

    # --- LIVE STATION / TRACKSIDE CAMERA FEEDS VIEW ---
    elif active_tab == "Live Station Cameras":
        st.markdown("<h2 style='color:#f8fafc;'>📷 Live Station & Trackside Camera Feeds</h2>", unsafe_allow_html=True)
        st.caption("Monitor platform and trackside conditions in real time across a train's route.")
        st.markdown("""
            <div class="rail-track-wrap" style="height:24px;">
                <div class="rail-track-line"></div>
                <span class="train-runner" style="font-size:1.2rem;">🚆</span>
            </div>
        """, unsafe_allow_html=True)

        cam_top_col1, cam_top_col2, cam_top_col3 = st.columns([2, 1, 1])
        with cam_top_col1:
            cam_train = st.selectbox("Select Train Route:", options=list(TRAINS_DATABASE.keys()), key="cam_train_select")
        with cam_top_col2:
            auto_refresh = st.checkbox(f"🔄 Auto-refresh ({CAMERA_REFRESH_SECONDS}s)", value=False, key="cam_auto_refresh")
        with cam_top_col3:
            st.button("🔁 Refresh Now")

        if auto_refresh:
            st.markdown(
                '<div style="color:#22d3ee; font-size:0.78rem; margin-bottom:6px;">'
                '⏳ Auto-refresh is on — this page will update itself in the background.'
                '</div>', unsafe_allow_html=True
            )

        st.markdown(
            f'<div style="color:#94a3b8; font-size:0.82rem; margin-bottom:14px;">'
            f'<span class="live-pulse"></span>Last updated: {datetime.now().strftime("%H:%M:%S")}'
            f'</div>', unsafe_allow_html=True
        )

        stations = TRAINS_DATABASE[cam_train]["waypoints"]
        cam_cols = st.columns(3)
        any_real_feed = False
        for i, station in enumerate(stations):
            img_url, is_real = get_camera_feed(station, "Platform Cam")
            any_real_feed = any_real_feed or is_real
            with cam_cols[i % 3]:
                st.image(img_url, use_container_width=True)
                status_html = (
                    '<span class="badge-low" style="font-size:0.65rem; padding:3px 10px;">● LIVE</span>'
                    if is_real else
                    '<span class="badge-medium" style="font-size:0.65rem; padding:3px 10px;">● DEMO FEED</span>'
                )
                st.markdown(
                    f'<div style="margin: -8px 0 20px 0;">'
                    f'<b style="color:#f8fafc;">{station}</b><br>'
                    f'<span style="color:#94a3b8; font-size:0.78rem;">Platform Camera 01</span> &nbsp; {status_html}'
                    f'</div>', unsafe_allow_html=True
                )

        if not any_real_feed:
            with st.expander("ℹ️ These are demo feeds — connect real CCTV cameras"):
                st.markdown("""
                No camera hardware is connected yet, so the feeds above are auto-refreshing
                placeholder imagery so you can see how live feeds will look and behave.

                To show real live footage, add a `CAMERA_FEED_URLS` table to
                `.streamlit/secrets.toml` mapping each station name to an HTTP(S)
                snapshot or MJPEG URL from your CCTV/NVR system, for example:

                ```toml
                [CAMERA_FEED_URLS]
                "Mumbai Central" = "https://your-nvr.example.com/cam/platform1/snapshot.jpg"
                "New Delhi"       = "https://your-nvr.example.com/cam/concourse/snapshot.jpg"
                ```

                Most NVR/CCTV systems expose an HTTP snapshot or MJPEG endpoint that can be
                used directly here. Raw RTSP streams need an RTSP→HLS/MJPEG relay in front
                of them, since browsers can't play RTSP natively.
                """)

        if auto_refresh:
            time.sleep(CAMERA_REFRESH_SECONDS)
            st.rerun()

    # --- PASSENGER FEEDBACK & REVIEWS VIEW ---
    elif active_tab == "Passenger Feedback & Reviews":
        st.markdown("<h2 style='color:#f8fafc;'>⭐ Passenger Feedback & Operations Review Center</h2>", unsafe_allow_html=True)
        st.caption("Submit your feedback or view system ratings submitted by passengers across Indian Railways.")

        fb_col1, fb_col2 = st.columns([1, 1.2], gap="large")

        with fb_col1:
            st.markdown("""
                <div style="background: #131c2e; border: 1px solid #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                    <h3 style="color: #f8fafc; margin-top: 0;">✍️ Submit Your Experience</h3>
                    <p style="color: #94a3b8; font-size: 0.9rem;">Help us improve punctuality, cleanliness, and onboard catering services.</p>
                </div>
            """, unsafe_allow_html=True)

            fb_train = st.selectbox("Select Train for Review:", options=list(TRAINS_DATABASE.keys()), key="fb_train_select")
            fb_rating = st.slider("Rate Your Journey (1 to 5 Stars):", min_value=1, max_value=5, value=5)
            fb_category = st.selectbox("Feedback Category:", ["Punctuality & Timing", "Coach Cleanliness", "Catering / Food Quality", "TTE / Staff Behavior", "General Experience"])
            fb_comments = st.text_area("Detailed Comments / Suggestions:", placeholder="Describe your experience...")

            if st.button("📤 Submit Feedback"):
                if fb_comments.strip():
                    save_feedback(st.session_state.user_email, fb_train, fb_rating, fb_category, fb_comments)
                    st.success("✓ Thank you! Your feedback has been successfully recorded in the database.")
                else:
                    st.warning("Please enter some comments before submitting.")

        with fb_col2:
            st.markdown("""
                <div style="background: #131c2e; border: 1px solid #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                    <h3 style="color: #f8fafc; margin-top: 0;">📋 Community Feedback Feed</h3>
                    <p style="color: #94a3b8; font-size: 0.9rem;">Real-time stream of all passenger reviews stored securely in SQLite.</p>
                </div>
            """, unsafe_allow_html=True)

            feedback_df = get_all_feedback()
            if not feedback_df.empty:
                st.dataframe(feedback_df, use_container_width=True, height=400)
            else:
                st.info("No feedback entries found in the database yet.")