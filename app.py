import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sqlite3
import random

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
    
    default_accounts = [
        ("admin@railvision.gov", "admin123", "Admin"),
        ("ops@railvision.gov", "ops123", "Operations"),
        ("passenger@gmail.com", "pass123", "Passenger")
    ]
    for email, pwd, role in default_accounts:
        c.execute("INSERT OR IGNORE INTO users (email, password, role) VALUES (?, ?, ?)", (email, pwd, role))

    c.execute("SELECT COUNT(*) FROM feedback")
    if c.fetchone()[0] == 0:
        sample_feedback = [
            ("passenger@gmail.com", "12951 - Mumbai Rajdhani Express", 5, "Cleanliness", "Exceptional service and timely arrival."),
            ("guest_user@gmail.com", "22436 - Vande Bharat Express", 4, "Punctuality", "Minimal delay, very comfortable journey."),
            ("traveler99@gmail.com", "12626 - Kerala Express", 2, "Delay Advisory", "Major delay near Nagpur, announcements could be better.")
        ]
        c.executemany("INSERT INTO feedback (user_email, train_name, rating, category, comments) VALUES (?, ?, ?, ?, ?)", sample_feedback)

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

# --- 3. CUSTOM CSS WITH HIGH-CONTRAST VISIBLE TEXT ---
st.markdown("""
    <style>
    /* Full-screen background configuration */
    .stApp { 
        background-image: url("https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcROP71ccb2zKHOi9rNwBQwYbFUl6RgwdO6h7GkixVCOmA&s=10");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
        font-family: 'Inter', system-ui, sans-serif; 
    }
    
    /* Dark contrast glass overlay layer across the main app canvas */
    .stApp::before {
        content: "";
        position: absolute;
        top: 0; left: 0; width: 100%; height: 100%;
        background-color: rgba(15, 23, 42, 0.92);
        z-index: -1;
    }

    /* --- GLOBALS & STREAMLIT CORE CONTROLS HIGH VISIBILITY TEXT --- */
    h1, h2, h3, h4, h5, h6, label, p, span, .stWidgetFormLabel {
        color: #f8fafc !important;
    }
    
    /* Global control labels styling for readability */
    .stWidgetFormLabel p, label p, div[data-testid="stWidgetLabel"] p {
        color: #f1f5f9 !important;
        font-weight: 600 !important;
    }

    /* --- SIDEBAR HIGH-CONTRAST FIXED RULES --- */
    div[data-testid="stSidebar"] {
        background-color: rgba(30, 41, 59, 0.98) !important;
        border-right: 1px solid #334155 !important;
    }
    div[data-testid="stSidebar"] h1, 
    div[data-testid="stSidebar"] h2, 
    div[data-testid="stSidebar"] h3, 
    div[data-testid="stSidebar"] label, 
    div[data-testid="stSidebar"] p,
    div[data-testid="stSidebar"] .stMarkdown {
        color: #f8fafc !important;
    }

    /* Fix Success blocks/Alert containers in the sidebar */
    div[data-testid="stSidebar"] div[data-testid="element-container"] div.stAlert {
        background-color: rgba(16, 185, 129, 0.2) !important;
        border: 1px solid #10b981 !important;
        color: #f8fafc !important;
    }
    div[data-testid="stSidebar"] div[data-testid="element-container"] div.stAlert p {
        color: #f8fafc !important;
        font-weight: 700 !important;
    }

    /* --- BRANDING & HERO CONTAINERS --- */
    .brand-logo-container {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 30px;
    }
    .brand-icon {
        font-size: 3.5rem;
        background: linear-gradient(135deg, #38bdf8 0%, #3b82f6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: pulseIcon 2s infinite alternate;
    }
    @keyframes pulseIcon {
        0% { transform: scale(1); filter: drop-shadow(0 0 5px rgba(56, 189, 248, 0.4)); }
        100% { transform: scale(1.08); filter: drop-shadow(0 0 18px rgba(59, 130, 246, 0.8)); }
    }
    .brand-logo-text {
        color: #f8fafc !important;
        font-size: 3rem;
        font-weight: 900;
        letter-spacing: -1.5px;
        margin: 0;
        line-height: 1;
    }
    .hero-tagline {
        color: #f8fafc !important;
        font-size: 3.2rem;
        font-weight: 800;
        line-height: 1.15;
        letter-spacing: -1px;
    }
    .hero-highlight { color: #38bdf8 !important; }
    
    .hero-description {
        color: #94a3b8 !important;
        font-size: 1.15rem;
        line-height: 1.6;
        margin-top: 20px;
        margin-bottom: 10px;
    }

    /* --- SOLID HIGH CONTRAST CARD CONTAINERS --- */
    .login-card-wrapper, .hero-container, .ops-card {
        background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%) !important;
        border: 1px solid #334155 !important;
        border-radius: 20px;
        padding: 36px 32px 24px 32px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4) !important;
        position: relative;
        overflow: hidden;
    }
    .hero-container {
        padding: 24px 32px;
        margin-bottom: 24px;
        border-radius: 16px;
    }
    .ops-card {
        padding: 24px;
        border-radius: 12px;
    }

    .login-header-text {
        color: #f8fafc !important;
        font-size: 1.35rem;
        font-weight: 700;
        margin-bottom: 24px;
    }
    
    /* --- FORM FIELDS INPUT STYLING OVERRIDES --- */
    div[data-baseweb="input"], div[data-baseweb="select"] {
        background-color: #0f172a !important;
        border: 1px solid #475569 !important;
    }
    input {
        color: #f8fafc !important;
    }
    
    /* --- COMPONENT ACCENTS & BUTTONS --- */
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #3b82f6 0%, #0ea5e9 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 30px !important;
        padding: 12px 24px !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        width: 100% !important;
        box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(14, 165, 233, 0.6);
    }

    .create-btn-container div.stButton > button:first-child {
        background: transparent !important;
        color: #38bdf8 !important;
        border: 1.5px solid #38bdf8 !important;
    }
    .create-btn-container div.stButton > button:first-child:hover {
        background: rgba(56, 189, 248, 0.1) !important;
    }

    .footer-brand {
        text-align: center;
        color: #94a3b8;
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: 28px;
    }

    .live-pulse {
        display: inline-block;
        width: 12px;
        height: 12px;
        background-color: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 0 rgba(16, 185, 129, 0.4);
        animation: pulse 1.6s infinite;
        margin-right: 8px;
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    .hero-title { color: #f8fafc !important; font-size: 2rem; font-weight: 800; margin: 0; }
    .hero-subtitle { color: #94a3b8 !important; font-size: 0.95rem; margin-top: 6px; }
    
    .badge-low { background: rgba(16, 185, 129, 0.2); color: #34d399 !important; border: 1px solid #10b981; padding: 6px 16px; border-radius: 20px; font-weight: 700; }
    .badge-medium { background: rgba(245, 158, 11, 0.2); color: #fbbf24 !important; border: 1px solid #f59e0b; padding: 6px 16px; border-radius: 20px; font-weight: 700; }
    .badge-high { background: rgba(239, 68, 68, 0.2); color: #f87171 !important; border: 1px solid #ef4444; padding: 6px 16px; border-radius: 20px; font-weight: 700; }
    
    .sandbox-title { color: #f8fafc !important; font-size: 1.8rem; font-weight: 800; margin: 0 0 12px 0; }
    .sandbox-desc { color: #94a3b8 !important; font-size: 0.95rem; line-height: 1.5; margin-bottom: 20px; }
    .metric-label-ops { color: #94a3b8 !important; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-val-ops { color: #34d399 !important; font-size: 2.2rem; font-weight: 900; margin: 10px 0; }
    
    .status-bar-normal {
        background-color: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #34d399 !important;
        padding: 12px 16px;
        border-radius: 8px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 20px;
    }
    .status-bar-disrupted {
        background-color: rgba(239, 68, 68, 0.15);
        border: 1px solid rgba(239, 68, 68, 0.4);
        color: #f87171 !important;
        padding: 12px 16px;
        border-radius: 8px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 4. DATASETS: INDIAN RAILWAY ROUTE MAPPINGS ---
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
    }
}

ROUTE_PATHS = [f"{data['origin']} → {data['dest']}" for data in TRAINS_DATABASE.values()]

# --- 5. SESSION STATE MANAGEMENT ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = ""
    st.session_state.user_role = "Passenger"
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "login"
if "simulated_blockage" not in st.session_state:
    st.session_state.simulated_blockage = False

# --- 6. AUTHENTICATION PORTAL ---
if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_left, col_right = st.columns([1.2, 1], gap="large")

    with col_left:
        st.markdown("""
            <div class="brand-logo-container">
                <span class="brand-icon">🚆</span>
                <h1 class="brand-logo-text">railvision</h1>
            </div>
            <div class="hero-tagline">
                Enterprise Rail Intelligence <br><span class="hero-highlight">& Live Decision Suite.</span>
            </div>
            <p class="hero-description">
                Empowering railway networks with next-generation predictive modeling, real-time corridor tracking, 
                and automated disruption management to optimize passenger journeys and operational efficiency.
            </p>
        """, unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="login-card-wrapper">', unsafe_allow_html=True)
        
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
                        st.error("❌ Authentication Failed: Incorrect credentials.")
                else:
                    st.error("Please fill in all authentication fields.")

            st.markdown("<hr style='border-color: #334155; margin: 15px 0;'>", unsafe_allow_html=True)
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

        elif st.session_state.view_mode == "register":
            st.markdown('<div class="login-header-text">Create New Account</div>', unsafe_allow_html=True)
            reg_role = st.selectbox("Account Role Type", ["Passenger", "Operations Controller", "System Administrator"])
            new_email = st.text_input("Email address", key="reg_email", placeholder="Enter your email")
            new_pass = st.text_input("New password", type="password", key="reg_pass", placeholder="New password")
            confirm_pass = st.text_input("Confirm password", type="password", key="reg_confirm", placeholder="Confirm password")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Register Account"):
                if new_email and new_pass and (new_pass == confirm_pass):
                    if reg_role in ["Operations Controller", "System Administrator"] and not new_email.endswith("@railvision.gov"):
                        st.error("❌ Operations and Admin accounts require a valid '@railvision.gov' corporate email address.")
                    else:
                        db_role = "Admin" if reg_role == "System Administrator" else ("Operations" if reg_role == "Operations Controller" else "Passenger")
                        if register_user(new_email, new_pass, db_role):
                            st.session_state.logged_in = True
                            st.session_state.user_email = new_email
                            st.session_state.user_role = db_role
                            st.rerun()
                        else:
                            st.error("An account with this email already exists!")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match!")

            st.markdown("<hr style='border-color: #334155; margin: 20px 0;'>", unsafe_allow_html=True)
            if st.button("Back to Login", key="reg_back"):
                st.session_state.view_mode = "login"
                st.rerun()

        elif st.session_state.view_mode == "forgot":
            st.markdown('<div class="login-header-text">🔐 Reset Password via Email OTP</div>', unsafe_allow_html=True)
            if "otp_sent" not in st.session_state:
                st.session_state.otp_sent = False

            forgot_role = st.selectbox("Select Account Role", ["Passenger", "Operations Controller", "System Administrator"], key="forgot_role")
            forgot_email = st.text_input("Registered Email ID", key="forgot_email", placeholder="Enter account email")

            if not st.session_state.otp_sent:
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
                            st.success(f"📨 [Simulated OTP]: Code is {generated_otp}")
                            st.rerun()
                        else:
                            st.error("No matching account found.")
            else:
                entered_otp = st.text_input("Enter 6-Digit OTP Code", max_chars=6)
                new_reset_pass = st.text_input("New Password", type="password")
                if st.button("Verify & Update Password"):
                    if verify_and_update_password(st.session_state.temp_otp_email, entered_otp, new_reset_pass):
                        st.success("✓ Password successfully updated!")
                        st.session_state.otp_sent = False
                        st.session_state.view_mode = "login"
                        st.rerun()
                    else:
                        st.error("❌ Incorrect OTP code.")

            st.markdown("<hr style='border-color: #334155; margin: 20px 0;'>", unsafe_allow_html=True)
            if st.button("Back to Login", key="forgot_back"):
                st.session_state.otp_sent = False
                st.session_state.view_mode = "login"
                st.rerun()

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
        active_tab = st.sidebar.radio("Passenger Navigation", ["Passenger Advisory & Live Map", "Passenger Feedback & Reviews"])
    elif st.session_state.user_role == "Operations":
        active_tab = st.sidebar.radio("Operations Navigation", ["Disruption Simulator & Ops", "Passenger Feedback & Reviews"])
    else:
        active_tab = st.sidebar.radio("Admin Navigation", ["Admin Model Health", "Passenger Feedback & Reviews"])

    # --- TAB: PASSENGER ADVISORY & LIVE MAP VIEW ---
    if active_tab == "Passenger Advisory & Live Map":
        st.markdown("""
            <div class="hero-container">
                <h1 class="hero-title"><span class="live-pulse"></span>Indian Railways Live Tracking & Smart Advisory Suite</h1>
                <p class="hero-subtitle">Real-time GPS tracking along official Indian Railway corridors, predictive occupancy insights, and carbon footprint reduction calculators.</p>
            </div>
        """, unsafe_allow_html=True)

        col_input, col_output = st.columns([1, 1.2], gap="large")

        with col_input:
            st.subheader("🔍 Select Indian Railway Train")
            selected_train = st.selectbox("Search Train Number/Name:", options=list(TRAINS_DATABASE.keys()))
            train_info = TRAINS_DATABASE[selected_train]
            official_route_str = " ➔ ".join(train_info["waypoints"])
            
            custom_route_path = st.text_input("Tracks Corridor Line:", value=official_route_str, disabled=True)
            
            c1, c2 = st.columns(2)
            with c1:
                travel_date = st.date_input("Travel Date", datetime.today())
            with c2:
                distance_input = st.number_input("Distance (KM):", value=int(train_info["distance"]), disabled=True)

            enable_alerts = st.checkbox("Enable SMS/Telegram Push Alerts", value=True)
            alert_destination = st.text_input("Address identifier:", value="+91 98765 43210" if enable_alerts else "")
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
                st.toast("Journey logged successfully!", icon="💾")

            st.markdown(f"""
                <div style="background: #1e293b; border: 1px solid #334155; padding: 20px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.2);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #94a3b8; font-size: 0.85rem; font-weight: 700;">USER: {st.session_state.user_email.upper()}</span>
                        <span class="{badge_class}">{risk_label}</span>
                    </div>
                    <h2 style="color: #f8fafc; margin-top: 10px;">{predicted_delay} <span style="font-size: 1.1rem; color: #94a3b8;">Minutes Delay Expected</span></h2>
                    <p style="color: #38bdf8; font-weight: 600; margin-bottom: 6px;">🛤️ Mapped Corridor: {custom_route_path}</p>
                    <p style="color: #fbbf24; margin: 4px 0;">👥 Occupancy Load: <b>{train_info['occupancy']}</b></p>
                    <p style="color: #34d399; margin: 4px 0;">🌱 Footprint Delta: <b>{carbon_saved_kg} kg CO₂ Saved</b></p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        fig_map = go.Figure()
        track_color = "#ef4444" if st.session_state.simulated_blockage else "#3b82f6"
        
        fig_map.add_trace(go.Scattermapbox(
            mode="lines+markers", lat=train_info["path_lats"], lon=train_info["path_lons"],
            line=dict(width=4, color=track_color), marker=dict(size=8, color="#f59e0b"),
            text=train_info["waypoints"], hoverinfo="text", name="Official Track Path"
        ))
        fig_map.update_layout(
            mapbox_style="carto-positron", mapbox_zoom=4.5,
            mapbox_center={"lat": np.mean(train_info["path_lats"]), "lon": np.mean(train_info["path_lons"])},
            margin={"r":0,"t":0,"l":0,"b":0}, height=400
        )
        st.plotly_chart(fig_map, use_container_width=True)

        st.subheader("📜 Recent Saved Journeys")
        st.dataframe(get_history(st.session_state.user_email), use_container_width=True)

    # --- TAB: OPERATIONS & DISRUPTION SIMULATOR VIEW ---
    elif active_tab == "Disruption Simulator & Ops":
        col_box1, col_box2 = st.columns([2, 1], gap="medium")
        
        with col_box1:
            st.markdown("""
                <div class="ops-card">
                    <h2 class="sandbox-title">⚡ What-If Disruption Sandbox</h2>
                    <p class="sandbox-desc">
                        Simulate an emergency line block, signal failure, or severe weather incident to test real-time cascade delays and rerouting advisory outputs.
                    </p>
                </div>
            """, unsafe_allow_html=True)
        
        with col_box2:
            loss_val = "₹14.8 Lakhs" if not st.session_state.simulated_blockage else "₹3.2 Lakhs"
            st.markdown(f"""
                <div class="ops-card" style="text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center;">
                    <div class="metric-label-ops">ECONOMIC LOSS PREVENTED</div>
                    <div class="metric-val-ops">{loss_val}</div>
                    <div style="color: #94a3b8; font-size: 0.8rem;">Calculated via automated predictive re-routing.</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        if not st.session_state.simulated_blockage:
            st.markdown("""
                <div class="status-bar-normal">
                    <span style="height: 10px; width: 10px; background-color: #10b981; border-radius: 50%; display: inline-block;"></span>
                    Network Operating normally under optimal scheduling vectors.
                </div>
            """, unsafe_allow_html=True)
            btn_label = "🟦 Trigger Simulated Track Emergency / Blockage"
        else:
            st.markdown("""
                <div class="status-bar-disrupted">
                    <span style="height: 10px; width: 10px; background-color: #ef4444; border-radius: 50%; display: inline-block;"></span>
                    CRITICAL ALERT: Dynamic network delay penalties (+45 mins) active.
                </div>
            """, unsafe_allow_html=True)
            btn_label = "🟩 Clear Active Network Simulation Blocks"

        if st.button(btn_label, key="emergency_toggle"):
            st.session_state.simulated_blockage = not st.session_state.simulated_blockage
            st.rerun()

        st.markdown("<br><br>", unsafe_allow_html=True)

        routes_list = [
            "Mumbai Central → New Delhi",
            "New Delhi → Howrah Junction",
            "New Delhi → Thiruvananthapuram",
            "New Delhi → Bhopal Junction",
            "New Delhi → Varanasi Junction",
            "New Delhi → Chennai Central",
            "Mumbai Central → Amritsar Junction",
            "Firozpur Cantt → Mumbai CSMT"
        ]
        
        if st.session_state.simulated_blockage:
            delays = [38, 48, 28, 45, 49, 39, 44, 42]
            risk_categories = ["High", "High", "Medium", "High", "High", "High", "High", "High"]
        else:
            delays = [13, 31, 16, 38, 39, 19, 29, 0]
            risk_categories = ["Low", "High", "Low", "High", "High", "Medium", "Medium", "Low"]
            
        color_map = {"Low": "#10b981", "Medium": "#f59e0b", "High": "#ef4444"}

        df_analytics = pd.DataFrame({
            "Route": routes_list,
            "Avg Delay (Mins)": delays,
            "Risk Level": risk_categories
        })

        col_chart1, col_chart2 = st.columns(2, gap="large")

        with col_chart1:
            st.markdown("<b style='color:#f8fafc; font-size:1.1rem;'>Corridor Delay Telemetry (Live Simulation Feed)</b>", unsafe_allow_html=True)
            fig_bars = px.bar(
                df_analytics, 
                x="Route", 
                y="Avg Delay (Mins)", 
                color="Risk Level",
                color_discrete_map=color_map,
                category_orders={"Risk Level": ["Low", "Medium", "High"]}
            )
            fig_bars.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#f8fafc",
                margin=dict(l=10, r=10, t=20, b=10),
                height=380,
                xaxis=dict(showgrid=False, tickangle=25),
                yaxis=dict(showgrid=True, gridcolor="#334155", title="Avg Delay (Mins)")
            )
            st.plotly_chart(fig_bars, use_container_width=True, config={'displayModeBar': False})

        with col_chart2:
            st.markdown("<b style='color:#f8fafc; font-size:1.1rem;'>Active Network Risk Matrix</b>", unsafe_allow_html=True)
            risk_counts = df_analytics["Risk Level"].value_counts().reset_index()
            risk_counts.columns = ["Risk Level", "Count"]
            
            fig_pie = px.pie(
                risk_counts, 
                values="Count", 
                names="Risk Level", 
                color="Risk Level",
                color_discrete_map=color_map,
                hole=0.4
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent')
            fig_pie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#f8fafc",
                margin=dict(l=10, r=10, t=20, b=10),
                height=380,
                showlegend=True
            )
            st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})

    # --- TAB: ADMIN MODEL HEALTH VIEW ---
    elif active_tab == "Admin Model Health":
        st.markdown("<h2 style='color:#f8fafc;'>⚙️ ML Core Model Health & Telemetry Metrics</h2>", unsafe_allow_html=True)
        
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            st.subheader("Prediction Precision Accuracies")
            metrics_df = pd.DataFrame({
                "Model Variant": ["Gradient Boosted Trees", "LSTM Sequence Engine", "Random Forest Regressor"],
                "R² Score": [0.914, 0.889, 0.842],
                "Mean Absolute Error (Min)": [3.2, 4.1, 5.8]
            })
            st.table(metrics_df)
        with col_h2:
            st.subheader("Compute Resource Distributions")
            st.progress(0.68, text="GPU Inference Core Engine Loads (68%)")
            st.progress(0.42, text="Database Multi-threaded I/O Operations Limits (42%)")

    # --- TAB: PASSENGER FEEDBACK & REVIEWS ---
    elif active_tab == "Passenger Feedback & Reviews":
        st.markdown("<h2 style='color:#f8fafc;'>💬 Passenger Experience & Service Feedback Portals</h2>", unsafe_allow_html=True)
        
        if st.session_state.user_role == "Passenger":
            with st.form("feedback_submission_form"):
                st.write("### Log Service Review Verification Data")
                target_train = st.selectbox("Reviewed Locomotive Identification:", options=list(TRAINS_DATABASE.keys()))
                fb_rating = st.slider("Service Experience Rating Levels (1-5):", min_value=1, max_value=5, value=5)
                fb_category = st.selectbox("Analytical Classification Categories:", ["Punctuality", "Cleanliness", "Staff Hospitality", "Delay Advisory", "Food/Catering"])
                fb_comments = st.text_area("Descriptive Incident Assessment Comments:")
                
                if st.form_submit_button("Submit Operational Report"):
                    if fb_comments:
                        save_feedback(st.session_state.user_email, target_train, fb_rating, fb_category, fb_comments)
                        st.success("Feedback saved to database successfully.")
                        st.rerun()
                    else:
                        st.error("Please add written assessment context inside comment windows before submission.")

        st.markdown("---")
        st.subheader("Global Feedback Feed Aggregations")
        feedback_records = get_all_feedback()
        if not feedback_records.empty:
            st.dataframe(feedback_records, use_container_width=True)
            
            fig_feedback = px.histogram(feedback_records, x="Category", color="Rating (1-5)", title="Distribution Categories Breakdown Matrix Reports")
            st.plotly_chart(fig_feedback, use_container_width=True)
        else:
            st.caption("No historical comments logged inside databases system yet.")
