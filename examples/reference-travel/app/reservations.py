import re
from datetime import datetime, timedelta
from auth import user as auth_user

def routes(conn, request):
    method = request.get('method', '')
    path = request.get('path', '')
    body = request.get('body', {})
    # Helper for quoting logic
    if path == '/quote' and method == 'POST':
        return handle_quote_public(conn, body)
    # Reservations for authenticated user
    if path == '/reservations' and method == 'POST':
        return handle_create_reservation(conn, request, body)
    if path == '/reservations' and method == 'GET':
        return handle_list_reservations(conn, request)
    # Single reservation by id
    if re.match(r'^/reservations/\d+$', path) and method == 'GET':
        res_id = int(path.split('/')[-1])
        return handle_get_reservation(conn, request, res_id)
    # Admin routes
    if path == '/admin/reservations' and method == 'GET':
        return handle_admin_list_reservations(conn, request)
    if path == '/admin/listings' and method == 'GET':
        return handle_admin_list_listings(conn, request)
    if re.match(r'^/admin/listings/\d+$', path) and method == 'PUT':
        listing_id = int(path.split('/')[-1])
        return handle_admin_update_listing(conn, request, listing_id, body)
    return None


def handle_quote_public(conn, body):
    # Quote is public: no auth check
    listing_id = body.get('listing_id')
    check_in = body.get('check_in')
    check_out = body.get('check_out')
    party = body.get('party')
    # Validate types: listing_id must be int or convertible; reject bool etc.
    if not isinstance(listing_id, (int, float)) or isinstance(listing_id, bool):
        return {'status': 400, 'body': {'error': 'Invalid listing_id.'}}
    listing_id = int(listing_id)
    if not isinstance(check_in, str) or not isinstance(check_out, str) or not isinstance(party, (int, float)) or isinstance(party, bool):
        return {'status': 400, 'body': {'error': 'Invalid input types.'}}
    # Must be int
    if not isinstance(party, int):
        if isinstance(party, float):
            if party != int(party):
                return {'status': 400, 'body': {'error': 'Party must be integer.'}}
            party = int(party)
        else:
            return {'status': 400, 'body': {'error': 'Party must be integer.'}}
    # Validate date format YYYY-MM-DD
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if not date_pattern.match(check_in) or not date_pattern.match(check_out):
        return {'status': 400, 'body': {'error': 'Dates must be YYYY-MM-DD.'}}
    try:
        ci = datetime.strptime(check_in, '%Y-%m-%d').date()
        co = datetime.strptime(check_out, '%Y-%m-%d').date()
    except ValueError:
        return {'status': 400, 'body': {'error': 'Invalid date.'}}
    today = datetime.utcnow().date()
    if ci < today:
        return {'status': 400, 'body': {'error': 'Check-in cannot be in the past.'}}
    if co <= ci:
        return {'status': 400, 'body': {'error': 'Check-out must be after check-in.'}}
    nights = (co - ci).days
    if nights > 30:
        return {'status': 400, 'body': {'error': 'Maximum stay is 30 nights.'}}
    if not isinstance(party, int) or party < 1 or party > 8:
        return {'status': 400, 'body': {'error': 'Party must be between 1 and 8.'}}
    # Fetch listing
    c = conn.cursor()
    c.execute('SELECT id, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
    row = c.fetchone()
    if row is None or row['active'] == 0:
        return {'status': 404, 'body': {'error': 'Listing not found or inactive.'}}
    if party > row['capacity']:
        return {'status': 400, 'body': {'error': 'Party exceeds capacity.'}}
    nightly = row['price']
    total = nightly * nights
    return {'status': 200, 'body': {'quote': {
        'listing_id': listing_id,
        'check_in': check_in,
        'check_out': check_out,
        'party': party,
        'nights': nights,
        'nightly': nightly,
        'total': total,
        'currency': 'EUR'
    }}}


def handle_create_reservation(conn, request, body):
    u = auth_user(conn, request)
    if u is None:
        return {'status': 401, 'body': {'error': 'Not authenticated.'}}
    listing_id = body.get('listing_id')
    check_in = body.get('check_in')
    check_out = body.get('check_out')
    party = body.get('party')
    request_key = body.get('request_key')
    if not listing_id or not check_in or not check_out or not party or not request_key:
        return {'status': 400, 'body': {'error': 'Missing required fields.'}}
    # Validate types
    if not isinstance(listing_id, (int, float)) or isinstance(listing_id, bool):
        return {'status': 400, 'body': {'error': 'Invalid listing_id.'}}
    listing_id = int(listing_id)
    if not isinstance(request_key, str) or len(request_key) < 8 or len(request_key) > 100:
        return {'status': 400, 'body': {'error': 'request_key must be 8-100 characters.'}}
    # Use quote validation logic (public)
    quote_resp = handle_quote_public(conn, {'listing_id': listing_id, 'check_in': check_in, 'check_out': check_out, 'party': party})
    if quote_resp['status'] != 200:
        return {'status': quote_resp['status'], 'body': quote_resp['body']}
    quote = quote_resp['body']['quote']
    total = quote['total']
    c = conn.cursor()
    # Check duplicate request_key for this user
    c.execute('SELECT id FROM reservations WHERE user_id = ? AND request_key = ?', (u['id'], request_key))
    if c.fetchone() is not None:
        return {'status': 409, 'body': {'error': 'Duplicate request_key for this user.'}}
    c.execute('INSERT INTO reservations (user_id, listing_id, check_in, check_out, party, total, request_key) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (u['id'], listing_id, check_in, check_out, party, total, request_key))
    conn.commit()
    c.execute('SELECT id, listing_id, check_in, check_out, party, total FROM reservations WHERE id = last_insert_rowid()')
    row = c.fetchone()
    return {'status': 201, 'body': {'reservation': dict(row)}}


def handle_list_reservations(conn, request):
    u = auth_user(conn, request)
    if u is None:
        return {'status': 401, 'body': {'error': 'Not authenticated.'}}
    c = conn.cursor()
    c.execute('SELECT id, listing_id, check_in, check_out, party, total FROM reservations WHERE user_id = ?', (u['id'],))
    rows = c.fetchall()
    reservations = [dict(r) for r in rows]
    return {'status': 200, 'body': {'reservations': reservations}}


def handle_get_reservation(conn, request, res_id):
    u = auth_user(conn, request)
    if u is None:
        return {'status': 401, 'body': {'error': 'Not authenticated.'}}
    c = conn.cursor()
    c.execute('SELECT id, listing_id, check_in, check_out, party, total FROM reservations WHERE id = ? AND user_id = ?', (res_id, u['id']))
    row = c.fetchone()
    if row is None:
        return {'status': 404, 'body': {'error': 'Reservation not found.'}}
    return {'status': 200, 'body': {'reservation': dict(row)}}


def handle_admin_list_reservations(conn, request):
    u = auth_user(conn, request)
    if u is None:
        return {'status': 401, 'body': {'error': 'Not authenticated.'}}
    if u['role'] != 'admin':
        return {'status': 403, 'body': {'error': 'Forbidden.'}}
    c = conn.cursor()
    c.execute('SELECT id, user_id, listing_id, check_in, check_out, party, total FROM reservations')
    rows = c.fetchall()
    reservations = [dict(r) for r in rows]
    return {'status': 200, 'body': {'reservations': reservations}}


def handle_admin_list_listings(conn, request):
    u = auth_user(conn, request)
    if u is None:
        return {'status': 401, 'body': {'error': 'Not authenticated.'}}
    if u['role'] != 'admin':
        return {'status': 403, 'body': {'error': 'Forbidden.'}}
    c = conn.cursor()
    c.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings')
    rows = c.fetchall()
    listings = [dict(r) for r in rows]
    return {'status': 200, 'body': {'listings': listings}}


def handle_admin_update_listing(conn, request, listing_id, body):
    u = auth_user(conn, request)
    if u is None:
        return {'status': 401, 'body': {'error': 'Not authenticated.'}}
    if u['role'] != 'admin':
        return {'status': 403, 'body': {'error': 'Forbidden.'}}
    price = body.get('price')
    active = body.get('active')
    if price is None or (not isinstance(price, (int, float)) or isinstance(price, bool)):
        return {'status': 400, 'body': {'error': 'Price must be a number.'}}
    if active is None or (not isinstance(active, (int, float)) or isinstance(active, bool)):
        return {'status': 400, 'body': {'error': 'Active must be 0 or 1.'}}
    price = int(price)
    active = int(active)
    if price < 1 or price > 10000:
        return {'status': 400, 'body': {'error': 'Price must be between 1 and 10000.'}}
    if active not in (0, 1):
        return {'status': 400, 'body': {'error': 'Active must be 0 or 1.'}}
    c = conn.cursor()
    c.execute('SELECT id FROM listings WHERE id = ?', (listing_id,))
    if c.fetchone() is None:
        return {'status': 404, 'body': {'error': 'Listing not found.'}}
    c.execute('UPDATE listings SET price = ?, active = ? WHERE id = ?', (price, active, listing_id))
    conn.commit()
    c.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
    row = c.fetchone()
    return {'status': 200, 'body': {'listing': dict(row)}}
