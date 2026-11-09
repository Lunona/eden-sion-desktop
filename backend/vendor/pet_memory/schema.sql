PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES('schema_version','1');
CREATE TABLE IF NOT EXISTS scopes(
 owner TEXT NOT NULL,pet TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,
 generation INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,pet));
CREATE TABLE IF NOT EXISTS identities(
 owner TEXT NOT NULL,pet TEXT NOT NULL,profile TEXT NOT NULL,revision INTEGER NOT NULL,
 PRIMARY KEY(owner,pet));
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL,owner TEXT NOT NULL,pet TEXT NOT NULL,
 session TEXT NOT NULL,world TEXT NOT NULL,layer TEXT NOT NULL,role TEXT NOT NULL,
 text TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL,
 excluded INTEGER NOT NULL DEFAULT 0,exclusions TEXT NOT NULL DEFAULT '[]',
 UNIQUE(owner,pet,id));
CREATE TABLE IF NOT EXISTS jobs(
 id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,pet TEXT NOT NULL,event_id TEXT,
 memory_id TEXT,revision INTEGER,kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,error TEXT,next_at REAL NOT NULL DEFAULT 0,
 UNIQUE(owner,pet,event_id,kind));
CREATE TABLE IF NOT EXISTS memories(
 rowid INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL,revision INTEGER NOT NULL,
 owner TEXT NOT NULL,pet TEXT NOT NULL,session TEXT NOT NULL,world TEXT NOT NULL,
 layer TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,subject TEXT NOT NULL,
 predicate TEXT NOT NULL,value_json TEXT NOT NULL,qualifiers TEXT NOT NULL,
 fact_key TEXT NOT NULL,text_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',
 verification TEXT NOT NULL,pinned INTEGER NOT NULL DEFAULT 0,
 valid_from TEXT NOT NULL,valid_to TEXT,event_at TEXT,expires_at TEXT,
 created_at TEXT NOT NULL,last_accessed_at TEXT,access_count INTEGER NOT NULL DEFAULT 0,
 PRIMARY_SOURCE TEXT,UNIQUE(owner,pet,id,revision));
CREATE INDEX IF NOT EXISTS memory_scope ON memories(owner,pet,world,status);
CREATE INDEX IF NOT EXISTS memory_fact ON memories(owner,pet,world,fact_key,status);
CREATE TABLE IF NOT EXISTS evidence(
 memory_row INTEGER NOT NULL REFERENCES memories(rowid) ON DELETE CASCADE,
 event_seq INTEGER NOT NULL REFERENCES events(seq),start INTEGER NOT NULL,end INTEGER NOT NULL,
 quote TEXT NOT NULL,UNIQUE(memory_row,event_seq,start,end));
CREATE TABLE IF NOT EXISTS links(
 owner TEXT NOT NULL,pet TEXT NOT NULL,parent_id TEXT NOT NULL,child_id TEXT NOT NULL,
 PRIMARY KEY(owner,pet,parent_id,child_id));
CREATE TABLE IF NOT EXISTS aliases(
 owner TEXT NOT NULL,pet TEXT NOT NULL,world TEXT NOT NULL,entity TEXT NOT NULL,alias TEXT NOT NULL,
 UNIQUE(owner,pet,world,entity,alias));
CREATE TABLE IF NOT EXISTS vectors(
 memory_row INTEGER NOT NULL REFERENCES memories(rowid) ON DELETE CASCADE,
 model TEXT NOT NULL,dimension INTEGER NOT NULL,vector TEXT NOT NULL,
 PRIMARY KEY(memory_row,model));
CREATE TABLE IF NOT EXISTS deleted(
 owner TEXT NOT NULL,pet TEXT NOT NULL,id TEXT NOT NULL,PRIMARY KEY(owner,pet,id));
CREATE TABLE IF NOT EXISTS blocked_texts(
 owner TEXT NOT NULL,pet TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(owner,pet,digest));
CREATE TABLE IF NOT EXISTS replayed_deletions(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS operations(
 owner TEXT NOT NULL,pet TEXT NOT NULL,key TEXT NOT NULL,operation TEXT NOT NULL,
 fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(owner,pet,key));
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(tokens,tokenize='unicode61');
