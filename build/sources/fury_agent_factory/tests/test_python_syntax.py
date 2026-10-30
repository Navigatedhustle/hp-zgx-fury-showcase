"""Syntax diagnostics for rejected generated files, not a replacement compiler."""
import unittest
from devteam import validate_ticket_patch
class PythonSyntaxTests(unittest.TestCase):
 def test_unterminated_sql_gives_actionable_local_diagnostic(self):
  with self.assertRaisesRegex(ValueError,'Python syntax error') as caught:
   validate_ticket_patch({'files':{'backend.py':'conn.execute("CREATE TABLE hotels (\n id INTEGER) ")'}})
  self.assertIn('triple-quoted SQL',str(caught.exception));self.assertIn('1: conn.execute',str(caught.exception))
 def test_valid_multiline_sql_is_preserved(self):
  source='def create(conn):\n conn.execute("""CREATE TABLE hotels (\n id INTEGER\n )""")\n'
  validate_ticket_patch({'files':{'backend.py':source}})
