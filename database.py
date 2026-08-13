import sqlite3

def get_db_connection():
    conn = sqlite3.connect("railway.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            otp TEXT
        )
    ''')
    
    # Prediction history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS prediction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            train_number TEXT,
            route TEXT,
            travel_date TEXT,
            predicted_delay INTEGER,
            risk_category TEXT,
            carbon_saved TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Feedback table
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            train_name TEXT,
            rating INTEGER,
            category TEXT,
            comments TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Safe migration check: add user_email to prediction_history if missing in legacy DBs
    try:
        c.execute("ALTER TABLE prediction_history ADD COLUMN user_email TEXT;")
    except sqlite3.OperationalError:
        pass  # Column already exists
        
    conn.commit()
    conn.close()
