import auth
from datetime import datetime, date

def routes(conn, request):
    method = request.get('method', '')
    path = request.get('path', '')
    body = request.get('body', {})

    # Health endpoint
    if path == '/health' and method == 'GET':
        return {'status': 200, 'body': {'ok': True, 'demo': True}}

    # Admin endpoints - check admin auth only if path matches /admin/
    if path.startswith('/admin/'):
        u = auth.user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        if u['role'] != 'admin':
            return {'status': 403, 'body': {'error': 'Forbidden.'}}

        if path == '/admin/reservations' and method == 'GET':
            c = conn.cursor()
            c.execute('SELECT id, user_id, listing_id, check_in, check_out, party, total FROM reservations')
            rows = c.fetchall()
            reservations = [dict(r) for r in rows]
            return {'status': 200, 'body': {'reservations': reservations}}

        if path == '/admin/listings' and method == 'GET':
            c = conn.cursor()
            c.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings')
            rows = c.fetchall()
            listings = [dict(r) for r in rows]
            return {'status': 200, 'body': {'listings': listings}}

        # PUT /admin/listings/{id}
        if path.startswith('/admin/listings/') and method == 'PUT':
            parts = path.split('/')
            if len(parts) != 4:
                return None
            try:
                listing_id = int(parts[3])
            except (ValueError, TypeError):
                return {'status': 400, 'body': {'error': 'Invalid listing ID.'}}
            price = body.get('price')
            active = body.get('active')
            if price is not None and (not isinstance(price, int) or price < 1 or price > 10000):
                return {'status': 400, 'body': {'error': 'Price must be integer 1-10000.'}}
            if active is not None and (active not in (0, 1)):
                return {'status': 400, 'body': {'error': 'Active must be 0 or 1.'}}
            c = conn.cursor()
            c.execute('SELECT id FROM listings WHERE id = ?', (listing_id,))
            if c.fetchone() is None:
                return {'status': 404, 'body': {'error': 'Listing not found.'}}
            if price is not None:
                c.execute('UPDATE listings SET price = ? WHERE id = ?', (price, listing_id))
            if active is not None:
                c.execute('UPDATE listings SET active = ? WHERE id = ?', (active, listing_id))
            conn.commit()
            c.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
            row = c.fetchone()
            return {'status': 200, 'body': {'listing': dict(row)}}

        return None

    # Public listing search
    if path == '/listings' and method == 'GET':
        q = body.get('q', None)
        city_filter = body.get('city', None)
        sort = body.get('sort', None)
        page = body.get('page', 1)
        page_size = body.get('page_size', 6)
        max_price = body.get('max_price', None)
        party = body.get('party', None)

        # Validate pagination
        if not isinstance(page, int) or page < 1:
            page = 1
        if not isinstance(page_size, int) or page_size < 1 or page_size > 12:
            page_size = 6
        # max_price must be positive finite numeric (not bool, not inf/nan)
        if max_price is not None:
            if isinstance(max_price, bool):
                return {'status': 400, 'body': {'error': 'max_price must be a positive number.'}}
            if not isinstance(max_price, (int, float)):
                return {'status': 400, 'body': {'error': 'max_price must be a positive number.'}}
            # Reject inf, -inf, nan
            if isinstance(max_price, float) and (max_price == float('inf') or max_price == float('-inf') or max_price != max_price):
                return {'status': 400, 'body': {'error': 'max_price must be a positive finite number.'}}
            if max_price <= 0:
                return {'status': 400, 'body': {'error': 'max_price must be a positive number.'}}
        if party is not None and (not isinstance(party, int) or party < 1 or party > 8):
            return {'status': 400, 'body': {'error': 'party must be integer 1-8.'}}

        query = 'SELECT id, name, city, country, description, price, capacity, active FROM listings WHERE active = 1'
        params = []

        # Case-insensitive search
        if q is not None and isinstance(q, str) and q.strip():
            query += ' AND (LOWER(name) LIKE ? OR LOWER(city) LIKE ? OR LOWER(country) LIKE ?)'
            search_term = '%' + q.strip().lower() + '%'
            params.extend([search_term, search_term, search_term])

        if city_filter is not None and isinstance(city_filter, str) and city_filter.strip():
            query += ' AND city = ?'
            params.append(city_filter.strip())

        if max_price is not None:
            query += ' AND price <= ?'
            # Convert to integer safely (already validated finite positive)
            params.append(int(max_price))

        if party is not None:
            query += ' AND capacity >= ?'
            params.append(party)

        # Sort
        if sort == 'price_asc':
            query += ' ORDER BY price ASC'
        elif sort == 'price_desc':
            query += ' ORDER BY price DESC'
        else:
            query += ' ORDER BY id'

        c = conn.cursor()
        c.execute(query, params)
        all_rows = c.fetchall()
        total = len(all_rows)

        # Pagination
        offset = (page - 1) * page_size
        listings_page = all_rows[offset:offset + page_size]
        listings = [dict(r) for r in listings_page]

        return {'status': 200, 'body': {'listings': listings, 'total': total, 'page': page, 'page_size': page_size}}

    # Public listing detail
    if path.startswith('/listings/') and method == 'GET':
        parts = path.split('/')
        if len(parts) != 3:
            return None
        try:
            listing_id = int(parts[2])
        except (ValueError, TypeError):
            return {'status': 400, 'body': {'error': 'Invalid listing ID.'}}

        c = conn.cursor()
        c.execute('SELECT id, name, city, country, description, price, capacity, active FROM listings WHERE id = ?', (listing_id,))
        row = c.fetchone()
        if row is None:
            return {'status': 404, 'body': {'error': 'Listing not found.'}}
        return {'status': 200, 'body': {'listing': dict(row)}}

    # Public quote endpoint: no authentication required
    if path == '/quote' and method == 'POST':
        listing_id = body.get('listing_id')
        check_in = body.get('check_in')
        check_out = body.get('check_out')
        party = body.get('party')

        if not listing_id or not check_in or not check_out or party is None:
            return {'status': 400, 'body': {'error': 'Missing required fields: listing_id, check_in, check_out, party.'}}
        if not isinstance(listing_id, int) or not isinstance(party, int):
            return {'status': 400, 'body': {'error': 'listing_id and party must be integers.'}}
        if not isinstance(check_in, str) or not isinstance(check_out, str):
            return {'status': 400, 'body': {'error': 'Dates must be strings.'}}
        # Reject bool
        if isinstance(body.get('listing_id'), bool) or isinstance(body.get('party'), bool):
            return {'status': 400, 'body': {'error': 'Invalid input types.'}}

        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return {'status': 400, 'body': {'error': 'Invalid date format. Use YYYY-MM-DD.'}}

        today = date.today()
        if check_in_date < today:
            return {'status': 400, 'body': {'error': 'check_in must be today or later.'}}
        if check_out_date <= check_in_date:
            return {'status': 400, 'body': {'error': 'check_out must be after check_in.'}}
        nights = (check_out_date - check_in_date).days
        if nights < 1 or nights > 30:
            return {'status': 400, 'body': {'error': 'Nights must be between 1 and 30.'}}
        if party < 1 or party > 8:
            return {'status': 400, 'body': {'error': 'Party must be between 1 and 8.'}}

        c = conn.cursor()
        c.execute('SELECT price, capacity, active FROM listings WHERE id = ?', (listing_id,))
        row = c.fetchone()
        if row is None or row['active'] == 0:
            return {'status': 404, 'body': {'error': 'Listing not found or inactive.'}}
        if party > row['capacity']:
            return {'status': 400, 'body': {'error': 'Party exceeds listing capacity.'}}

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

    return None