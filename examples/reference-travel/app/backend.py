import contextlib
import db
import auth
import catalog
import private
import reservations

def handle(request, db_path):
    with contextlib.closing(db.connect(db_path)) as conn:
        # Dispatch to each module; return first non-None response
        responses = []
        responses.append(auth.routes(conn, request))
        responses.append(catalog.routes(conn, request))
        responses.append(private.routes(conn, request))
        responses.append(reservations.routes(conn, request))
        for response in responses:
            if response is not None:
                conn.commit()
                return response
        conn.commit()
        return {'status': 404, 'body': {'error': 'Not found'}}
