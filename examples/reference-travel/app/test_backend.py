import unittest
import tempfile
import os
import backend
import db
from datetime import date, timedelta

def make_request(method, path, body={}, token=None):
    headers = {}
    if token:
        headers['authorization'] = 'Bearer ' + token
    return {'method': method, 'path': path, 'body': body, 'headers': headers}

class TestBackend(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        conn = db.connect(self.db_path)
        conn.close()
        self.future_in = (date.today() + timedelta(days=90)).isoformat()
        self.future_out = (date.today() + timedelta(days=94)).isoformat()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_health(self):
        resp = backend.handle(make_request('GET', '/health'), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertTrue(resp['body']['ok'])
        self.assertTrue(resp['body']['demo'])

    def test_register_login(self):
        email = 'test@example.test'
        password = 'test12345678'
        resp = backend.handle(make_request('POST', '/register', {'email': email, 'password': password}), self.db_path)
        self.assertEqual(resp['status'], 201)
        self.assertIn('token', resp['body'])
        self.assertEqual(resp['body']['user']['role'], 'user')
        token = resp['body']['token']
        resp2 = backend.handle(make_request('POST', '/login', {'email': email, 'password': password}), self.db_path)
        self.assertEqual(resp2['status'], 200)
        self.assertIn('token', resp2['body'])
        resp3 = backend.handle(make_request('POST', '/login', {'email': email, 'password': 'wrong'}), self.db_path)
        self.assertEqual(resp3['status'], 401)
        self.assertIn('error', resp3['body'])
        resp4 = backend.handle(make_request('POST', '/register', {'email': email, 'password': password}), self.db_path)
        self.assertEqual(resp4['status'], 409)

    def test_register_validation(self):
        resp = backend.handle(make_request('POST', '/register', {'email': 'a@b.com', 'password': 'short'}), self.db_path)
        self.assertEqual(resp['status'], 400)
        resp = backend.handle(make_request('POST', '/register', {'email': '', 'password': 'longenough123'}), self.db_path)
        self.assertEqual(resp['status'], 400)

    def test_admin_login(self):
        resp = backend.handle(make_request('POST', '/login', {'email': 'admin@example.test', 'password': 'DemoAdmin2028!'}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['user']['role'], 'admin')
        return resp['body']['token']

    def test_listings(self):
        resp = backend.handle(make_request('GET', '/listings', {'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertGreaterEqual(resp['body']['total'], 18)
        self.assertGreaterEqual(len(resp['body']['listings']), 12)
        self.assertIn('total', resp['body'])
        # get second page to verify all 18 can be seen
        resp2 = backend.handle(make_request('GET', '/listings', {'page': 2, 'page_size': 12}), self.db_path)
        self.assertEqual(resp2['status'], 200)
        combined = len(resp['body']['listings']) + len(resp2['body']['listings'])
        self.assertGreaterEqual(combined, 18)

    def test_listings_filter(self):
        resp = backend.handle(make_request('GET', '/listings', {'city': 'Lisbon', 'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertEqual(l['city'], 'Lisbon')
        resp = backend.handle(make_request('GET', '/listings', {'max_price': 150, 'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertLessEqual(l['price'], 150)
        resp = backend.handle(make_request('GET', '/listings', {'party': 6, 'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        for l in resp['body']['listings']:
            self.assertGreaterEqual(l['capacity'], 6)
        resp = backend.handle(make_request('GET', '/listings', {'q': 'garden', 'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertGreater(len(resp['body']['listings']), 0)
        resp = backend.handle(make_request('GET', '/listings', {'sort': 'price_asc', 'page_size': 12}), self.db_path)
        self.assertEqual(resp['status'], 200)
        prices = [l['price'] for l in resp['body']['listings']]
        self.assertEqual(prices, sorted(prices))

    def test_listing_detail(self):
        resp = backend.handle(make_request('GET', '/listings', {'page_size': 12}), self.db_path)
        listing_id = resp['body']['listings'][0]['id']
        resp2 = backend.handle(make_request('GET', f'/listings/{listing_id}'), self.db_path)
        self.assertEqual(resp2['status'], 200)
        self.assertEqual(resp2['body']['listing']['id'], listing_id)
        resp3 = backend.handle(make_request('GET', '/listings/99999'), self.db_path)
        self.assertEqual(resp3['status'], 404)

    def test_favorites_requires_auth(self):
        resp = backend.handle(make_request('GET', '/favorites'), self.db_path)
        self.assertEqual(resp['status'], 401)
        resp = backend.handle(make_request('POST', '/favorites', {'listing_id': 1}), self.db_path)
        self.assertEqual(resp['status'], 401)

    def test_favorites(self):
        resp = backend.handle(make_request('POST', '/register', {'email': 'fav@example.test', 'password': 'test12345678'}), self.db_path)
        token = resp['body']['token']
        resp = backend.handle(make_request('GET', '/listings', {'page_size': 12}), self.db_path)
        lid = resp['body']['listings'][0]['id']
        resp = backend.handle(make_request('POST', '/favorites', {'listing_id': lid}, token), self.db_path)
        self.assertEqual(resp['status'], 201)
        resp = backend.handle(make_request('POST', '/favorites', {'listing_id': lid}, token), self.db_path)
        self.assertEqual(resp['status'], 200)
        resp = backend.handle(make_request('GET', '/favorites', {}, token), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(len(resp['body']['favorites']), 1)
        self.assertEqual(resp['body']['favorites'][0]['id'], lid)
        resp = backend.handle(make_request('DELETE', f'/favorites/{lid}', {}, token), self.db_path)
        self.assertEqual(resp['status'], 200)
        resp = backend.handle(make_request('GET', '/favorites', {}, token), self.db_path)
        self.assertEqual(len(resp['body']['favorites']), 0)
        resp = backend.handle(make_request('DELETE', '/favorites/99999', {}, token), self.db_path)
        self.assertEqual(resp['status'], 404)

    def test_itineraries_requires_auth(self):
        resp = backend.handle(make_request('GET', '/itineraries'), self.db_path)
        self.assertEqual(resp['status'], 401)
        resp = backend.handle(make_request('POST', '/itineraries', {'title': 'Test', 'notes': 'notes'}), self.db_path)
        self.assertEqual(resp['status'], 401)

    def test_itineraries(self):
        resp1 = backend.handle(make_request('POST', '/register', {'email': 'user1@example.test', 'password': 'test12345678'}), self.db_path)
        token1 = resp1['body']['token']
        resp2 = backend.handle(make_request('POST', '/register', {'email': 'user2@example.test', 'password': 'test12345678'}), self.db_path)
        token2 = resp2['body']['token']
        resp = backend.handle(make_request('POST', '/itineraries', {'title': 'Trip to Paris', 'notes': 'Fun trip!'}, token1), self.db_path)
        self.assertEqual(resp['status'], 201)
        itin1 = resp['body']['itinerary']
        itin1_id = itin1['id']
        resp = backend.handle(make_request('GET', '/itineraries', {}, token1), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(len(resp['body']['itineraries']), 1)
        resp = backend.handle(make_request('GET', '/itineraries', {}, token2), self.db_path)
        self.assertEqual(len(resp['body']['itineraries']), 0)
        resp = backend.handle(make_request('PUT', f'/itineraries/{itin1_id}', {'title': 'Updated Trip', 'notes': 'Updated notes'}, token1), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['itinerary']['title'], 'Updated Trip')
        resp = backend.handle(make_request('PUT', f'/itineraries/{itin1_id}', {'title': 'Hack', 'notes': ''}, token2), self.db_path)
        self.assertEqual(resp['status'], 404)
        resp = backend.handle(make_request('DELETE', f'/itineraries/{itin1_id}', {}, token1), self.db_path)
        self.assertEqual(resp['status'], 200)
        resp = backend.handle(make_request('DELETE', f'/itineraries/{itin1_id}', {}, token2), self.db_path)
        self.assertEqual(resp['status'], 404)
        resp = backend.handle(make_request('GET', '/itineraries', {}, token1), self.db_path)
        self.assertEqual(len(resp['body']['itineraries']), 0)

    def test_quote_public(self):
        resp = backend.handle(make_request('GET', '/listings', {'page_size': 12}), self.db_path)
        lid = resp['body']['listings'][0]['id']
        price = resp['body']['listings'][0]['price']
        resp = backend.handle(make_request('POST', '/quote', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 2}), self.db_path)
        self.assertEqual(resp['status'], 200)
        q = resp['body']['quote']
        self.assertEqual(q['listing_id'], lid)
        self.assertEqual(q['nights'], 4)
        self.assertEqual(q['nightly'], price)
        self.assertEqual(q['total'], price * 4)
        self.assertEqual(q['currency'], 'EUR')
        resp = backend.handle(make_request('POST', '/quote', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_in, 'party': 2}), self.db_path)
        self.assertEqual(resp['status'], 400)
        resp = backend.handle(make_request('POST', '/quote', {'listing_id': 99999, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 2}), self.db_path)
        self.assertEqual(resp['status'], 404)
        resp = backend.handle(make_request('POST', '/quote', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 99}), self.db_path)
        self.assertEqual(resp['status'], 400)
        resp = backend.handle(make_request('POST', '/quote', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_out, 'party': True}), self.db_path)
        self.assertEqual(resp['status'], 400)

    def test_reservations_auth(self):
        resp = backend.handle(make_request('POST', '/reservations', {'listing_id': 1, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 2, 'request_key': 'testkey12345678'}), self.db_path)  # gitleaks:allow -- fictional idempotency fixture, not a credential
        self.assertEqual(resp['status'], 401)

    def test_reservations(self):
        resp = backend.handle(make_request('POST', '/register', {'email': 'res@example.test', 'password': 'test12345678'}), self.db_path)
        token = resp['body']['token']
        resp = backend.handle(make_request('GET', '/listings'), self.db_path)
        lid = resp['body']['listings'][0]['id']
        price = resp['body']['listings'][0]['price']
        resp = backend.handle(make_request('POST', '/reservations', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 2, 'request_key': 'unique_res_key_123'}, token), self.db_path)  # gitleaks:allow -- fictional idempotency fixture, not a credential
        self.assertEqual(resp['status'], 201)
        res = resp['body']['reservation']
        self.assertEqual(res['listing_id'], lid)
        self.assertEqual(res['total'], price * 4)
        resp = backend.handle(make_request('POST', '/reservations', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 2, 'request_key': 'unique_res_key_123'}, token), self.db_path)  # gitleaks:allow -- fictional idempotency fixture, not a credential
        self.assertEqual(resp['status'], 409)
        resp = backend.handle(make_request('GET', '/reservations', {}, token), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(len(resp['body']['reservations']), 1)
        res_id = res['id']
        resp = backend.handle(make_request('GET', f'/reservations/{res_id}', {}, token), self.db_path)
        self.assertEqual(resp['status'], 200)
        resp2 = backend.handle(make_request('POST', '/register', {'email': 'res2@example.test', 'password': 'test12345678'}), self.db_path)
        token2 = resp2['body']['token']
        resp = backend.handle(make_request('GET', f'/reservations/{res_id}', {}, token2), self.db_path)
        self.assertEqual(resp['status'], 404)

    def test_admin_reservations(self):
        admin_token = self.test_admin_login()
        resp = backend.handle(make_request('POST', '/register', {'email': 'user@example.test', 'password': 'test12345678'}), self.db_path)
        token = resp['body']['token']
        resp = backend.handle(make_request('GET', '/listings'), self.db_path)
        lid = resp['body']['listings'][0]['id']
        resp = backend.handle(make_request('POST', '/reservations', {'listing_id': lid, 'check_in': self.future_in, 'check_out': self.future_out, 'party': 2, 'request_key': 'admin_test_key_1'}, token), self.db_path)  # gitleaks:allow -- fictional idempotency fixture, not a credential
        self.assertEqual(resp['status'], 201)
        resp = backend.handle(make_request('GET', '/admin/reservations', {}, admin_token), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertIn('user_id', resp['body']['reservations'][0])
        resp = backend.handle(make_request('GET', '/admin/reservations', {}, token), self.db_path)
        self.assertEqual(resp['status'], 403)

    def test_admin_listings(self):
        admin_token = self.test_admin_login()
        resp = backend.handle(make_request('GET', '/listings', {'page_size': 12}), self.db_path)
        lid = resp['body']['listings'][0]['id']
        resp = backend.handle(make_request('PUT', f'/admin/listings/{lid}', {'price': 500, 'active': 0}, admin_token), self.db_path)
        self.assertEqual(resp['status'], 200)
        self.assertEqual(resp['body']['listing']['price'], 500)
        self.assertEqual(resp['body']['listing']['active'], 0)
        resp = backend.handle(make_request('POST', '/register', {'email': 'test@example.test', 'password': 'test12345678'}), self.db_path)
        token = resp['body']['token']
        resp = backend.handle(make_request('PUT', f'/admin/listings/{lid}', {'price': 100, 'active': 1}, token), self.db_path)
        self.assertEqual(resp['status'], 403)
        resp = backend.handle(make_request('GET', '/admin/listings', {}, admin_token), self.db_path)
        active_listings = [l for l in resp['body']['listings'] if not l['active']]
        self.assertGreater(len(active_listings), 0)

if __name__ == '__main__':
    unittest.main()
