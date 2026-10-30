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
            expires TIMESTAMP NOT NULL
        );
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL,
            description TEXT NOT NULL,
            price INTEGER NOT NULL,
            capacity INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            UNIQUE(user_id, listing_id)
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
    seed_admin(conn)
    seed_listings(conn)
    conn.commit()
    return conn

def seed_admin(conn):
    c = conn.cursor()
    email = 'admin@example.test'
    password = 'DemoAdmin2028!'
    c.execute('SELECT id FROM users WHERE email = ?', (email,))
    if c.fetchone() is not None:
        return
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    c.execute('INSERT INTO users (email, password, salt, role) VALUES (?, ?, ?, ?)', (email, hashed, salt, 'admin'))

def seed_listings(conn):
    c = conn.cursor()
    listings = [
        (1, 'Casa do Rio', 'Lisbon', 'Portugal', 'Charming riverside apartment with stunning views.', 120, 2),
        (2, 'Alfama Hideaway', 'Lisbon', 'Portugal', 'Cozy studio in historic Alfama district.', 85, 2),
        (3, 'Chiado Loft', 'Lisbon', 'Portugal', 'Modern loft in vibrant Chiado neighborhood.', 150, 3),
        (4, 'Belém Tower Suite', 'Lisbon', 'Portugal', 'Luxurious suite near Belém Tower.', 200, 4),
        (5, 'Zen Garden House', 'Kyoto', 'Japan', 'Traditional house with private zen garden.', 180, 4),
        (6, 'Gion Machiya', 'Kyoto', 'Japan', 'Restored machiya in historic Gion district.', 250, 6),
        (7, 'Arashiyama Retreat', 'Kyoto', 'Japan', 'Peaceful retreat near bamboo grove.', 220, 3),
        (8, 'Philosopher’s Walk Studio', 'Kyoto', 'Japan', 'Charming studio along the canal.', 130, 2),
        (9, 'Nyhavn Apartment', 'Copenhagen', 'Denmark', 'Bright apartment overlooking Nyhavn harbor.', 190, 4),
        (10, 'Christianshavn Loft', 'Copenhagen', 'Denmark', 'Industrial-chic loft in Christianshavn.', 170, 3),
        (11, 'Royal Suite', 'Copenhagen', 'Denmark', 'Elegant suite near Amalienborg Palace.', 300, 6),
        (12, 'Old Town Charm', 'Edinburgh', 'Scotland', 'Historic flat on Royal Mile.', 140, 2),
        (13, 'Castle View Apartment', 'Edinburgh', 'Scotland', 'Apartment with Edinburgh Castle views.', 210, 4),
        (14, 'Stockbridge Cottage', 'Edinburgh', 'Scotland', 'Quaint cottage in leafy Stockbridge.', 160, 3),
        (15, 'Ribeira Riverside', 'Porto', 'Portugal', 'Colorful riverside house with terrace.', 110, 2),
        (16, 'Porto Wine Loft', 'Porto', 'Portugal', 'Loft in old port wine cellar district.', 140, 3),
        (17, 'Foz do Douro Penthouse', 'Porto', 'Portugal', 'Penthouse with ocean views.', 230, 5),
        (18, 'Preseren Square Flat', 'Ljubljana', 'Slovenia', 'Central flat overlooking Preseren Square.', 100, 2),
        (19, 'Ljubljanica River House', 'Ljubljana', 'Slovenia', 'House with private dock on the river.', 180, 4),
        (20, 'Tivoli Park Retreat', 'Ljubljana', 'Slovenia', 'Modern apartment near Tivoli Park.', 150, 3),
    ]
    c.executemany('INSERT OR IGNORE INTO listings (id, name, city, country, description, price, capacity) VALUES (?, ?, ?, ?, ?, ?, ?)', listings)
