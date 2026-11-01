import unittest
import tempfile
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import handle

def _make_request(method, path, body=None, headers=None):
    req = {'method': method, 'path': path, 'body': body or {}, 'headers': headers or {}}
    return req

def _login(conn, email, password):
    from auth import routes
    req = _make_request('POST', '/login', {'email': email, 'password': password})
    resp = routes(conn, req)
    conn.commit()
    return resp

def _register(conn, email, password):
    from auth import routes
    req = _make_request('POST', '/register', {'email': email, 'password': password})
    resp = routes(conn, req)
    conn.commit()
    return resp

class TestBackendIntegration(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        # Pre-initialize schema and seed data
        from db import connect
        self.conn = connect(self.db_path)
        self.conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_health(self):
        resp = handle(_make_request('GET', '/health'), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertTrue(resp['body']['ok'])
        self.assertTrue(resp['body']['demo'])

    def test_register_and_login(self):
        # Register a new user
        resp = handle(_make_request('POST', '/register', {'email': 'test@example.com', 'password': 'TestPassword123'}), self.db_path)
        self.assertEqual(resp['status'], 201)
        self.assertIn('token', resp['body'])
        self.assertEqual(resp['body']['user']['role'], 'user')
        user_id = resp['body']['user']['id']
        # Login with the same credentials
        resp = handle(_make_request('POST', '/login', {'email': 'test@example.com', 'password': 'TestPassword123'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertIn('token', resp['body'])
        # Login with wrong password
        resp = handle(_make_request('POST', '/login', {'email': 'test@example.com', 'password': 'wrong'}), self.db_path)
        self.assertEqual(resp['status'], 401)
        # Duplicate email registration
        resp = handle(_make_request('POST', '/register', {'email': 'test@example.com', 'password': 'AnotherPass123'}), self.db_path)
        self.assertEqual(resp['status'], 409)

    def test_login_default_admin(self):
        resp = handle(_make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['user']['role'], 'admin')

    def test_logout_idempotent(self):
        # Login first
        resp = handle(_make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        token = resp['body']['token']
        # Logout
        resp = handle(_make_request('POST', '/logout', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        # Second logout with same token -> 401
        resp = handle(_make_request('POST', '/logout', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 401)

    def test_me_authenticated(self):
        resp = handle(_make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        token = resp['body']['token']
        resp = handle(_make_request('GET', '/me', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['user']['email'], 'admin@example.test')
        # Unauthenticated
        resp = handle(_make_request('GET', '/me'), self.db_path)
        self.assertEqual(resp['status'], 401)

    def test_listings_list_basic(self):
        resp = handle(_make_request('GET', '/listings'), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertIn('listings', resp['body'])
        total = resp['body']['total']
        self.assertGreaterEqual(total, 18)
        self.assertEqual(resp['body']['page'], 1)
        self.assertEqual(resp['body']['page_size'], 6)

    def test_listings_filter_city(self):
        resp = handle(_make_request('GET', '/listings', {'city': 'Lisbon'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertEqual(l['city'], 'Lisbon')

    def test_listings_search_q(self):
        resp = handle(_make_request('GET', '/listings', {'q': 'kyoto'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertIn('kyoto', l['city'].lower() or l['name'].lower())

    def test_listings_sort_price_desc(self):
        resp = handle(_make_request('GET', '/listings', {'sort': 'price_desc', 'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        listings = resp['body']['listings']
        for i in range(len(listings) - 1):
            self.assertGreaterEqual(listings[i]['price'], listings[i+1]['price'])

    def test_listings_max_price(self):
        resp = handle(_make_request('GET', '/listings', {'max_price': 150}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertLessEqual(l['price'], 150)

    def test_listings_party_filter(self):
        resp = handle(_make_request('GET', '/listings', {'party': 6}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertGreaterEqual(l['capacity'], 6)

    def test_listing_detail(self):
        resp = handle(_make_request('GET', '/listings/1'), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertIn('listing', resp['body'])
        self.assertEqual(resp['body']['listing']['id'], 1)

    def test_listing_detail_not_found(self):
        resp = handle(_make_request('GET', '/listings/99999'), self.db_path)
        self.assertEqual(resp['status'], 404)

    def test_favorites_authentication(self):
        resp = handle(_make_request('GET', '/favorites'), self.db_path)
        self.assertEqual(resp['status'], 401)

    def test_favorites_add_list_delete(self):
        # Login as admin
        resp = handle(_make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        token = resp['body']['token']
        # Add favorite for listing 1
        resp = handle(_make_request('POST', '/favorites', {'listing_id': 1}, headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertIn(resp['status'], [200, 201])
        # List favorites
        resp = handle(_make_request('GET', '/favorites', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertGreaterEqual(len(resp['body']['favorites']), 1)
        fav_ids = [l['id'] for l in resp['body']['favorites']]
        self.assertIn(1, fav_ids)
        # Delete favorite
        resp = handle(_make_request('DELETE', '/favorites/1', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        # Verify deleted
        resp = handle(_make_request('GET', '/favorites', headers={'authorization': f'Bearer {token}'}), self.db_path)
        fav_ids = [l['id'] for l in resp['body']['favorites']]
        self.assertNotIn(1, fav_ids)

    def test_favorites_two_users_isolation(self):
        # Register two users
        resp1 = handle(_make_request('POST', '/register', {'email': 'alice@test.com', 'password': 'AlicePass123'}), self.db_path)
        token1 = resp1['body']['token']
        resp2 = handle(_make_request('POST', '/register', {'email': 'bob@test.com', 'password': 'BobPass123'}), self.db_path)
        token2 = resp2['body']['token']
        # Alice adds favorite for listing 1
        handle(_make_request('POST', '/favorites', {'listing_id': 1}, headers={'authorization': f'Bearer {token1}'}), self.db_path)
        # Bob lists favorites should be empty
        resp = handle(_make_request('GET', '/favorites', headers={'authorization': f'Bearer {token2}'}), self.db_path)
        self.assertEqual(resp['body']['favorites'], [])

    def test_itineraries_crud_and_isolation(self):
        # Register two users
        resp = handle(_make_request('POST', '/register', {'email': 'alice@test.com', 'password': 'AlicePass123'}), self.db_path)
        token_alice = resp['body']['token']
        resp = handle(_make_request('POST', '/register', {'email': 'bob@test.com', 'password': 'BobPass123'}), self.db_path)
        token_bob = resp['body']['token']
        # Alice creates an itinerary
        resp = handle(_make_request('POST', '/itineraries', {'title': 'Alice Trip', 'notes': 'Exciting'}, headers={'authorization': f'Bearer {token_alice}'}), self.db_path)
        self.assertEqual(resp['status'], 201)
        itin_id = resp['body']['itinerary']['id']
        # Bob cannot access Alice's itinerary
        resp = handle(_make_request('PUT', f'/itineraries/{itin_id}', {'title': 'Hacked'}, headers={'authorization': f'Bearer {token_bob}'}), self.db_path)
        self.assertEqual(resp['status'], 404)
        # Alice can update
        resp = handle(_make_request('PUT', f'/itineraries/{itin_id}', {'title': 'Updated Trip', 'notes': 'Better'}, headers={'authorization': f'Bearer {token_alice}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['itinerary']['title'], 'Updated Trip')
        # Bob cannot delete
        resp = handle(_make_request('DELETE', f'/itineraries/{itin_id}', headers={'authorization': f'Bearer {token_bob}'}), self.db_path)
        self.assertEqual(resp['status'], 404)
        # Alice can delete
        resp = handle(_make_request('DELETE', f'/itineraries/{itin_id}', headers={'authorization': f'Bearer {token_alice}'}), self.db_path)
        self.assertEqual(resp['status'], 200)

    def test_quote_public_and_arithmetic(self):
        # Public quote - no auth required
        resp = handle(_make_request('POST', '/quote', {'listing_id': 1, 'check_in': '2028-06-01', 'check_out': '2028-06-05', 'party': 2}), self.db_path)
        self.assertEqual(resp['status'], 200)
        q = resp['body']['quote']
        self.assertEqual(q['nights'], 4)
        self.assertEqual(q['total'], q['nightly'] * 4)
        self.assertEqual(q['currency'], 'EUR')
        # Invalid dates
        resp = handle(_make_request('POST', '/quote', {'listing_id': 1, 'check_in': '2020-01-01', 'check_out': '2020-01-02', 'party': 2}), self.db_path)
        self.assertEqual(resp['status'], 400)
        # Party > capacity
        resp = handle(_make_request('POST', '/quote', {'listing_id': 1, 'check_in': '2028-06-01', 'check_out': '2028-06-05', 'party': 10}), self.db_path)
        self.assertEqual(resp['status'], 400)
        # Unknown listing
        resp = handle(_make_request('POST', '/quote', {'listing_id': 9999, 'check_in': '2028-06-01', 'check_out': '2028-06-05', 'party': 2}), self.db_path)
        self.assertEqual(resp['status'], 404)

    def test_reservation_create_and_list(self):
        # Login
        resp = handle(_make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        token = resp['body']['token']
        # Create reservation
        resp = handle(_make_request('POST', '/reservations', {
            'listing_id': 1,
            'check_in': '2028-07-01',
            'check_out': '2028-07-05',
            'party': 2,
            'request_key': 'test_key_123456789'
        }, headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 201)
        res_id = resp['body']['reservation']['id']
        # List reservations
        resp = handle(_make_request('GET', '/reservations', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(len(resp['body']['reservations']), 1)
        # Get single reservation
        resp = handle(_make_request('GET', f'/reservations/{res_id}', headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['reservation']['id'], res_id)
        # Duplicate request_key for the same user -> 409
        resp = handle(_make_request('POST', '/reservations', {
            'listing_id': 2,
            'check_in': '2028-08-01',
            'check_out': '2028-08-03',
            'party': 2,
            'request_key': 'test_key_123456789'
        }, headers={'authorization': f'Bearer {token}'}), self.db_path)
        self.assertEqual(resp['status'], 409)

    def test_reservation_cross_user_isolation(self):
        # Register two users
        resp = handle(_make_request('POST', '/register', {'email': 'alice@test.com', 'password': 'AlicePass123'}), self.db_path)
        token_alice = resp['body']['token']
        resp = handle(_make_request('POST', '/register', {'email': 'bob@test.com', 'password': 'BobPass123'}), self.db_path)
        token_bob = resp['body']['token']
        # Alice creates reservation
        resp = handle(_make_request('POST', '/reservations', {
            'listing_id': 1,
            'check_in': '2028-09-01',
            'check_out': '2028-09-04',
            'party': 2,
            'request_key': 'alice_key_001'
        }, headers={'authorization': f'Bearer {token_alice}'}), self.db_path)
        self.assertEqual(resp['status'], 201)
        res_id_alice = resp['body']['reservation']['id']
        # Bob cannot access Alice's reservation
        resp = handle(_make_request('GET', f'/reservations/{res_id_alice}', headers={'authorization': f'Bearer {token_bob}'}), self.db_path)
        self.assertEqual(resp['status'], 404)

    def test_admin_endpoints(self):
        # Regular user cannot access admin
        resp = handle(_make_request('POST', '/register', {'email': 'user@test.com', 'password': 'UserPass123'}), self.db_path)
        token_user = resp['body']['token']
        resp = handle(_make_request('GET', '/admin/reservations', headers={'authorization': f'Bearer {token_user}'}), self.db_path)
        self.assertEqual(resp['status'], 403)
        # Admin can access
        resp = handle(_make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        token_admin = resp['body']['token']
        resp = handle(_make_request('GET', '/admin/reservations', headers={'authorization': f'Bearer {token_admin}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        # Admin listings
        resp = handle(_make_request('GET', '/admin/listings', headers={'authorization': f'Bearer {token_admin}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        # Admin update listing
        resp = handle(_make_request('PUT', '/admin/listings/1', {'price': 999, 'active': 0}, headers={'authorization': f'Bearer {token_admin}'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['listing']['price'], 999)
        self.assertEqual(resp['body']['listing']['active'], 0)

    def test_invalid_inputs(self):
        # Invalid email
        resp = handle(_make_request('POST', '/register', {'email': '', 'password': 'Short'}), self.db_path)
        self.assertEqual(resp['status'], 400)
        # Bool for numeric in quote
        resp = handle(_make_request('POST', '/quote', {'listing_id': 1, 'check_in': '2028-06-01', 'check_out': '2028-06-05', 'party': True}), self.db_path)
        self.assertEqual(resp['status'], 400)
        # Unknown path
        resp = handle(_make_request('GET', '/nonexistent'), self.db_path)
        self.assertEqual(resp['status'], 404)
        # Invalid method
        resp = handle(_make_request('POST', '/listings/1'), self.db_path)
        self.assertEqual(resp['status'], 404)

if __name__ == '__main__':
    unittest.main()