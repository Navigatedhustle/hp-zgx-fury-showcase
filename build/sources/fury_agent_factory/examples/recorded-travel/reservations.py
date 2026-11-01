import secrets
import re
from datetime import datetime, date
import db

def _parse_date(date_str):
    if not isinstance(date_str, str):
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

def _valid_party(party, capacity):
    return isinstance(party, int) and 1 <= party <= capacity

def routes(conn, request):
    path = request.get('path', '')
    method = request.get('method', '')
    body = request.get('body', {})
    if not isinstance(body, dict):
        body = {}

    # Public quote endpoint - no authentication
    if path == '/quote' and method == 'POST':
        listing_id = body.get('listing_id')
        check_in_str = body.get('check_in')
        check_out_str = body.get('check_out')
        party = body.get('party')

        # Validate types
        if not isinstance(listing_id, int) or isinstance(listing_id, bool):
            return {'status': 400, 'body': {'error': 'listing_id must be an integer'}}
        if not isinstance(check_in_str, str) or not isinstance(check_out_str, str):
            return {'status': 400, 'body': {'error': 'check_in and check_out must be strings'}}
        if not isinstance(party, int) or isinstance(party, bool):
            return {'status': 400, 'body': {'error': 'party must be an integer'}}

        # Parse dates
        check_in = _parse_date(check_in_str)
        check_out = _parse_date(check_out_str)
        if not check_in or not check_out:
            return {'status': 400, 'body': {'error': 'Invalid date format, use YYYY-MM-DD'}}

        today = date.today()
        if check_in < today:
            return {'status': 400, 'body': {'error': 'check_in must be today or later'}}
        if check_out <= check_in:
            return {'status': 400, 'body': {'error': 'check_out must be after check_in'}}
        nights = (check_out - check_in).days
        if nights > 30:
            return {'status': 400, 'body': {'error': 'Maximum stay is 30 nights'}}

        # Lookup listing
        cur = conn.execute('SELECT id, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
        listing = cur.fetchone()
        if not listing or not listing['active']:
            return {'status': 404, 'body': {'error': 'Listing not found or inactive'}}
        if not 1 <= party <= listing['capacity']:
            return {'status': 400, 'body': {'error': 'Party size exceeds capacity'}}

        total = listing['price'] * nights
        return {'status': 200, 'body': {'quote': {
            'listing_id': listing_id,
            'check_in': check_in_str,
            'check_out': check_out_str,
            'party': party,
            'nights': nights,
            'nightly': listing['price'],
            'total': total,
            'currency': 'EUR'
        }}}

    # Authenticated reservation endpoints
    auth_user = db.auth.user if hasattr(db, 'auth') else None
    if auth_user is None:
        # Import auth module if not already imported; but given architecture, auth is from global import
        # Use function from auth module that will be imported in backend.py
        from auth import user as auth_user_func
        auth_user = auth_user_func(conn, request)

    # Reservations CR
    if path == '/reservations' and method == 'POST':
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        listing_id = body.get('listing_id')
        check_in_str = body.get('check_in')
        check_out_str = body.get('check_out')
        party = body.get('party')
        request_key = body.get('request_key')

        # Validate types
        if not isinstance(listing_id, int) or isinstance(listing_id, bool):
            return {'status': 400, 'body': {'error': 'listing_id must be an integer'}}
        if not isinstance(check_in_str, str) or not isinstance(check_out_str, str):
            return {'status': 400, 'body': {'error': 'check_in and check_out must be strings'}}
        if not isinstance(party, int) or isinstance(party, bool):
            return {'status': 400, 'body': {'error': 'party must be an integer'}}
        if not isinstance(request_key, str) or len(request_key) < 8 or len(request_key) > 100:
            return {'status': 400, 'body': {'error': 'request_key must be a string between 8 and 100 characters'}}

        # Parse dates
        check_in = _parse_date(check_in_str)
        check_out = _parse_date(check_out_str)
        if not check_in or not check_out:
            return {'status': 400, 'body': {'error': 'Invalid date format, use YYYY-MM-DD'}}

        today = date.today()
        if check_in < today:
            return {'status': 400, 'body': {'error': 'check_in must be today or later'}}
        if check_out <= check_in:
            return {'status': 400, 'body': {'error': 'check_out must be after check_in'}}
        nights = (check_out - check_in).days
        if nights > 30:
            return {'status': 400, 'body': {'error': 'Maximum stay is 30 nights'}}

        # Lookup listing
        cur = conn.execute('SELECT id, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
        listing = cur.fetchone()
        if not listing or not listing['active']:
            return {'status': 404, 'body': {'error': 'Listing not found or inactive'}}
        if not _valid_party(party, listing['capacity']):
            return {'status': 400, 'body': {'error': 'Party size exceeds capacity'}}

        total = listing['price'] * nights
        # Check duplicate request_key for this user
        cur = conn.execute('SELECT id FROM reservations WHERE user_id = ? AND request_key = ?', (auth_user['id'], request_key))
        if cur.fetchone():
            return {'status': 409, 'body': {'error': 'Duplicate reservation request'}}

        cur = conn.execute(
            'INSERT INTO reservations (user_id, listing_id, check_in, check_out, party, total, request_key) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (auth_user['id'], listing_id, check_in_str, check_out_str, party, total, request_key)
        )
        conn.commit()
        res_id = cur.lastrowid
        return {'status': 201, 'body': {'reservation': {
            'id': res_id,
            'listing_id': listing_id,
            'check_in': check_in_str,
            'check_out': check_out_str,
            'party': party,
            'total': total
        }}}

    if path == '/reservations' and method == 'GET':
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        cur = conn.execute('SELECT id, listing_id, check_in, check_out, party, total FROM reservations WHERE user_id = ? ORDER BY id', (auth_user['id'],))
        reservations = [dict(row) for row in cur.fetchall()]
        return {'status': 200, 'body': {'reservations': reservations}}

    # GET /reservations/{id}
    match = re.match(r'^/reservations/(\d+)$', path)
    if match and method == 'GET':
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        res_id = int(match.group(1))
        cur = conn.execute('SELECT id, listing_id, check_in, check_out, party, total, user_id FROM reservations WHERE id = ?', (res_id,))
        reservation = cur.fetchone()
        if not reservation:
            return {'status': 404, 'body': {'error': 'Reservation not found'}}
        if reservation['user_id'] != auth_user['id']:
            return {'status': 404, 'body': {'error': 'Reservation not found'}}
        return {'status': 200, 'body': {'reservation': {
            'id': reservation['id'],
            'listing_id': reservation['listing_id'],
            'check_in': reservation['check_in'],
            'check_out': reservation['check_out'],
            'party': reservation['party'],
            'total': reservation['total']
        }}}

    # Admin endpoints
    # GET /admin/listings
    if path == '/admin/listings' and method == 'GET':
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        if auth_user['role'] != 'admin':
            return {'status': 403, 'body': {'error': 'Forbidden'}}
        cur = conn.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings ORDER BY id')
        listings = [dict(row) for row in cur.fetchall()]
        return {'status': 200, 'body': {'listings': listings}}

    # PUT /admin/listings/{id}
    match = re.match(r'^/admin/listings/(\d+)$', path)
    if match and method == 'PUT':
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        if auth_user['role'] != 'admin':
            return {'status': 403, 'body': {'error': 'Forbidden'}}
        listing_id = int(match.group(1))
        price = body.get('price')
        active = body.get('active')
        # Validate
        if price is not None:
            if not isinstance(price, int) or isinstance(price, bool) or price < 1 or price > 10000:
                return {'status': 400, 'body': {'error': 'price must be integer 1-10000'}}
        if active is not None:
            if not isinstance(active, int) or isinstance(active, bool) or active not in (0, 1):
                return {'status': 400, 'body': {'error': 'active must be 0 or 1'}}
        # Build update
        updates = []
        if price is not None:
            updates.append(('price', price))
        if active is not None:
            updates.append(('active', active))
        if not updates:
            return {'status': 400, 'body': {'error': 'Nothing to update'}}
        set_clause = ', '.join(f'{col} = ?' for col, _ in updates)
        values = [val for _, val in updates]
        values.append(listing_id)
        conn.execute(f'UPDATE listings SET {set_clause} WHERE id = ?', values)
        conn.commit()
        cur = conn.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
        listing = cur.fetchone()
        if not listing:
            return {'status': 404, 'body': {'error': 'Listing not found'}}
        return {'status': 200, 'body': {'listing': dict(listing)}}

    # GET /admin/reservations
    if path == '/admin/reservations' and method == 'GET':
        if not auth_user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        if auth_user['role'] != 'admin':
            return {'status': 403, 'body': {'error': 'Forbidden'}}
        cur = conn.execute('SELECT id, user_id, listing_id, check_in, check_out, party, total FROM reservations ORDER BY id')
        reservations = [dict(row) for row in cur.fetchall()]
        return {'status': 200, 'body': {'reservations': reservations}}

    return None