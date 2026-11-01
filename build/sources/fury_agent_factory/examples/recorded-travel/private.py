import db
import auth

def routes(conn, request):
    path = request.get('path', '')
    method = request.get('method', '')

    # Favorites endpoints
    if path == '/favorites' and method == 'GET':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        cur = conn.execute('''
            SELECT l.id, l.name, l.city, l.country, l.description, l.price, l.capacity, l.active
            FROM favorites f JOIN listings l ON f.listing_id = l.id
            WHERE f.user_id = ?
        ''', (user['id'],))
        rows = cur.fetchall()
        results = []
        for row in rows:
            results.append({
                'id': row['id'],
                'name': row['name'],
                'city': row['city'],
                'country': row['country'],
                'description': row['description'],
                'price': row['price'],
                'capacity': row['capacity'],
                'active': row['active']
            })
        return {'status': 200, 'body': {'favorites': results}}

    if path == '/favorites' and method == 'POST':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        body = request.get('body', {})
        if not isinstance(body, dict):
            return {'status': 400, 'body': {'error': 'Invalid request body'}}
        listing_id = body.get('listing_id')
        if not isinstance(listing_id, int):
            return {'status': 400, 'body': {'error': 'listing_id must be an integer'}}
        # Check listing exists and is active
        cur = conn.execute('SELECT id FROM listings WHERE id = ? AND active = 1', (listing_id,))
        if not cur.fetchone():
            return {'status': 404, 'body': {'error': 'Listing not found or inactive'}}
        # Idempotent insert
        try:
            conn.execute('INSERT INTO favorites (user_id, listing_id) VALUES (?, ?)', (user['id'], listing_id))
            conn.commit()
            return {'status': 201, 'body': {'ok': True}}
        except db.sqlite3.IntegrityError:
            # Already favorited
            return {'status': 200, 'body': {'ok': True}}

    if path.startswith('/favorites/') and method == 'DELETE':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        listing_id_str = path[len('/favorites/'):]
        try:
            listing_id = int(listing_id_str)
        except ValueError:
            return {'status': 404, 'body': {'error': 'Invalid listing ID'}}
        cur = conn.execute('DELETE FROM favorites WHERE user_id = ? AND listing_id = ?', (user['id'], listing_id))
        conn.commit()
        if cur.rowcount == 0:
            return {'status': 404, 'body': {'error': 'Favorite not found'}}
        return {'status': 200, 'body': {'ok': True}}

    # Itineraries endpoints
    if path == '/itineraries' and method == 'GET':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        cur = conn.execute('SELECT id, title, notes FROM itineraries WHERE user_id = ?', (user['id'],))
        rows = cur.fetchall()
        results = []
        for row in rows:
            results.append({
                'id': row['id'],
                'title': row['title'],
                'notes': row['notes']
            })
        return {'status': 200, 'body': {'itineraries': results}}

    if path == '/itineraries' and method == 'POST':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        body = request.get('body', {})
        if not isinstance(body, dict):
            return {'status': 400, 'body': {'error': 'Invalid request body'}}
        title = body.get('title')
        notes = body.get('notes', '')
        if not title or not isinstance(title, str) or len(title) < 1 or len(title) > 100:
            return {'status': 400, 'body': {'error': 'title must be a string between 1 and 100 characters'}}
        if notes and (not isinstance(notes, str) or len(notes) > 4000):
            return {'status': 400, 'body': {'error': 'notes must be a string up to 4000 characters'}}
        cur = conn.execute('INSERT INTO itineraries (user_id, title, notes) VALUES (?, ?, ?)',
                          (user['id'], title, notes))
        conn.commit()
        itinerary_id = cur.lastrowid
        return {'status': 201, 'body': {'itinerary': {'id': itinerary_id, 'title': title, 'notes': notes}}}

    if path.startswith('/itineraries/') and method == 'PUT':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        itinerary_id_str = path[len('/itineraries/'):]
        try:
            itinerary_id = int(itinerary_id_str)
        except ValueError:
            return {'status': 404, 'body': {'error': 'Invalid itinerary ID'}}
        body = request.get('body', {})
        if not isinstance(body, dict):
            return {'status': 400, 'body': {'error': 'Invalid request body'}}
        title = body.get('title')
        notes = body.get('notes', '')
        if not title or not isinstance(title, str) or len(title) < 1 or len(title) > 100:
            return {'status': 400, 'body': {'error': 'title must be a string between 1 and 100 characters'}}
        if notes and (not isinstance(notes, str) or len(notes) > 4000):
            return {'status': 400, 'body': {'error': 'notes must be a string up to 4000 characters'}}
        # Check ownership
        cur = conn.execute('SELECT id FROM itineraries WHERE id = ? AND user_id = ?', (itinerary_id, user['id']))
        if not cur.fetchone():
            return {'status': 404, 'body': {'error': 'Itinerary not found'}}
        conn.execute('UPDATE itineraries SET title = ?, notes = ? WHERE id = ?',
                     (title, notes, itinerary_id))
        conn.commit()
        return {'status': 200, 'body': {'itinerary': {'id': itinerary_id, 'title': title, 'notes': notes}}}

    if path.startswith('/itineraries/') and method == 'DELETE':
        user = auth.user(conn, request)
        if not user:
            return {'status': 401, 'body': {'error': 'Unauthorized'}}
        itinerary_id_str = path[len('/itineraries/'):]
        try:
            itinerary_id = int(itinerary_id_str)
        except ValueError:
            return {'status': 404, 'body': {'error': 'Invalid itinerary ID'}}
        cur = conn.execute('DELETE FROM itineraries WHERE id = ? AND user_id = ?', (itinerary_id, user['id']))
        conn.commit()
        if cur.rowcount == 0:
            return {'status': 404, 'body': {'error': 'Itinerary not found'}}
        return {'status': 200, 'body': {'ok': True}}

    return None
