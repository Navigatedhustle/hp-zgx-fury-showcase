"""Add seeded v2 synthetic entity relationships without changing any v1 analytics rows."""
import csv,json,sqlite3
from atlas.config import DB,ROOT
from atlas.data.generate import COLLEGES

def ensure():
    with sqlite3.connect(DB) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS knowledge_policies(id TEXT PRIMARY KEY,name TEXT,value REAL,unit TEXT);
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,name TEXT);
        CREATE TABLE IF NOT EXISTS deal_products(deal_id TEXT PRIMARY KEY,product_id TEXT);
        CREATE TABLE IF NOT EXISTS principal_investigators(id TEXT PRIMARY KEY,name TEXT,college TEXT);
        CREATE TABLE IF NOT EXISTS grant_investigators(grant_id TEXT PRIMARY KEY,pi_id TEXT);
        CREATE TABLE IF NOT EXISTS programs(id TEXT PRIMARY KEY,name TEXT,college TEXT);
        ''')
        c.executemany('INSERT OR IGNORE INTO knowledge_policies VALUES (?,?,?,?)',[('discount_approval','Finance approval exposure threshold',1500000,'USD'),('cost_share','Default required cost share',0,'ratio')])
        if not c.execute('SELECT COUNT(*) FROM products').fetchone()[0]:
            c.executemany('INSERT INTO products VALUES (?,?)',[(f'P{i:02}',name) for i,name in enumerate(['Edge systems','Data platforms','Secure infrastructure','Analytics services'],1)])
            deals=c.execute('SELECT id FROM pipeline UNION SELECT id FROM closed_deals ORDER BY id').fetchall()
            c.executemany('INSERT INTO deal_products VALUES (?,?)',[(r[0],f'P{i%4+1:02}') for i,r in enumerate(deals)])
            pis=[(f'PI{i:02}',f'Dr. Avery {i:02}',college) for i,college in enumerate(COLLEGES*2,1)]
            c.executemany('INSERT INTO principal_investigators VALUES (?,?,?)',pis)
            grants=c.execute('SELECT id,college FROM grant_history UNION SELECT id,college FROM grant_pipeline ORDER BY id').fetchall()
            c.executemany('INSERT INTO grant_investigators VALUES (?,?)',[(g,next(p[0] for p in (pis if i%2 else pis[::-1]) if p[2]==college)) for i,(g,college) in enumerate(grants)])
            c.executemany('INSERT INTO programs VALUES (?,?,?)',[(f'PR{i:02}',f'{college} {level}',college) for i,(college,level) in enumerate([(c,l) for c in COLLEGES for l in ['Undergraduate','Graduate']],1)])
        for table in ['knowledge_policies','products','deal_products','principal_investigators','grant_investigators','programs']:
            cur=c.execute('SELECT * FROM '+table)
            with (ROOT/'data/csv'/f'{table}.csv').open('w') as f:
                writer=csv.writer(f);writer.writerow([d[0] for d in cur.description]);writer.writerows(cur)
    return True
if __name__=='__main__':ensure()
