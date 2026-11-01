import hashlib
import secrets
from datetime import datetime, timedelta
import db

def _constant_time_compare(a, b):
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0

def _normalize_email(email):
    if not email or not isinstance(email, str) or len(email) > 160:
        return None
    return email.strip().lower()

def _validate_password(password):
    if not password or not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        return False
    return True

def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()

def _create_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    conn.execute('INSERT INTO sessions (token, user_id, expires) VALUES (?, ?, ?)',
                 (token, user_id, expires))
    conn.commit()
    return token

def _get_user_from_token(conn, token):
    if not token:
        return None
    cur = conn.execute('SELECT u.id, u.email, u.role FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ? AND s.expires > ?',
                       (token, datetime.utcnow().isoformat()))
    row = cur.fetchone()
    if row:
        return {'id': row['id'], 'email': row['email'], 'role': row['role']}
    return None

def user(conn, request):
    auth_header = request.get('headers', {}).get('authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:]
    return _get_user_from_token(conn, token)

def routes(conn, request):
    path = request.get('path', '')
    method = request.get('method', '')

    # Health check is in catalog, not here
    if path == '/register' and method == 'POST':
        body = request.get('body', {})
        if not isinstance(body, dict):
            return {'status': 400, 'body': {'error': 'Invalid request body'}}
        email = _normalize_email(body.get('email'))
        password = body.get('password')
        if not email or not _validate_password(password):
            return {'status': 400, 'body': {'error': 'Invalid email or password (min 10 chars, max 128)'}}
        # Check duplicate
        cur = conn.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cur.fetchone():
            return {'status': 409, 'body': {'error': 'Email already registered'}}
        salt = secrets.token_hex(16)
        hashed = _hash_password(password, salt)
        cur = conn.execute('INSERT INTO users (email, password, salt, role) VALUES (?, ?, ?, \'user\')',
                          (email, hashed, salt))
        conn.commit()
        user_id = cur.lastrowid
        token = _create_session(conn, user_id)
        return {'status': 201, 'body': {'token': token, 'user': {'id': user_id, 'email': email, 'role': 'user'}}}

    elif path == '/login' and method == 'POST':
        body = request.get('body', {})
        if not isinstance(body, dict):
            return {'status': 400, 'body': {'error': 'Invalid request body'}}
        email = _normalize_email(body.get('email'))
        password = body.get('password')
        if not email or not password or not isinstance(password, str):
            return {'status': 400, 'body': {'error': 'Email and password required'}}
        cur = conn.execute('SELECT id, email, password, salt, role FROM users WHERE email = ?', (email,))
        row = cur.fetchone()
        if not row:
            return {'status': 401, 'body': {'error': 'Invalid credentials'}}
        hashed = _hash_password(password, row['salt'])
        if not _constant_time_compare(hashed, row['password']):
            return {'status': 401, 'body': {'error': 'Invalid credentials'}}
        token = _create_session(conn, row['id'])
        return {'status': 200, 'body': {'token': token, 'user': {'id': row['id'], 'email': row['email'], 'role': row['role']}}}

    elif path == '/logout' and method == 'POST':
        auth_user = user(conn, request)
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        auth_header = request.get('headers', {}).get('authorization', '')
        token = auth_header[7:]
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        return {'status': 200, 'body': {'ok': True}}

    elif path == '/me' and method == 'GET':
        auth_user = user(conn, request)
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        return {'status': 200, 'body': {'user': auth_user}}

    return None
