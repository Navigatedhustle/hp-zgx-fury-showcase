"""Trusted API oracle ONLY for checking generated QA, never a published backend.

Generated tests run against this fixture first to reject contradictions in the
public contract. Actual release tests still run against model-generated code.
"""
import json,re,sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

def handle(request,db_path):
 config=json.loads(Path(__file__).with_name('qa-reference.json').read_text());hotels=config['hotels']
 method=request.get('method');path=request.get('path');body=request.get('body') or {}
 def reply(status,**payload):
  if 'error' in payload:payload={key:payload['error'] for key in config['error_fields'].get(str(status),['error'])}
  return {'status':status,'body':payload}
 with closing(sqlite3.connect(db_path)) as db, db:
  db.execute('CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY,hotel_id INTEGER,guest TEXT,date TEXT,UNIQUE(hotel_id,date))')
  if method=='GET' and path=='/hotels':return reply(200,hotels=hotels)
  if method=='GET' and path=='/bookings':
   rows=db.execute('SELECT id,hotel_id,guest,date FROM reservations ORDER BY id').fetchall()
   return reply(200,bookings=[dict(zip(('id','hotel_id','guest','date'),r)) for r in rows])
  if method!='POST' or path!='/bookings':return reply(404,error='Unknown route')
  if not isinstance(body,dict):return reply(400,error='Request body must be an object')
  hid=body.get('hotel_id');guest=body.get('guest');day=body.get('date')
  if type(hid) is not int:return reply(400,error='Hotel ID must be an integer')
  if hid not in [h['id'] for h in hotels]:return reply(404,error='Unknown hotel')
  if not isinstance(guest,str) or not 1<=len(guest.strip())<=120:return reply(400,error='Guest must have1 to120 characters')
  if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):return reply(400,error='Date must be YYYY-MM-DD')
  try:date.fromisoformat(day)
  except ValueError:return reply(400,error='Invalid calendar date')
  try:
   cursor=db.execute('INSERT INTO reservations(hotel_id,guest,date) VALUES(?,?,?)',(hid,guest.strip(),day))
  except sqlite3.IntegrityError:return reply(409,error='Hotel already booked on that date')
  booking={'id':cursor.lastrowid,'hotel_id':hid,'guest':guest.strip(),'date':day}
  return reply(201,booking=booking)
