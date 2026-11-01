import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta

def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            capacity INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, listing_id)
        );
        CREATE TABLE IF NOT EXISTS itineraries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            party INTEGER NOT NULL,
            total INTEGER NOT NULL,
            request_key TEXT NOT NULL,
            UNIQUE(user_id, request_key)
        );
    ''')

    # Seed demo admin
    admin_email = 'admin@example.test'
    admin_password = 'DemoAdmin2028!'
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', admin_password.encode(), salt.encode(), 100000).hex()
    c.execute('''
        INSERT OR IGNORE INTO users (email, password, salt, role)
        VALUES (?, ?, ?, 'admin')
    ''', (admin_email, hashed, salt))

    # Seed listings (18+ varied rich properties, stable IDs)
    listings = [
        (1, 'Lisbon Light Loft', 'Lisbon', 'Portugal', 'A bright loft in the heart of Alfama with stunning city views.', 120, 2),
        (2, 'Chiado Charm Suite', 'Lisbon', 'Portugal', 'Elegant suite near Chiado with classic Portuguese tiles.', 150, 3),
        (3, 'Riverside Retreat', 'Lisbon', 'Portugal', 'Modern apartment overlooking the Tagus River.', 200, 4),
        (4, 'Kyoto Zen House', 'Kyoto', 'Japan', 'Traditional machiya with private garden and tatami rooms.', 250, 4),
        (5, 'Arashiyama Bamboo Stay', 'Kyoto', 'Japan', 'Quiet guesthouse near the bamboo grove with hot spring bath.', 180, 2),
        (6, 'Gion Geisha Quarter Residence', 'Kyoto', 'Japan', 'Luxurious accommodation in the historic Gion district.', 350, 3),
        (7, 'Copenhagen Harbour Haven', 'Copenhagen', 'Denmark', 'Scandinavian design apartment in Nyhavn with canal view.', 220, 2),
        (8, 'Christiania Creative Loft', 'Copenhagen', 'Denmark', 'Unique artist loft in the Freetown Christiania area.', 160, 4),
        (9, 'Tivoli Garden View', 'Copenhagen', 'Denmark', 'Central apartment steps from Tivoli Gardens.', 190, 3),
        (10, 'Edinburgh Castle View', 'Edinburgh', 'Scotland', 'Historic apartment with direct views of Edinburgh Castle.', 180, 2),
        (11, 'Royal Mile Apartment', 'Edinburgh', 'Scotland', 'Charming flat on the Royal Mile with original features.', 210, 4),
        (12, 'Stockbridge Serenity', 'Edinburgh', 'Scotland', 'Peaceful retreat in the bohemian Stockbridge neighbourhood.', 140, 2),
        (13, 'Porto Riverside Villa', 'Porto', 'Portugal', 'Beautiful villa overlooking the Douro River and port cellars.', 170, 6),
        (14, 'Ribeira District Flat', 'Porto', 'Portugal', 'Cosy flat in the UNESCO-listed Ribeira district.', 130, 3),
        (15, 'Foz do Douro Modern', 'Porto', 'Portugal', 'Contemporary apartment near the Atlantic coast.', 200, 4),
        (16, 'Ljubljana Old Town Gem', 'Ljubljana', 'Slovenia', 'Central apartment with views of the Ljubljanica River.', 110, 2),
        (17, 'Tivoli Park Villa', 'Ljubljana', 'Slovenia', 'Spacious villa near Tivoli Park with mountain views.', 280, 8),
        (18, 'Metelkova Creative Studio', 'Ljubljana', 'Slovenia', 'Edgy artist studio in the alternative Metelkova district.', 90, 2),
        (19, 'Bairro Alto Penthouse', 'Lisbon', 'Portugal', 'Rooftop penthouse in the lively Bairro Alto with terrace.', 300, 5),
        (20, 'Philosopher\'s Path Cottage', 'Kyoto', 'Japan', 'Quaint cottage along the Philosopher\'s Path with cherry trees.', 200, 2),
    ]

    c.executemany('''
        INSERT OR IGNORE INTO listings (id, name, city, country, description, price, capacity, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    ''', listings)

    conn.commit()
    return conn
