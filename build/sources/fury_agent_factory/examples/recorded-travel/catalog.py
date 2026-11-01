import math
import db
from auth import user

def routes(conn, request):
    path = request.get('path', '')
    method = request.get('method', '')

    if path == '/health' and method == 'GET':
        return {'status': 200, 'body': {'ok': True, 'demo': True}}

    if path == '/listings' and method == 'GET':
        body = request.get('body', {})
        if not isinstance(body, dict):
            return {'status': 400, 'body': {'error': 'Invalid request body'}}
        return _list_listings(conn, body)

    # Check for /listings/{id} or /admin paths after listing list
    parts = path.strip('/').split('/')
    if len(parts) == 2 and parts[0] == 'listings':
        try:
            listing_id = int(parts[1])
        except ValueError:
            return None
        if method == 'GET':
            return _get_listing(conn, listing_id)
        else:
            return None

    if len(parts) == 2 and parts[0] == 'admin' and parts[1] == 'reservations':
        # Admin reservations handled in reservations.py, skip
        return None

    if len(parts) == 2 and parts[0] == 'admin' and parts[1] == 'listings':
        if method == 'GET':
            auth_user = user(conn, request)
            if not auth_user:
                return {'status': 401, 'body': {'error': 'Unauthorized'}}
            if auth_user['role'] != 'admin':
                return {'status': 403, 'body': {'error': 'Forbidden'}}
            cur = conn.execute('SELECT * FROM listings ORDER BY id')
            listings = [dict(row) for row in cur.fetchall()]
            return {'status': 200, 'body': {'listings': listings}}
        else:
            return None

    if len(parts) == 3 and parts[0] == 'admin' and parts[1] == 'listings':
        try:
            listing_id = int(parts[2])
        except ValueError:
            return None
        if method == 'PUT':
            auth_user = user(conn, request)
            if not auth_user:
                return {'status': 401, 'body': {'error': 'Unauthorized'}}
            if auth_user['role'] != 'admin':
                return {'status': 403, 'body': {'error': 'Forbidden'}}
            return _update_listing(conn, listing_id, request.get('body', {}))
        else:
            return None

    return None

def _list_listings(conn, body):
    q = body.get('q', '')
    if not isinstance(q, str):
        return {'status': 400, 'body': {'error': 'Invalid search query'}}
    city = body.get('city', '')
    if city is not None and not isinstance(city, str):
        return {'status': 400, 'body': {'error': 'Invalid city filter'}}
    sort = body.get('sort', 'price_asc')
    if sort not in ('price_asc', 'price_desc'):
        return {'status': 400, 'body': {'error': 'Invalid sort direction'}}
    page = body.get('page', 1)
    page_size = body.get('page_size', 6)
    max_price = body.get('max_price', None)
    party = body.get('party', None)

    # Validate types
    if not isinstance(page, int) or page < 1:
        return {'status': 400, 'body': {'error': 'Invalid page'}}
    if not isinstance(page_size, int) or page_size < 1 or page_size > 12:
        return {'status': 400, 'body': {'error': 'Invalid page_size'}}
    if max_price is not None:
        if isinstance(max_price, bool) or not isinstance(max_price, (int, float)) or max_price <= 0:
            return {'status': 400, 'body': {'error': 'Invalid max_price'}}
        max_price = int(max_price)
    if party is not None:
        if isinstance(party, bool) or not isinstance(party, int) or party < 1 or party > 8:
            return {'status': 400, 'body': {'error': 'Invalid party size'}}

    # Build query
    conditions = ['active = 1']
    params = []
    if q:
        conditions.append('(LOWER(name) LIKE ? OR LOWER(city) LIKE ? OR LOWER(country) LIKE ?)')
        like_q = f'%{q.lower()}%'
        params.extend([like_q, like_q, like_q])
    if city:
        conditions.append('LOWER(city) = ?')
        params.append(city.lower())
    if max_price is not None:
        conditions.append('price <= ?')
        params.append(max_price)
    if party is not None:
        conditions.append('capacity >= ?')
        params.append(party)

    where_clause = ' AND '.join(conditions)

    # Count total
    count_cur = conn.execute(f'SELECT COUNT(*) FROM listings WHERE {where_clause}', params)
    total = count_cur.fetchone()[0]

    # Order and paginate
    order = 'price ASC' if sort == 'price_asc' else 'price DESC'
    offset = (page - 1) * page_size
    cur = conn.execute(f'SELECT * FROM listings WHERE {where_clause} ORDER BY {order} LIMIT ? OFFSET ?',
                       params + [page_size, offset])
    listings = [dict(row) for row in cur.fetchall()]

    return {'status': 200, 'body': {
        'listings': listings,
        'total': total,
        'page': page,
        'page_size': page_size
    }}

def _get_listing(conn, listing_id):
    cur = conn.execute('SELECT * FROM listings WHERE id = ? AND active = 1', (listing_id,))
    row = cur.fetchone()
    if not row:
        return {'status': 404, 'body': {'error': 'Listing not found'}}
    return {'status': 200, 'body': {'listing': dict(row)}}

def _update_listing(conn, listing_id, body):
    if not isinstance(body, dict):
        return {'status': 400, 'body': {'error': 'Invalid request body'}}
    price = body.get('price')
    active = body.get('active')
    # Validate at least one field present
    if price is None and active is None:
        return {'status': 400, 'body': {'error': 'No fields to update'}}
    # Check listing exists
    cur = conn.execute('SELECT * FROM listings WHERE id = ?', (listing_id,))
    row = cur.fetchone()
    if not row:
        return {'status': 404, 'body': {'error': 'Listing not found'}}
    # Validate price
    if price is not None:
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 1 or price > 10000:
            return {'status': 400, 'body': {'error': 'Invalid price (must be integer 1-10000)'}}
        price = int(price)
    # Validate active
    if active is not None:
        if active not in (0, 1):
            return {'status': 400, 'body': {'error': 'Invalid active flag (must be 0 or 1)'}}
    # Build update
    updates = []
    params = []
    if price is not None:
        updates.append('price = ?')
        params.append(price)
    if active is not None:
        updates.append('active = ?')
        params.append(active)
    params.append(listing_id)
    conn.execute(f'UPDATE listings SET {', '.join(updates)} WHERE id = ?', params)
    conn.commit()
    cur = conn.execute('SELECT * FROM listings WHERE id = ?', (listing_id,))
    updated = dict(cur.fetchone())
    return {'status': 200, 'body': {'listing': updated}}
