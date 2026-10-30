import hashlib
import secrets
from datetime import datetime, timedelta

def user(conn, request):
    auth_header = request.get('headers', {}).get('authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:]
    c = conn.cursor()
    c.execute('SELECT user_id, expires FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    if row is None:
        return None
    expires = datetime.fromisoformat(row['expires'])
    if expires < datetime.utcnow():
        c.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        return None
    user_id = row['user_id']
    c.execute('SELECT id, email, role FROM users WHERE id = ?', (user_id,))
    user_row = c.fetchone()
    if user_row is None:
        return None
    return {'id': user_row['id'], 'email': user_row['email'], 'role': user_row['role']}

def routes(conn, request):
    method = request.get('method', '')
    path = request.get('path', '')
    body = request.get('body', {})

    if path == '/health' and method == 'GET':
        return {'status': 200, 'body': {'ok': True, 'demo': True}}

    if path == '/register' and method == 'POST':
        email = body.get('email', '')
        password = body.get('password', '')
        if not email or not password:
            return {'status': 400, 'body': {'error': 'Email and password are required.'}}
        email = email.strip().lower()
        if len(email) > 160 or '@' not in email:
            return {'status': 400, 'body': {'error': 'Invalid email format.'}}
        if len(password) < 10 or len(password) > 128:
            return {'status': 400, 'body': {'error': 'Password must be between 10 and 128 characters.'}}
        if not isinstance(email, str) or not isinstance(password, str):
            return {'status': 400, 'body': {'error': 'Invalid input types.'}}

        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE email = ?', (email,))
        if c.fetchone() is not None:
            return {'status': 409, 'body': {'error': 'Email already registered.'}}

        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        c.execute('INSERT INTO users (email, password, salt, role) VALUES (?, ?, ?, ?)', (email, hashed, salt, 'user'))
        c.execute('SELECT id, email, role FROM users WHERE email = ?', (email,))
        user_row = c.fetchone()
        user_id = user_row['id']

        token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(hours=24)
        c.execute('INSERT INTO sessions (token, user_id, expires) VALUES (?, ?, ?)', (token, user_id, expires.isoformat()))
        conn.commit()
        return {'status': 201, 'body': {'token': token, 'user': {'id': user_id, 'email': email, 'role': 'user'}}}

    if path == '/login' and method == 'POST':
        email = body.get('email', '')
        password = body.get('password', '')
        if not email or not password:
            return {'status': 400, 'body': {'error': 'Email and password are required.'}}
        if not isinstance(email, str) or not isinstance(password, str):
            return {'status': 400, 'body': {'error': 'Invalid input types.'}}
        email = email.strip().lower()

        c = conn.cursor()
        c.execute('SELECT id, email, password, salt, role FROM users WHERE email = ?', (email,))
        row = c.fetchone()
        if row is None:
            return {'status': 401, 'body': {'error': 'Invalid credentials.'}}
        stored_hash = row['password']
        salt = row['salt']
        computed_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        if computed_hash != stored_hash:
            return {'status': 401, 'body': {'error': 'Invalid credentials.'}}

        token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(hours=24)
        c.execute('INSERT INTO sessions (token, user_id, expires) VALUES (?, ?, ?)', (token, row['id'], expires.isoformat()))
        conn.commit()
        return {'status': 200, 'body': {'token': token, 'user': {'id': row['id'], 'email': row['email'], 'role': row['role']}}}

    if path == '/logout' and method == 'POST':
        auth_header = request.get('headers', {}).get('authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        token = auth_header[7:]
        c = conn.cursor()
        c.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        return {'status': 200, 'body': {}}

    if path == '/me' and method == 'GET':
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        return {'status': 200, 'body': {'user': u}}

    return None
