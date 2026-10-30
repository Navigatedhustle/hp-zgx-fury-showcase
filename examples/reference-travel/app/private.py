import sqlite3
from auth import user

def routes(conn, request):
    method = request.get('method', '')
    path = request.get('path', '')
    body = request.get('body', {})

    # Favorites
    if path == '/favorites' and method == 'GET':
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        c = conn.cursor()
        c.execute('''
            SELECT l.* FROM listings l
            JOIN favorites f ON l.id = f.listing_id
            WHERE f.user_id = ?
        ''', (u['id'],))
        favorites = [dict(row) for row in c.fetchall()]
        return {'status': 200, 'body': {'favorites': favorites}}

    if path == '/favorites' and method == 'POST':
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        listing_id = body.get('listing_id')
        if listing_id is None:
            return {'status': 400, 'body': {'error': 'listing_id is required.'}}
        if not isinstance(listing_id, int) or listing_id < 1:
            return {'status': 400, 'body': {'error': 'Invalid listing_id.'}}
        c = conn.cursor()
        c.execute('SELECT id FROM listings WHERE id = ?', (listing_id,))
        if c.fetchone() is None:
            return {'status': 404, 'body': {'error': 'Listing not found.'}}
        try:
            c.execute('INSERT INTO favorites (user_id, listing_id) VALUES (?, ?)', (u['id'], listing_id))
            conn.commit()
            return {'status': 201, 'body': {}}
        except sqlite3.IntegrityError:
            # Already a favorite
            return {'status': 200, 'body': {}}

    if path.startswith('/favorites/') and method == 'DELETE':
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        parts = path.split('/')
        if len(parts) != 3:
            return None
        try:
            listing_id = int(parts[2])
        except (ValueError, TypeError):
            return {'status': 400, 'body': {'error': 'Invalid listing_id.'}}
        c = conn.cursor()
        c.execute('DELETE FROM favorites WHERE user_id = ? AND listing_id = ?', (u['id'], listing_id))
        conn.commit()
        if c.rowcount == 0:
            return {'status': 404, 'body': {'error': 'Favorite not found.'}}
        return {'status': 200, 'body': {}}

    # Itineraries
    if path == '/itineraries' and method == 'GET':
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        c = conn.cursor()
        c.execute('SELECT id, user_id, title, notes FROM itineraries WHERE user_id = ?', (u['id'],))
        itineraries = [dict(row) for row in c.fetchall()]
        return {'status': 200, 'body': {'itineraries': itineraries}}

    if path == '/itineraries' and method == 'POST':
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        title = body.get('title', '')
        notes = body.get('notes', '')
        if not title or not isinstance(title, str):
            return {'status': 400, 'body': {'error': 'Title is required and must be a string.'}}
        title = title.strip()
        if len(title) < 1 or len(title) > 100:
            return {'status': 400, 'body': {'error': 'Title must be between 1 and 100 characters.'}}
        if notes is not None and not isinstance(notes, str):
            return {'status': 400, 'body': {'error': 'Notes must be a string.'}}
        if notes and len(notes) > 4000:
            return {'status': 400, 'body': {'error': 'Notes must not exceed 4000 characters.'}}
        notes = notes.strip() if notes else None
        c = conn.cursor()
        c.execute('INSERT INTO itineraries (user_id, title, notes) VALUES (?, ?, ?)', (u['id'], title, notes))
        itinerary_id = c.lastrowid
        conn.commit()
        c.execute('SELECT id, user_id, title, notes FROM itineraries WHERE id = ?', (itinerary_id,))
        itinerary = dict(c.fetchone())
        return {'status': 201, 'body': {'itinerary': itinerary}}

    if path.startswith('/itineraries/') and method in ('PUT', 'DELETE'):
        u = user(conn, request)
        if u is None:
            return {'status': 401, 'body': {'error': 'Not authenticated.'}}
        parts = path.split('/')
        if len(parts) != 3:
            return None
        try:
            itinerary_id = int(parts[2])
        except (ValueError, TypeError):
            return {'status': 400, 'body': {'error': 'Invalid itinerary ID.'}}
        c = conn.cursor()
        c.execute('SELECT user_id FROM itineraries WHERE id = ?', (itinerary_id,))
        row = c.fetchone()
        if row is None:
            return {'status': 404, 'body': {'error': 'Itinerary not found.'}}
        if row['user_id'] != u['id']:
            return {'status': 404, 'body': {'error': 'Itinerary not found.'}}

        if method == 'PUT':
            title = body.get('title', '')
            notes = body.get('notes', '')
            if not title or not isinstance(title, str):
                return {'status': 400, 'body': {'error': 'Title is required and must be a string.'}}
            title = title.strip()
            if len(title) < 1 or len(title) > 100:
                return {'status': 400, 'body': {'error': 'Title must be between 1 and 100 characters.'}}
            if notes is not None and not isinstance(notes, str):
                return {'status': 400, 'body': {'error': 'Notes must be a string.'}}
            if notes and len(notes) > 4000:
                return {'status': 400, 'body': {'error': 'Notes must not exceed 4000 characters.'}}
            notes = notes.strip() if notes else None
            c.execute('UPDATE itineraries SET title = ?, notes = ? WHERE id = ?', (title, notes, itinerary_id))
            conn.commit()
            c.execute('SELECT id, user_id, title, notes FROM itineraries WHERE id = ?', (itinerary_id,))
            itinerary = dict(c.fetchone())
            return {'status': 200, 'body': {'itinerary': itinerary}}

        if method == 'DELETE':
            c.execute('DELETE FROM itineraries WHERE id = ?', (itinerary_id,))
            conn.commit()
            return {'status': 200, 'body': {}}

    return None
