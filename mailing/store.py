"""Local verification store; cloud deployment must use durable atomic shared storage."""
import json,sqlite3
from contextlib import contextmanager
from pathlib import Path
class LocalStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY,body TEXT,status TEXT,result TEXT)')
    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path,timeout=15)
        try:
            with connection:yield connection
        finally:connection.close()
    def claim(self,key,body):
        with self.connect() as c:
            try:c.execute('INSERT INTO deliveries VALUES(?,?,?,?)',(key,json.dumps(body),'claimed','{}'));return True
            except sqlite3.IntegrityError:return False
    def finish(self,key,status,result):
        with self.connect() as c:c.execute('UPDATE deliveries SET status=?,result=? WHERE id=?',(status,json.dumps(result),key))
    def sent_dois(self,email):
        with self.connect() as c:rows=c.execute('SELECT body FROM deliveries').fetchall()
        # Claimed/unknown may have been accepted; exclude until an administrator resolves them.
        return [r['doi'] for (raw,) in rows if (r:=json.loads(raw))['recipient'].lower()==email.lower()]
