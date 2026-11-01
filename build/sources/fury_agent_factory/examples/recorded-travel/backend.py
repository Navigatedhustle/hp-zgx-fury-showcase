import contextlib
from db import connect
from auth import routes as auth_routes
from catalog import routes as catalog_routes
from private import routes as private_routes
from reservations import routes as reservation_routes

def handle(request, db_path):
    if not isinstance(request, dict):
        return {'status': 400, 'body': {'error': 'Invalid request'}}
    method = request.get('method', '')
    path = request.get('path', '')
    body = request.get('body', {})
    if not isinstance(body, dict):
        return {'status': 400, 'body': {'error': 'Invalid request body'}}
    if not isinstance(method, str) or not isinstance(path, str):
        return {'status': 400, 'body': {'error': 'Invalid method or path'}}
    try:
        with contextlib.closing(connect(db_path)) as conn:
            response = auth_routes(conn, request)
            if response is not None:
                conn.commit()
                return response
            response = catalog_routes(conn, request)
            if response is not None:
                conn.commit()
                return response
            response = private_routes(conn, request)
            if response is not None:
                conn.commit()
                return response
            response = reservation_routes(conn, request)
            if response is not None:
                conn.commit()
                return response
            conn.commit()
            return {'status': 404, 'body': {'error': 'Not found'}}
    except Exception as e:
        return {'status': 400, 'body': {'error': str(e)}}
