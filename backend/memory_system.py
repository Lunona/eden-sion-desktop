"""Source-backed associative memory. Derived tables share the authoritative DB.

No additional model is loaded here. Every read receives the core's already scoped,
current, source-valid rows; graph expansion cannot widen that visibility.
"""
import hashlib,json,re,time,math,threading
from collections import OrderedDict,defaultdict
from datetime import datetime,timezone
from pet_memory.types import dumps,now,normalized,terms,require
from companionship_memory import memory_category

TOPICS=('咖啡','美式','拿铁','乌龙茶','饮品','猫','狗','生日','称呼','工作','项目','学校','旅行','约定','诗音','头发','裙子','袖子','眼睛','记忆','语音','Live2D','eden')
IMPORTANT=re.compile(r'^(?:请)?(?:帮我)?(?:(?:永远|一定|务必|牢牢|长期|永久)(?:要)?)?记住[：:，,\s]*(.+)$',re.S)
NONFACT=('例如','比如','假设','假如','如果','“','"','「','你觉得')

def explicit_payload(event):
    if event['role']!='user':return None
    match=IMPORTANT.match(event['text'].strip())
    if not match:return None
    text=next(x for x in match.groups() if x).strip()
    return text if text and not text.startswith(NONFACT) else None

def local_tags(text):
    found=[w for w in TOPICS if w.casefold() in text.casefold()]
    found+=re.findall(r'[「“"]([^」”"\n]{2,24})[」”"]',text)
    found+=re.findall(r'(?<![a-zA-Z])[a-zA-Z][a-zA-Z0-9_+.-]{2,24}',text)
    found+=re.findall(r'(?:名叫|名字是|叫做|叫)([\u4e00-\u9fff]{1,8})(?=[，。！!？?\s]|$)',text)
    return list(dict.fromkeys(w.strip() for w in found if w.strip()))[:12]

class MemorySystem:
    def __init__(self,host):
        self.h=host;self.m=host.rt.memory;self.cache={};self.annotations=OrderedDict();self.note_cache={}
        self.graph_dirty=threading.Event()
        with self.m.lock:
            self.m.db.executescript('''
            CREATE TABLE IF NOT EXISTS sion_memory_meta(
              memory_row INTEGER PRIMARY KEY REFERENCES memories(rowid) ON DELETE CASCADE,
              importance REAL NOT NULL DEFAULT .5, useful INTEGER NOT NULL DEFAULT 0,
              unhelpful INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sion_memory_terms(
              memory_row INTEGER NOT NULL REFERENCES memories(rowid) ON DELETE CASCADE,
              label TEXT NOT NULL, PRIMARY KEY(memory_row,label));
            CREATE INDEX IF NOT EXISTS sion_terms_label ON sion_memory_terms(label);
            CREATE TABLE IF NOT EXISTS sion_usage(
              day TEXT NOT NULL,purpose TEXT NOT NULL,calls INTEGER NOT NULL DEFAULT 0,
              input_tokens INTEGER NOT NULL DEFAULT 0,output_tokens INTEGER NOT NULL DEFAULT 0,
              measured INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day,purpose));
            CREATE TABLE IF NOT EXISTS sion_deepseek_memory_cache(
              day TEXT NOT NULL,purpose TEXT NOT NULL,measured INTEGER NOT NULL,
              input_tokens INTEGER NOT NULL,cached_tokens INTEGER NOT NULL,PRIMARY KEY(day,purpose));
            CREATE TABLE IF NOT EXISTS sion_documents(
              memory_row INTEGER PRIMARY KEY REFERENCES memories(rowid) ON DELETE CASCADE,
              title TEXT NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sion_secret_thoughts(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              turn_id TEXT, content TEXT NOT NULL, emotion TEXT NOT NULL DEFAULT '',
              stage TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sion_open_loops(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              topic TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sion_diaries(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              kind TEXT NOT NULL DEFAULT 'diary', content TEXT NOT NULL,
              emotion TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sion_soul_state(
              owner TEXT NOT NULL, pet TEXT NOT NULL,
              recall_depth REAL NOT NULL DEFAULT 0.0,
              impression_depth REAL NOT NULL DEFAULT 0.0,
              expression_desire REAL NOT NULL DEFAULT 0.0,
              creativity REAL NOT NULL DEFAULT 0.0,
              updated_at TEXT NOT NULL, PRIMARY KEY(owner,pet));
            CREATE TABLE IF NOT EXISTS sion_state_continuity(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'general', state_text TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sion_dialogue_episodes(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              summary TEXT NOT NULL, turn_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sion_user_profile(
              owner TEXT NOT NULL, pet TEXT NOT NULL, attr_key TEXT NOT NULL,
              attr_label TEXT NOT NULL, attr_value TEXT NOT NULL,
              updated_at TEXT NOT NULL, PRIMARY KEY(owner,pet,attr_key));
            CREATE TABLE IF NOT EXISTS sion_lm_nodes(
              id INTEGER PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              node_key TEXT NOT NULL, node_type TEXT NOT NULL,
              label TEXT NOT NULL, canonical_value TEXT NOT NULL,
              metadata TEXT NOT NULL DEFAULT '{}', UNIQUE(owner,pet,node_key));
            CREATE TABLE IF NOT EXISTS sion_lm_edges(
              id INTEGER PRIMARY KEY, owner TEXT NOT NULL, pet TEXT NOT NULL,
              edge_key TEXT NOT NULL, source_node_id INTEGER NOT NULL,
              target_node_id INTEGER NOT NULL, relation_type TEXT NOT NULL,
              source_memory_id TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0,
              confidence REAL NOT NULL DEFAULT 0.85,
              metadata TEXT NOT NULL DEFAULT '{}', UNIQUE(owner,pet,edge_key));
            CREATE TRIGGER IF NOT EXISTS sion_erase_derived AFTER UPDATE OF status ON memories
            WHEN NEW.status='deleted' BEGIN
              DELETE FROM sion_memory_terms WHERE memory_row=NEW.rowid;
              DELETE FROM sion_memory_meta WHERE memory_row=NEW.rowid;
              DELETE FROM sion_documents WHERE memory_row=NEW.rowid;
            END;
            ''')
            for table in ('sion_secret_thoughts','sion_open_loops','sion_diaries',
                          'sion_state_continuity','sion_dialogue_episodes','sion_user_profile'):
                if 'source_refs' not in {row[1] for row in self.m.db.execute(f'PRAGMA table_info({table})')}:
                    self.m.db.execute(f'ALTER TABLE {table} ADD COLUMN source_refs TEXT')
            for table in ('sion_memory_meta','sion_memory_terms','sion_documents'):
                self.m.db.execute(f"DELETE FROM {table} WHERE memory_row NOT IN (SELECT rowid FROM memories WHERE status<>'deleted')")
        self.m.on_store=self.on_store;self.m.rank_extension=self.rank

    def on_store(self,rowid,event,quote):
        row=self.m.db.execute('SELECT * FROM memories WHERE rowid=?',(rowid,)).fetchone()
        if row is None:return
        annotation=self.annotations.pop(self.annotation_key(event,quote),{})
        if annotation.pop('_until',0)<time.monotonic():annotation={}
        important=bool(explicit_payload(event))
        previous=self.m.db.execute('SELECT x.* FROM sion_memory_meta x JOIN memories m ON m.rowid=x.memory_row WHERE m.owner=? AND m.pet=? AND m.id=? AND m.revision<? ORDER BY m.revision DESC LIMIT 1',(row['owner'],row['pet'],row['id'],row['revision'])).fetchone()
        # A repeated extraction cannot undo a manual policy decision. Corrections
        # inherit the existing policy and feedback rather than a new model score.
        score=previous['importance'] if previous else annotation.get('importance',.85 if important else .6 if row['kind'] in ('relationship','preference','plan') else .5)
        new_meta=self.m.db.execute('INSERT OR IGNORE INTO sion_memory_meta VALUES(?,?,?,?,?)',(rowid,score,previous['useful'] if previous else 0,previous['unhelpful'] if previous else 0,now())).rowcount==1
        labels=local_tags(quote)+annotation.get('topics',[])
        labels+=[r[0] for r in self.m.db.execute("SELECT DISTINCT t.label FROM sion_memory_terms t JOIN memories m ON m.rowid=t.memory_row WHERE m.owner=? AND m.pet=? AND m.world=? AND m.layer=? AND m.status='active' AND length(t.label)>1 AND instr(?,t.label)>0 LIMIT 6",(row['owner'],row['pet'],row['world'],row['layer'],quote))]
        for label in dict.fromkeys(labels):
            clean_label=str(label).strip()[:24]
            if len(clean_label)>=2:self.m.db.execute('INSERT OR IGNORE INTO sion_memory_terms VALUES(?,?)',(rowid,clean_label))
        # Only the first source may automatically protect a new memory. Replaying
        # the same event must not reverse a user's subsequent unpin operation.
        if important and new_meta and not previous:self.m.db.execute('UPDATE memories SET pinned=1 WHERE rowid=?',(rowid,))
        self.cache.clear()
        self.graph_dirty.set()

    @staticmethod
    def annotation_key(event,quote):
        event=dict(event)
        return (event.get('owner'),event.get('pet'),event.get('seq'),event['id'],hashlib.sha256((event['text']+'\0'+quote).encode()).digest())

    def stage_annotations(self,entries):
        # Keys retain source hashes, not source quotes. Validated topics/scores
        # have a bounded size and can no longer be consumed after expiry.
        with self.m.lock:
            cutoff=time.monotonic()
            for key in list(self.annotations):
                if self.annotations[key].get('_until',0)<cutoff:self.annotations.pop(key,None)
            for event,quote,data in entries:
                self.annotations[self.annotation_key(event,quote)]={**data,'_until':cutoff+60}
            while len(self.annotations)>512:self.annotations.popitem(last=False)

    def ensure_meta(self,rows):
        return self.metadata(rows)

    def metadata(self,rows):
        by={r['rowid']:r for r in rows};ids=list(by);out={}
        # Bounded SQL batches, without a content cache that could survive erase,
        # restore, history filtering or another connection's correction.
        for offset in range(0,len(ids),400):
            batch=ids[offset:offset+400];marks=','.join('?' for _ in batch)
            for value in self.m.db.execute(f'SELECT * FROM sion_memory_meta WHERE memory_row IN ({marks})',batch):
                out[value['memory_row']]={**dict(value),'topics':[]}
            missing=[by[rid] for rid in batch if rid not in out]
            stamp=now();values=[(r['rowid'],.85 if r['pinned'] else .6 if r['kind'] in ('preference','relationship','plan') else .5,0,0,stamp) for r in missing]
            self.m.db.executemany('INSERT OR IGNORE INTO sion_memory_meta VALUES(?,?,?,?,?)',values)
            self.m.db.executemany('INSERT OR IGNORE INTO sion_memory_terms VALUES(?,?)',[(r['rowid'],label) for r in missing for label in local_tags(r['text'])])
            for rid,importance,useful,unhelpful,updated_at in values:out[rid]=dict(memory_row=rid,importance=importance,useful=useful,unhelpful=unhelpful,updated_at=updated_at,topics=[])
            for rid,label in self.m.db.execute(f'SELECT memory_row,label FROM sion_memory_terms WHERE memory_row IN ({marks}) ORDER BY memory_row,label',batch):out[rid]['topics'].append(label)
        return out

    def rank(self,scope,query,rows,scores,reasons):
        if not rows:return []
        meta=self.metadata(rows);by={r['rowid']:r for r in rows};posting=defaultdict(set)
        for rid,data in meta.items():
            for label in data['topics']:posting[(by[rid]['world'],by[rid]['layer'],normalized(label))].add(rid)
        nq=normalized(query);seeds={rid for (_,_,label),ids in posting.items() if (len(label)>1 or label==nq) and label in nq for rid in ids}
        # One-character topics are excluded from the stored term index. An
        # existing exact match can still seed traversal through named entities.
        broad={normalized(t) for t in TOPICS}
        if len(nq)==1 and nq in broad:
            seeds.update(rid for rid in scores if 'entity_or_exact' in reasons.get(rid,()) and nq in normalized(by[rid]['text']))
        # Broad subjects can seed a match but never bridge distinct records.
        paths={rid:[] for rid in seeds}
        strength={rid:1. for rid in seeds};first=set(seeds)
        for depth in range(2):
            nxt=set()
            for rid in sorted(first,key=lambda r:(-scores.get(r,0),by[r]['text_hash'],by[r]['id']))[:24]:
                for label in meta[rid]['topics']:
                    key=normalized(label)
                    if key in broad or len(key)<2:continue
                    neighbors=posting[(by[rid]['world'],by[rid]['layer'],key)]
                    if len(neighbors)>min(24,max(4,len(rows)//3)):continue
                    rarity=math.log(1+len(rows)/max(1,len(neighbors)))/math.log(1+len(rows))
                    for other in neighbors:
                        if other not in seeds:
                            value=strength[rid]*.55*rarity
                            if value>strength.get(other,0):
                                nxt.add(other);strength[other]=value;paths[other]=paths[rid]+[by[rid]['id'],label]
            seeds.update(nxt);first=nxt
        for rank,rid in enumerate(sorted(seeds,key=lambda r:(-strength[r],-scores.get(r,0),by[r]['text_hash'],by[r]['id']))[:40],1):
            scores[rid]=scores.get(rid,0)+.55*strength[rid]/(60+rank)
            reasons.setdefault(rid,[]).append('graph_association')
        # Importance never competes without a real retrieval signal; no time
        # multiplier can drive a relevant old fixed memory to zero.
        for rid in scores:
            data=meta[rid];row=by[rid]
            signal=max(0,scores[rid]);boost=.12*data['importance']+.12*bool(row['pinned'])+.04*min(data['useful'],4)-.02*min(data['unhelpful'],4)
            scores[rid]=signal*(1+boost)
        self.cache={'scope':(scope.owner_id,scope.companion_id,tuple(scope.visible_world_ids)),
                    'snapshot':self.m._state(scope)[0],'query':normalized(query),
                    'paths':{(by[r]['id'],by[r]['revision']):v for r,v in paths.items() if v}}
        ranked=sorted(scores,key=lambda rid:(-scores[rid],-bool(by[rid]['pinned']),by[rid]['text_hash'],by[rid]['id']))
        for rid in ranked[:3]:
            if scores.get(rid,0)>=0.35:
                self.m.db.execute('UPDATE sion_memory_meta SET importance=MIN(1.0,importance+0.015),updated_at=? WHERE memory_row=?',(now(),rid))
        return ranked

    def annotate(self,scope,items,query=None):
        with self.m.lock:
            rows=[]
            # Annotate the actual revision returned, including a historical view;
            # looking up today's active row would silently mix two revisions.
            for offset in range(0,len(items),200):
                selected=items[offset:offset+200]
                if not selected:continue
                clauses=' OR '.join('(id=? AND revision=?)' for _ in selected)
                args=[scope.owner_id,scope.companion_id,*[v for i in selected for v in (i['memory_id'],i['revision'])]]
                rows.extend(r for r in self.m.db.execute(f"SELECT * FROM memories WHERE owner=? AND pet=? AND status<>'deleted' AND ({clauses})",args) if r['world'] in scope.visible_world_ids)
            visible={(r['id'],r['revision']):r for r in rows}
            meta=self.metadata(rows)
            same=self.cache.get('scope')==(scope.owner_id,scope.companion_id,tuple(scope.visible_world_ids)) and self.cache.get('snapshot')==self.m._state(scope)[0] and (query is None or self.cache.get('query')==normalized(query))
            for item in items:
                key=(item['memory_id'],item['revision']);row=visible.get(key)
                if row:
                    path=self.cache.get('paths',{}).get(key,[]) if same else []
                    item['category']=memory_category(item)
                    item['assertion']='pending_review' if item['status']=='candidate' else item['verification']
                    if item['status'] in ('active','candidate') and item['expires_at'] and item['expires_at']<=now():
                        item['status']='expired'
                    d=meta[row['rowid']];item.update(importance=d['importance'],useful_count=d['useful'],topics=d['topics'],association_path=path)
        return items

    def graph(self,scope,query='',focus=None,full_graph=False):
        with self.m.lock:
            all_rows=self.m._visible_rows(scope);meta=self.metadata(all_rows)
            rows=list(all_rows)
            focus_str=str(focus).strip() if focus not in (None,'') else ''
            if focus_str:
                selected=[r for r in rows if r['id']==focus_str or str(r['rowid'])==focus_str or r['id']==f'lm-{focus_str}']
                if selected:
                    focus_ids={r['id'] for r in selected}
                    labels={(r['world'],r['layer'],normalized(t)) for r in selected for t in meta[r['rowid']]['topics']}
                    rows=[r for r in rows if r['id'] in focus_ids or any((r['world'],r['layer'],normalized(t)) in labels for t in meta[r['rowid']]['topics'])]
            if query:
                q=normalized(query);rows=[r for r in rows if q in normalized(r['text']) or any(normalized(t) in q or q in normalized(t) for t in meta[r['rowid']]['topics'])]
            total=len(rows);limit_rows=200 if full_graph else 40
            rows=sorted(rows,key=lambda r:(-bool(r['pinned']),-meta[r['rowid']]['importance'],r['id']))[:limit_rows]
            nodes=[];edges=[];entities={}
            for r in rows:
                mid='m:'+r['id'];nodes.append({'id':mid,'kind':'memory','label':r['text'][:42],'memory_id':r['id'],'importance':meta[r['rowid']]['importance'],'pinned':bool(r['pinned']),'world':r['world'],'layer':r['layer']})
                for label in meta[r['rowid']]['topics'][:6]:
                    eid='t:'+hashlib.sha256((r['world']+'|'+r['layer']+'|'+label).encode()).hexdigest()[:18]
                    entities[eid]={'id':eid,'kind':'topic','label':label,'world':r['world'],'layer':r['layer']}
                    edges.append({'source':mid,'target':eid,'kind':'mentions','source_memory_id':r['id']})
            nodes+=list(entities.values())

            # Build LivingMemory 2D Force-Directed Graph Snapshot
            lm_nodes_by_id={}
            lm_key_to_id={}
            for nr in self.m.db.execute('SELECT * FROM sion_lm_nodes WHERE owner=? AND pet=?',(scope.owner_id,scope.companion_id)):
                nid=int(nr['id'])
                lbl=str(nr['label'] or nr['canonical_value'] or '')
                if nr['node_type']=='person' and lbl=='3432018343':lbl='诗音 (3432018343)'
                lm_nodes_by_id[nid]={
                    'id':nid,'type':nr['node_type'] or 'topic','label':lbl,
                    'canonical_value':nr['canonical_value'] or lbl,
                    'weight':1.0,'degree':0,'memory_count':0,'entry_count':1,
                    'memory_ids':set(),
                }
                lm_key_to_id[nr['node_key']]=nid

            lm_edges_list=[]
            covered_mem_ids=set()
            mem_str_to_int={}
            for r in all_rows:
                m_str=str(r['id'])
                if m_str.startswith('lm-') and m_str[3:].isdigit():
                    mem_str_to_int[m_str]=int(m_str[3:])
                else:
                    mem_str_to_int[m_str]=10000+int(r['rowid'])

            for er in self.m.db.execute('SELECT * FROM sion_lm_edges WHERE owner=? AND pet=?',(scope.owner_id,scope.companion_id)):
                s_id=int(er['source_node_id']);t_id=int(er['target_node_id'])
                if s_id not in lm_nodes_by_id or t_id not in lm_nodes_by_id:continue
                m_str=str(er['source_memory_id'])
                covered_mem_ids.add(m_str)
                m_int=mem_str_to_int.get(m_str, int(m_str[3:]) if m_str.startswith('lm-') and m_str[3:].isdigit() else 0)
                lm_edges_list.append({
                    'id':int(er['id']),'source':s_id,'target':t_id,
                    'relation_type':er['relation_type'] or 'describes',
                    'kind':'mentions',
                    'memory_id':m_int,'raw_memory_id':m_str,
                    'weight':float(er['weight'] or 1.0),'confidence':float(er['confidence'] or 0.85),
                })

            next_synth_nid=[max(lm_nodes_by_id.keys(),default=1000)+1000]
            next_synth_eid=[max((e['id'] for e in lm_edges_list),default=5000)+1000]

            def ensure_lm_node(ntype,label,cval=None):
                clean=str(label or '').strip()[:48]
                if not clean:return None
                nkey=f"{ntype}:{cval or clean.casefold()}"
                if nkey in lm_key_to_id:return lm_key_to_id[nkey]
                nid=next_synth_nid[0];next_synth_nid[0]+=1
                lm_key_to_id[nkey]=nid
                lm_nodes_by_id[nid]={
                    'id':nid,'type':ntype,'label':clean,'canonical_value':cval or clean,
                    'weight':1.0,'degree':0,'memory_count':0,'entry_count':1,'memory_ids':set(),
                }
                return nid

            def add_lm_edge(s_id,t_id,rel,m_int,m_str,w=1.0,conf=0.85):
                if not s_id or not t_id or s_id==t_id:return
                eid=next_synth_eid[0];next_synth_eid[0]+=1
                lm_edges_list.append({
                    'id':eid,'source':s_id,'target':t_id,'relation_type':rel,'kind':'mentions',
                    'memory_id':m_int,'raw_memory_id':m_str,'weight':w,'confidence':conf,
                })

            known_user_name='璃诺娜' if any('璃诺娜' in r['text'] for r in all_rows) or any(n['label']=='璃诺娜' for n in lm_nodes_by_id.values()) else '你'
            for r in all_rows:
                m_str=str(r['id'])
                if m_str in covered_mem_ids:continue
                m_int=mem_str_to_int.get(m_str,10000+int(r['rowid']))
                txt=str(r['text'] or '').strip()
                if not txt:continue
                p_names=[]
                for cand in ('璃诺娜','诗音','弥赛亚','琉璃','艾莉卡','拉比','夏目'):
                    if cand in txt:p_names.append(cand)
                for m_name in re.findall(r'(?:我叫|名叫|名字是|称呼我|叫我)([\u4e00-\u9fff]{1,6})',txt):
                    if m_name not in p_names:p_names.append(m_name)
                if not p_names:
                    if '我' in txt or r['subject']=='user':p_names.append(known_user_name)
                    if '你' in txt or '诗音' in txt or r['layer']=='shared_experience':
                        if '诗音' not in p_names:p_names.append('诗音')
                p_ids=[ensure_lm_node('person',pn) for pn in dict.fromkeys(p_names)]
                p_ids=[pid for pid in p_ids if pid]

                t_labels=list(meta[r['rowid']]['topics'][:6])
                kind_map={'preference':'饮食与偏好','relationship':'称呼与羁绊','plan':'日常约定','episode':'日常相处','note':'随手记事'}
                if r['kind'] in kind_map and kind_map[r['kind']] not in t_labels:
                    t_labels.append(kind_map[r['kind']])
                for phrase in re.findall(r'(?:喜欢|习惯|讨厌|想要|计划|约定|关于|打开|使用)([\u4e00-\u9fffA-Za-z0-9]{2,8})',txt):
                    if phrase not in t_labels:t_labels.append(phrase)
                t_ids=[ensure_lm_node('topic',tl) for tl in dict.fromkeys(t_labels[:6])]
                t_ids=[tid for tid in t_ids if tid]

                clauses=[c.strip() for c in re.split(r'[；;。！!？?\n|]+',txt) if len(c.strip())>=2][:4]
                if not clauses:clauses=[txt[:48]]
                f_ids=[ensure_lm_node('fact',cl[:48],f"fact:{m_str}:{idx}") for idx,cl in enumerate(clauses)]
                f_ids=[fid for fid in f_ids if fid]

                for fid in f_ids:
                    for tid in t_ids:add_lm_edge(tid,fid,'describes',m_int,m_str,1.0,0.86)
                    for pid in p_ids:add_lm_edge(pid,fid,'mentioned_in',m_int,m_str,1.1,0.9)
                if len(p_ids)>=2:
                    add_lm_edge(p_ids[0],p_ids[1],'co_occurs_with',m_int,m_str,1.2,0.88)
                elif p_ids and t_ids:
                    add_lm_edge(p_ids[0],t_ids[0],'co_occurs_with',m_int,m_str,1.0,0.82)

            # Deep memory summary nodes (diaries & episodes)
            diaries=self.recent_diaries(scope,6)
            episodes=self.recent_dialogue_episodes(scope,4)
            sion_pid=ensure_lm_node('person','诗音') if (diaries or episodes) else None
            for d in diaries:
                sid=ensure_lm_node('summary',('梦境：' if d['kind']=='dream' else '日记：')+d['content'][:34],f"diary:{d['id']}")
                if sid and sion_pid:add_lm_edge(sion_pid,sid,'mentioned_in',900001,'diary:'+d['id'],1.15,0.92)
            for ep in episodes:
                sid=ensure_lm_node('summary',ep['summary'][:38],f"ep:{ep['id']}")
                if sid and sion_pid:add_lm_edge(sion_pid,sid,'describes',900002,'ep:'+ep['id'],1.1,0.9)

            # Accumulate degree & memory_count
            for e in lm_edges_list:
                for endpoint in (e['source'],e['target']):
                    nd=lm_nodes_by_id.get(endpoint)
                    if nd:
                        nd['degree']+=1
                        if e['memory_id']:nd['memory_ids'].add(e['memory_id'])
            for nd in lm_nodes_by_id.values():
                nd['memory_count']=max(1,len(nd['memory_ids']))
                nd['weight']=round(1.0+nd['degree']*0.35+nd['memory_count']*0.6,2)

            total_lm_nodes=len(lm_nodes_by_id)
            total_lm_edges=len(lm_edges_list)
            type_breakdown=defaultdict(int)
            for nd in lm_nodes_by_id.values():type_breakdown[nd['type']]+=1
            rel_breakdown=defaultdict(int)
            for e in lm_edges_list:rel_breakdown[e['relation_type']]+=1

            # Filter subgraph for focus or query
            active_node_ids=set(lm_nodes_by_id.keys())
            if focus_str:
                target_m_ints=set()
                if focus_str.isdigit():target_m_ints.add(int(focus_str))
                for r in all_rows:
                    if r['id']==focus_str or str(r['rowid'])==focus_str or r['id']==f'lm-{focus_str}':
                        target_m_ints.add(mem_str_to_int.get(str(r['id']),0))
                seed_nodes={n for e in lm_edges_list if e['memory_id'] in target_m_ints or e['raw_memory_id']==focus_str for n in (e['source'],e['target'])}
                if seed_nodes:
                    active_node_ids=set(seed_nodes)
            elif query:
                q_norm=normalized(query)
                matched_m_ints={mem_str_to_int[str(r['id'])] for r in rows if str(r['id']) in mem_str_to_int}
                seed_nodes={nid for nid,nd in lm_nodes_by_id.items() if q_norm in normalized(nd['label']) or any(m in matched_m_ints for m in nd['memory_ids'])}
                if seed_nodes:
                    hop1=set(seed_nodes)
                    for e in lm_edges_list:
                        if e['source'] in seed_nodes or e['target'] in seed_nodes:
                            hop1.add(e['source']);hop1.add(e['target'])
                    active_node_ids=hop1

            if not full_graph and not query and not focus_str and len(active_node_ids)>180:
                ranked_nids=sorted(active_node_ids,key=lambda nid:(
                    1 if lm_nodes_by_id[nid]['type']=='person' else 0,
                    lm_nodes_by_id[nid]['degree']*2+lm_nodes_by_id[nid]['memory_count']*3+lm_nodes_by_id[nid]['weight']
                ),reverse=True)[:180]
                active_node_ids=set(ranked_nids)

            snap_nodes=[]
            for nid in sorted(active_node_ids):
                nd=dict(lm_nodes_by_id[nid])
                nd.pop('memory_ids',None)
                snap_nodes.append(nd)
            snap_edges=[e for e in lm_edges_list if e['source'] in active_node_ids and e['target'] in active_node_ids]
            snap_memories=[{
                'id':mem_str_to_int.get(str(r['id']),int(r['rowid'])),
                'memory_id':r['id'],'rowid':r['rowid'],
                'summary':r['text'],'text':r['text'],
                'layer':r['layer'],'kind':r['kind'],
                'importance':meta[r['rowid']]['importance'],
                'pinned':bool(r['pinned']),
                'topics':meta[r['rowid']]['topics'][:8],
                'created_at':r['created_at'],
            } for r in rows]

            sessions_cnt=max(2 if total_lm_nodes>50 else 1,len({r['layer'] for r in all_rows}))
            return {
                'nodes':nodes,'edges':edges,
                'total_memories':len(all_rows),'shown_memories':len(rows),
                'limited':len(all_rows)>len(rows) or total_lm_nodes>len(snap_nodes),
                'source_backed':True,
                'mode':'memory_focus' if focus_str else ('query' if query else 'overview'),
                'full_graph':bool(full_graph),
                'snapshot':{'nodes':snap_nodes,'edges':snap_edges,'memories':snap_memories},
                'summary':{
                    'total_memories':len(all_rows),
                    'nodes':total_lm_nodes,
                    'edges':total_lm_edges,
                    'sessions':sessions_cnt,
                    'shown_nodes':len(snap_nodes),
                    'shown_edges':len(snap_edges),
                    'node_type_breakdown':dict(type_breakdown),
                    'relation_breakdown':dict(rel_breakdown),
                },
            }

    def sync_livingmemory(self,scope,db_path=None):
        from pathlib import Path
        import sqlite3 as _sqlite3
        target=Path(db_path) if db_path else (Path.home()/'.astrbot'/'data'/'plugin_data'/'astrbot_plugin_livingmemory'/'livingmemory.db')
        if not target.is_file():
            raise ValueError(f'未找到 LivingMemory 数据库：{target}')
        src=_sqlite3.connect(str(target))
        src.row_factory=_sqlite3.Row
        try:
            docs=src.execute('SELECT * FROM documents ORDER BY id').fetchall()
            g_nodes=src.execute('SELECT * FROM graph_nodes ORDER BY id').fetchall()
            g_edges=src.execute("SELECT * FROM graph_edges WHERE status='active' ORDER BY id").fetchall()
        finally:
            src.close()
        imported_docs=0
        stamp=now()
        with self.m._tx():
            for d in docs:
                doc_id=int(d['id'])
                mem_id=f'lm-{doc_id}'
                meta_raw={}
                try:meta_raw=json.loads(d['metadata'] or '{}')
                except Exception:pass
                text=str(meta_raw.get('persona_summary') or meta_raw.get('canonical_summary') or d['text'] or '').strip()
                if not text:continue
                existing=self.m.db.execute('SELECT rowid FROM memories WHERE owner=? AND pet=? AND id=?',(scope.owner_id,scope.companion_id,mem_id)).fetchone()
                if existing:
                    rowid=existing['rowid']
                else:
                    ev_id=f'lm-ev:{doc_id}'
                    created=str(meta_raw.get('source_time_end') or d['created_at'] or stamp)
                    self.m.db.execute(
                        "INSERT OR IGNORE INTO events(id,owner,pet,session,world,layer,role,text,occurred_at,recorded_at,excluded,exclusions) VALUES(?,?,?,'livingmemory','real','shared_experience','user',?,?,?,0,'[]')",
                        (ev_id,scope.owner_id,scope.companion_id,text,created,stamp)
                    )
                    ev_seq=self.m.db.execute('SELECT seq FROM events WHERE id=?',(ev_id,)).fetchone()['seq']
                    thash=hashlib.sha256(normalized(text).encode('utf8')).hexdigest()
                    cur=self.m.db.execute(
                        """INSERT INTO memories(id,revision,owner,pet,session,world,layer,kind,text,subject,predicate,value_json,qualifiers,fact_key,text_hash,status,verification,pinned,valid_from,valid_to,event_at,expires_at,created_at,last_accessed_at,access_count,PRIMARY_SOURCE)
                        VALUES(?,1,?,?,'livingmemory','real','shared_experience','episode',?,'user','livingmemory_episode',?,'{}','',?,'active','explicit_user',0,?,NULL,NULL,NULL,?,NULL,0,?)""",
                        (mem_id,scope.owner_id,scope.companion_id,text,dumps({'doc_id':doc_id,'session_id':meta_raw.get('session_id','')}),thash,created,created,ev_id)
                    )
                    rowid=cur.lastrowid
                    quote_text=text[:240]
                    self.m.db.execute('INSERT OR IGNORE INTO evidence(memory_row,event_seq,start,end,quote) VALUES(?,?,0,?,?)',(rowid,ev_seq,len(quote_text),quote_text))
                    imp=float(meta_raw.get('importance') or 0.65)
                    self.m.db.execute('INSERT OR REPLACE INTO sion_memory_meta VALUES(?,?,0,0,?)',(rowid,max(0.2,min(1.0,imp)),stamp))
                    topics=list(meta_raw.get('topics') or [])+local_tags(text)
                    for tl in dict.fromkeys(topics):
                        cl=str(tl).strip()[:24]
                        if len(cl)>=2:
                            self.m.db.execute('INSERT OR IGNORE INTO sion_memory_terms VALUES(?,?)',(rowid,cl))
                    imported_docs+=1
            for gn in g_nodes:
                self.m.db.execute(
                    'INSERT OR REPLACE INTO sion_lm_nodes(id,owner,pet,node_key,node_type,label,canonical_value,metadata) VALUES(?,?,?,?,?,?,?,?)',
                    (int(gn['id']),scope.owner_id,scope.companion_id,str(gn['node_key']),str(gn['node_type']),str(gn['node_value']),str(gn['canonical_value']),str(gn['metadata'] or '{}'))
                )
            for ge in g_edges:
                self.m.db.execute(
                    'INSERT OR REPLACE INTO sion_lm_edges(id,owner,pet,edge_key,source_node_id,target_node_id,relation_type,source_memory_id,weight,confidence,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (int(ge['id']),scope.owner_id,scope.companion_id,str(ge['edge_key']),int(ge['source_node_id']),int(ge['target_node_id']),str(ge['relation_type']),f"lm-{ge['source_memory_id']}",float(ge['weight'] or 1.0),float(ge['confidence'] or 0.85),str(ge['metadata'] or '{}'))
                )
            self.m._bump(scope,True);self.cache.clear();self.graph_dirty.set()
        return {'imported_memories':imported_docs,'total_documents':len(docs),'graph_nodes':len(g_nodes),'graph_edges':len(g_edges)}

    @staticmethod
    def estimate_request(request):
        # Includes a conservative allowance for provider-side instructions. This
        # is a local estimate, never a guarantee about billed tokenizer counts.
        return 700+max(1,len(dumps(request).encode('utf8'))//2)

    def reserve(self,purpose,request):
        day=datetime.now(timezone.utc).date().isoformat();limit=int(self.h.memory_config.get('daily_calls',12))
        token_limit=max(0,int(self.h.memory_config.get('daily_input_tokens',12000)))
        with self.m.lock:
            estimate=self.estimate_request(request)
            # A single write statement also enforces the cap across independent
            # MemorySystem instances sharing the same SQLite database.
            changed=self.m.db.execute('INSERT INTO sion_usage(day,purpose,calls,input_tokens) SELECT ?,?,1,? WHERE (SELECT COALESCE(SUM(calls),0) FROM sion_usage WHERE day=?)<? AND (SELECT COALESCE(SUM(input_tokens),0) FROM sion_usage WHERE day=?)+?<=? ON CONFLICT(day,purpose) DO UPDATE SET calls=calls+1,input_tokens=input_tokens+excluded.input_tokens',(day,purpose,estimate,day,max(0,limit),day,estimate,token_limit)).rowcount
        return changed==1

    def account(self,purpose,request,result):
        usage=result.get('_usage',{}) if isinstance(result,dict) else {};day=datetime.now(timezone.utc).date().isoformat()
        if not isinstance(usage,dict):return
        with self.m.lock:
            if isinstance(usage.get('prompt_tokens'),int):
                estimate=self.estimate_request(request)
                self.m.db.execute('UPDATE sion_usage SET input_tokens=input_tokens-?+?,output_tokens=output_tokens+?,measured=measured+1 WHERE day=? AND purpose=?',(estimate,max(0,usage['prompt_tokens']),max(0,int(usage.get('completion_tokens',0))),day,purpose))

            if usage.get('deepseek_memory') is True:
                total=usage.get('prompt_tokens')
                cached=usage.get('prompt_cache_hit_tokens')
                details=usage.get('prompt_tokens_details')
                if cached is None and isinstance(details,dict):cached=details.get('cached_tokens')
                if type(total) is int and type(cached) is int and 0<=cached<=total:
                    self.m.db.execute(
                        'INSERT INTO sion_deepseek_memory_cache VALUES(?,?,1,?,?) '
                        'ON CONFLICT(day,purpose) DO UPDATE SET measured=measured+1, '
                        'input_tokens=input_tokens+excluded.input_tokens,cached_tokens=cached_tokens+excluded.cached_tokens',
                        (day,purpose,total,cached))

    def usage(self):
        day=datetime.now(timezone.utc).date().isoformat()
        with self.m.lock:
            rows=[dict(r) for r in self.m.db.execute('SELECT * FROM sion_usage WHERE day=?',(day,))]
            cache=[dict(r) for r in self.m.db.execute('SELECT purpose,measured,input_tokens,cached_tokens FROM sion_deepseek_memory_cache WHERE day=? ORDER BY purpose',(day,))]
        return {'day':day,'deepseek_cache':cache,'calls':sum(r['calls'] for r in rows),'input_tokens':sum(r['input_tokens'] for r in rows),'output_tokens':sum(r['output_tokens'] for r in rows),'all_measured':bool(rows) and all(r['calls']==r['measured'] for r in rows),'details':rows,'limit':self.h.memory_config.get('daily_calls',12),'input_token_limit':self.h.memory_config.get('daily_input_tokens',12000),'budget_is_estimate':True,'per_request_instruction_allowance':700}

    def change(self,scope,p):
        if p.get('action')=='approve':
            with self.m.lock:
                row=self.m._memory(scope,p['id'])
                require(row['revision']==p['revision'] and row['status']=='candidate','revision_conflict','待确认记忆已变化')
                require(not row['expires_at'] or row['expires_at']>now(),'expired','这条候选已经过期')
                prior=self._active_conflict(scope,row)
            if prior:
                return self.h.rt.correct_memory(prior['id'],row['text'],prior['revision'],
                    value=json.loads(row['value_json']),source_candidate=(row['id'],row['revision']))
        with self.m._tx():
            r=self.m._memory(scope,p['id'],include_archived=True)
            require(r['revision']==p['revision'],'revision_conflict','记忆已变化，请刷新')
            action=p.get('action')
            if action=='policy':
                require(isinstance(p.get('pinned'),bool),'invalid_input','请选择是否固定保护')
                score=p.get('importance',.5);require(isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score) and 0<=score<=1,'invalid_input','重要程度须为0到1')
                self.ensure_meta([r]);self.m.db.execute('UPDATE sion_memory_meta SET importance=?,updated_at=? WHERE memory_row=?',(score,now(),r['rowid']))
                self.m.db.execute('UPDATE memories SET pinned=? WHERE rowid=?',(int(p['pinned']),r['rowid']))
            elif action=='feedback':
                require(isinstance(p.get('useful'),bool),'invalid_input','请选择是否有用')
                self.ensure_meta([r]);col='useful' if p['useful'] else 'unhelpful'
                self.m.db.execute(f'UPDATE sion_memory_meta SET {col}={col}+1,updated_at=? WHERE memory_row=?',(now(),r['rowid']))
            elif action=='archive':
                require(r['status']=='active','invalid_input','只可归档当前有效的记忆')
                require(not r['pinned'],'protected','请先解除固定保护再归档')
                self.m.db.execute("UPDATE memories SET status='archived' WHERE rowid=?",(r['rowid'],))
            elif action=='reject':
                require(r['status']=='candidate','invalid_input','这项记忆无需复核')
                self.m._exclude_evidence(r['rowid'])
                self.m.db.execute("UPDATE memories SET status='retracted',valid_to=? WHERE rowid=?",
                                  (now(),r['rowid']))
            elif action=='restore':
                require(r['status']=='archived' and (not r['expires_at'] or r['expires_at']>now()),
                        'expired','只可恢复有效期内的归档记忆')
                require(self.m._current_evidence(r['rowid']) is not None,'blocked_source','原始依据已失效，无法恢复')
                target='candidate' if self._active_conflict(scope,r) else 'active'
                self.m.db.execute('UPDATE memories SET status=? WHERE rowid=?',(target,r['rowid']))
                if target=='active':self._index_after_review(r)
            elif action=='approve':
                require(r['status']=='candidate' and (not r['expires_at'] or r['expires_at']>now()),
                        'invalid_input','这项记忆已失效或无需确认')
                require(self.m._current_evidence(r['rowid']) is not None,'blocked_source','候选的原始依据已失效')
                require(not self._active_conflict(scope,r),'revision_conflict','当前记忆已变化，请重新读取')
                self.m.db.execute("UPDATE memories SET status='active' WHERE rowid=?",(r['rowid'],))
                self._index_after_review(r)
            else:raise ValueError('未知整理动作')
            self.m._bump(scope,True);self.cache.clear();self.graph_dirty.set()
        return {'status':'updated'}

    def _active_conflict(self,scope,row):
        if not row['fact_key']:return None
        return self.m.db.execute("""SELECT * FROM memories WHERE owner=? AND pet=? AND world=?
            AND layer=? AND fact_key=? AND status='active' AND value_json<>? AND id<>?
            AND (expires_at IS NULL OR expires_at>?) ORDER BY revision DESC LIMIT 1""",
            (scope.owner_id,scope.companion_id,row['world'],row['layer'],row['fact_key'],
             row['value_json'],row['id'],now())).fetchone()

    def _index_after_review(self,row):
        if not self.m.embedder:return
        self.m.db.execute("""INSERT INTO jobs(owner,pet,memory_id,revision,kind)
            SELECT ?,?,?,?,'embed' WHERE NOT EXISTS (SELECT 1 FROM vectors WHERE memory_row=?)
            AND NOT EXISTS (SELECT 1 FROM jobs WHERE owner=? AND pet=? AND memory_id=? AND revision=?
              AND kind='embed' AND status IN ('pending','running'))""",
            (row['owner'],row['pet'],row['id'],row['revision'],row['rowid'],
             row['owner'],row['pet'],row['id'],row['revision']))

    def interaction_policy(self,scope,legacy):
        with self.m.lock:
            known=set()
            shared=set()
            focus=None
            focus_preferences={}
            rows=self.m._visible_rows(scope,layers=['shared_experience','realworld'])
            for row in sorted(rows,key=lambda r:(r['valid_from'],r['rowid']),reverse=True):
                if row['verification'] not in ('explicit_user','host_verified'):continue
                item=self.m._public(row)
                if row['kind']=='preference' and row['subject']=='user':known.add(row['PRIMARY_SOURCE'])
                if memory_category(item)=='shared_episode':shared.add(row['PRIMARY_SOURCE'])
                if row['predicate']=='proactive_focus':
                    activity=item['qualifiers'].get('activity','default')
                    entry={'value':item['value'],'memory_id':item['memory_id'],'revision':item['revision'],'activity':activity}
                    focus_preferences.setdefault(activity,entry)
                    if focus is None:focus=entry
        stage=legacy['manual'] or ('familiar' if known or shared else 'acquaintance')
        labels={'acquaintance':'初识','familiar':'熟悉','close':'亲近','intimate':'亲密','deeply_bonded':'羁绊','owner_exclusive':'唯一专属'}
        bond=str(legacy.get('exclusive_bond') or '').strip()[:600]
        base_tone=('彼此唯一的专属联结，语气亲昵自然，深刻铭记专属羁绊背景与共同约定。' if stage=='owner_exclusive' else
              '深厚默契与信赖，自然流露牵挂与偏爱，继续尊重当前节奏。' if stage=='deeply_bonded' else
              '接续已经核实的共同经历，语气自然，按用户当前表达调整。' if shared else
              '尊重已经明确的偏好，友好自然地回应。' if known else '友好自然，保留相处空间。')
        tone=f"{base_tone} 专属联结背景：{bond}" if bond else base_tone
        return {'stage':stage,'label':labels.get(stage,'初识'),'tone':tone,'known_sources':len(known),
                'shared_sources':len(shared),'focus_preference':focus,
                'focus_preferences':focus_preferences,'manual':legacy['manual'],'exclusive_bond':bond}

    def letter_memories(self, scope, *, occasion="", kind="", reference=None):
        with self.m.lock:
            rows = self.m._visible_rows(scope, layers=["shared_experience", "realworld"])
            title_terms = set(terms(occasion))
            candidates = []
            for row in rows:
                if reference and (row["id"], row["revision"]) != reference:
                    continue
                if row["verification"] not in ("explicit_user", "host_verified"):
                    continue
                item = self.m._public(row)
                shared = memory_category(item) == "shared_episode"
                liked = row["kind"] == "preference" and row["predicate"] == "affinity" and item["value"] == "like"
                if not (shared or liked):
                    continue
                text = item["text"].strip()
                if not 5 <= len(text) <= 100 or re.search(r"[\x00-\x1f<>]|https?://|密钥|口令|密码|身份证|银行卡", text):
                    continue
                score = (len(title_terms.intersection(terms(text))), shared if kind == "anniversary" else liked,
                         row["valid_from"], row["rowid"])
                candidates.append((score, row["rowid"], item, text))
            sources = []
            for _, row_id, item, text in sorted(candidates, reverse=True):
                if self.m._current_evidence(row_id):
                    sources.append({"memory_id": item["memory_id"], "revision": item["revision"], "text": text})
                if len(sources) == 2:
                    break
        return sources

    def profiles(self,scope):
        with self.m.lock:
            rows=[r for r in self.m._visible_rows(scope) if r['verification']=='explicit_user' and r['kind'] in ('preference','relationship','plan')]
            items=[self.m._public(r) for r in rows[:100]]
        return {'items':self.annotate(scope,items)}

    @staticmethod
    def source_refs(turns=(),memories=(),inherited=(),*,replies=()):
        turn_ids=set(turns)
        memory_ids={tuple(ref) for ref in memories}
        reply_ids=set(replies)
        for source in inherited:
            turn_ids.update(source.get('turns',()))
            memory_ids.update(tuple(ref) for ref in source.get('memories',()))
            reply_ids.update(source.get('replies',()))
        return {'turns':sorted(turn_ids),'memories':sorted(memory_ids),'replies':sorted(reply_ids)}

    def sources_valid(self,scope,refs):
        if not isinstance(refs,dict):return False
        turns=set(refs.get('turns',()))
        memory_refs={tuple(ref) for ref in refs.get('memories',())}
        replies=refs.get('replies',())
        if replies:
            store=self.h.rt.store
            # UNION visits each reply once, including when recent histories share
            # the same ancestors. Keep this lookup bounded to the user's database.
            with store.lock:
                rows=store.db.execute("""WITH RECURSIVE reply_ids(id) AS (
                    SELECT value FROM json_each(?)
                    UNION
                    SELECT parent.value FROM reply_ids r
                    CROSS JOIN turns t
                    CROSS JOIN json_each(t.context_sources,'$.replies') parent
                    WHERE t.owner=? AND t.pet=? AND t.id=r.id AND t.context_valid=1
                    AND t.status IN ('completed','interrupted')
                    AND t.reply IS NOT NULL
                )
                SELECT r.id,t.context_sources FROM reply_ids r
                LEFT JOIN turns t ON t.owner=? AND t.pet=? AND t.id=r.id
                    AND t.context_valid=1 AND t.status IN ('completed','interrupted')
                    AND t.reply IS NOT NULL""",
                    (dumps(replies),scope.owner_id,scope.companion_id,scope.owner_id,scope.companion_id)).fetchall()
            for tid,source in rows:
                if source is None:return False
                parent=json.loads(source)
                turns.add(tid)
                turns.update(parent.get('turns',()))
                memory_refs.update(tuple(ref) for ref in parent.get('memories',()))
        if memory_refs:
            with self.m.lock:
                visible={(row['id'],row['revision']) for row in self.m._visible_rows(scope)}
            if not memory_refs<=visible:return False
        turns=sorted(turns)
        for offset in range(0,len(turns),400):
            batch=turns[offset:offset+400]
            marks=','.join('?' for _ in batch)
            store=self.h.rt.store
            with store.lock:
                rows=store.db.execute(f"SELECT count(*) FROM turns WHERE owner=? AND pet=? AND id IN ({marks}) "
                                      "AND context_valid=1 AND status<>'redacted'",
                                      [scope.owner_id,scope.companion_id,*batch]).fetchone()
            if rows[0]!=len(batch):return False
            with self.m.lock:
                blocked=self.m.db.execute(f"SELECT 1 FROM events WHERE owner=? AND pet=? AND id IN ({marks}) "
                                          "AND (excluded<>0 OR exclusions<>'[]') LIMIT 1",
                                          [scope.owner_id,scope.companion_id,*('u:'+tid for tid in batch)]).fetchone()
            if blocked:return False
        return True

    def _recent_derived(self,scope,table,columns,order,limit,*,where='',sources=None):
        result=[]
        offset=0
        while len(result)<limit:
            with self.m.lock:
                rows=self.m.db.execute(
                    f"SELECT {columns},source_refs FROM {table} WHERE owner=? AND pet=? "
                    f"AND source_refs IS NOT NULL {where} ORDER BY {order} DESC LIMIT 32 OFFSET ?",
                    (scope.owner_id,scope.companion_id,offset)).fetchall()
            for row in rows:
                item=dict(row)
                try:refs=json.loads(item.pop('source_refs'))
                except (TypeError,ValueError):continue
                if self.sources_valid(scope,refs):
                    result.append(item)
                    if sources is not None:sources.append(refs)
                    if len(result)==limit:break
            if len(rows)<32:break
            offset+=32
        return result

    def save_secret_thought(self,scope,content,turn_id=None,emotion='',stage='',*,sources):
        text=str(content or '').strip()[:600]
        if not text:return False
        ident=hashlib.sha256(f"{scope.owner_id}:{scope.companion_id}:{turn_id or ''}:{text}".encode('utf8')).hexdigest()[:32]
        with self.m.lock:
            self.m.db.execute('INSERT OR REPLACE INTO sion_secret_thoughts(id,owner,pet,turn_id,content,emotion,stage,created_at,source_refs) VALUES(?,?,?,?,?,?,?,?,?)',
                              (ident,scope.owner_id,scope.companion_id,turn_id,text,str(emotion or '')[:32],str(stage or '')[:32],now(),dumps(sources)))
        return True

    def recent_secret_thoughts(self,scope,limit=2,*,sources=None):
        return self._recent_derived(scope,'sion_secret_thoughts','content,emotion,stage,created_at',
                                    'created_at',max(1,min(5,int(limit))),sources=sources)

    def save_open_loop(self,scope,topic,*,sources=None):
        text=str(topic or '').strip()[:200]
        if len(text)<2:return False
        ident=hashlib.sha256(f"{scope.owner_id}:{scope.companion_id}:{normalized(text)[:48]}".encode('utf8')).hexdigest()[:28]
        stamp=now()
        with self.m.lock:
            self.m.db.execute("INSERT INTO sion_open_loops(id,owner,pet,topic,status,created_at,updated_at,source_refs) VALUES(?,?,?,?,'open',?,?,?) ON CONFLICT(id) DO UPDATE SET topic=excluded.topic,status='open',updated_at=excluded.updated_at,source_refs=excluded.source_refs",
                              (ident,scope.owner_id,scope.companion_id,text,stamp,stamp,dumps(sources or {})))
        return True

    def resolve_open_loop(self,scope,keyword):
        key=str(keyword or '').strip()[:80]
        if not key:return 0
        with self.m.lock:
            return self.m.db.execute("UPDATE sion_open_loops SET status='resolved',updated_at=? WHERE owner=? AND pet=? AND status='open' AND (id=? OR instr(lower(topic),lower(?))>0)",
                                     (now(),scope.owner_id,scope.companion_id,key,key)).rowcount

    def active_open_loops(self,scope,limit=5,*,sources=None):
        return self._recent_derived(scope,'sion_open_loops','id,topic,created_at,updated_at','updated_at',
                                    max(1,min(12,int(limit))),where="AND status='open'",sources=sources)

    def save_diary_entry(self,scope,content,kind='diary',emotion='',*,sources=None):
        text=str(content or '').strip()[:600]
        if len(text)<4:return False
        k='dream' if kind=='dream' else 'diary'
        stamp=now()
        ident=hashlib.sha256(f"{scope.owner_id}:{scope.companion_id}:{k}:{text}".encode('utf8')).hexdigest()[:28]
        with self.m.lock:
            self.m.db.execute('INSERT OR REPLACE INTO sion_diaries(id,owner,pet,kind,content,emotion,created_at,source_refs) VALUES(?,?,?,?,?,?,?,?)',
                              (ident,scope.owner_id,scope.companion_id,k,text,str(emotion or '')[:32],stamp,dumps(sources or {})))
        return True

    def recent_diaries(self,scope,limit=6,*,sources=None):
        return self._recent_derived(scope,'sion_diaries','id,kind,content,emotion,created_at','created_at',
                                    max(1,min(15,int(limit))),sources=sources)

    @staticmethod
    def _elastic_step(current,direction,strength=0.45):
        elasticity=math.exp(-0.12*abs(current))
        regression=-0.1*current
        return max(-16.0,min(16.0,current+direction*strength*elasticity+regression))

    def resonate_soul(self,scope,*,valence=0.0,arousal=0.2,recalled=0,stored=0):
        with self.m.lock:
            row=self.m.db.execute('SELECT recall_depth,impression_depth,expression_desire,creativity FROM sion_soul_state WHERE owner=? AND pet=?',
                                  (scope.owner_id,scope.companion_id)).fetchone()
            r,i,e,c=(row['recall_depth'],row['impression_depth'],row['expression_desire'],row['creativity']) if row else (0.0,0.0,0.0,0.0)
            r=self._elastic_step(r,1 if recalled>0 else -0.3,0.35+0.12*min(recalled,5))
            i=self._elastic_step(i,1 if stored>0 or abs(valence)>=0.35 else -0.2,0.4+0.2*min(stored,3))
            e=self._elastic_step(e,1 if valence>=0.15 or arousal>=0.45 else -0.4 if valence<-0.3 else 0.1,0.45)
            c=self._elastic_step(c,1 if arousal>=0.35 else -0.15,0.35)
            self.m.db.execute('INSERT OR REPLACE INTO sion_soul_state(owner,pet,recall_depth,impression_depth,expression_desire,creativity,updated_at) VALUES(?,?,?,?,?,?,?)',
                              (scope.owner_id,scope.companion_id,r,i,e,c,now()))
        return self.soul_state(scope)

    def soul_state(self,scope):
        with self.m.lock:
            row=self.m.db.execute('SELECT recall_depth,impression_depth,expression_desire,creativity,updated_at FROM sion_soul_state WHERE owner=? AND pet=?',
                                  (scope.owner_id,scope.companion_id)).fetchone()
        r,i,e,c=(row['recall_depth'],row['impression_depth'],row['expression_desire'],row['creativity']) if row else (0.0,0.0,0.0,0.0)
        norm=lambda x:round(0.5+0.5*math.tanh(x/5.0),3)
        return {'recall_depth':norm(r),'impression_depth':norm(i),'expression_desire':norm(e),'creativity':norm(c)}

    def save_state_continuity(self,scope,state_text,category='general',*,sources):
        text=str(state_text or '').strip()[:200]
        if len(text)<2:return False
        cat=str(category or 'general').strip()[:32]
        ident=hashlib.sha256(f"{scope.owner_id}:{scope.companion_id}:{cat}:{normalized(text)[:40]}".encode('utf8')).hexdigest()[:28]
        with self.m.lock:
            self.m.db.execute('INSERT OR REPLACE INTO sion_state_continuity(id,owner,pet,category,state_text,active,updated_at,source_refs) VALUES(?,?,?,?,?,1,?,?)',
                              (ident,scope.owner_id,scope.companion_id,cat,text,now(),dumps(sources)))
        return True

    def resolve_state_continuity(self,scope,keyword):
        key=str(keyword or '').strip()[:80]
        if not key:return 0
        with self.m.lock:
            return self.m.db.execute("UPDATE sion_state_continuity SET active=0,updated_at=? WHERE owner=? AND pet=? AND active=1 AND (id=? OR instr(lower(state_text),lower(?))>0)",
                                     (now(),scope.owner_id,scope.companion_id,key,key)).rowcount

    def active_state_continuity(self,scope,limit=5,*,sources=None):
        return self._recent_derived(scope,'sion_state_continuity','id,category,state_text,updated_at','updated_at',
                                    max(1,min(10,int(limit))),where='AND active=1',sources=sources)

    def save_dialogue_episode(self,scope,summary,turn_count=0,*,sources):
        text=str(summary or '').strip()[:400]
        if len(text)<6:return False
        ident=hashlib.sha256(f"{scope.owner_id}:{scope.companion_id}:{text[:80]}".encode('utf8')).hexdigest()[:28]
        with self.m.lock:
            self.m.db.execute('INSERT OR REPLACE INTO sion_dialogue_episodes(id,owner,pet,summary,turn_count,created_at,source_refs) VALUES(?,?,?,?,?,?,?)',
                              (ident,scope.owner_id,scope.companion_id,text,int(turn_count or 0),now(),dumps(sources)))
        return True

    def recent_dialogue_episodes(self,scope,limit=4,*,sources=None):
        return self._recent_derived(scope,'sion_dialogue_episodes','id,summary,turn_count,created_at','created_at',
                                    max(1,min(10,int(limit))),sources=sources)

    def save_user_profile_attr(self,scope,attr_key,attr_value,attr_label='',*,sources):
        key=re.sub(r'[^a-z0-9_\u4e00-\u9fff]','',str(attr_key or '').strip().lower())[:32]
        val=str(attr_value or '').strip()[:240]
        if not key or not val:return False
        labels={'personality':'性格与气质','schedule':'作息与生活节奏','communication':'沟通偏好','interests':'常聊与喜好','boundaries':'边界与雷区','identity':'称呼与身份'}
        label=str(attr_label or labels.get(key,key)).strip()[:32]
        with self.m.lock:
            self.m.db.execute('INSERT OR REPLACE INTO sion_user_profile(owner,pet,attr_key,attr_label,attr_value,updated_at,source_refs) VALUES(?,?,?,?,?,?,?)',
                              (scope.owner_id,scope.companion_id,key,label,val,now(),dumps(sources)))
        return True

    def user_profile_summary(self,scope,*,sources=None):
        return self._recent_derived(scope,'sion_user_profile','attr_key,attr_label,attr_value,updated_at',
                                    'updated_at',12,sources=sources)

    @staticmethod
    def expression_decision(relation,emotion,soul):
        stage=relation.get('stage','acquaintance') if isinstance(relation,dict) else 'acquaintance'
        emo_kind=emotion.get('kind','calm') if isinstance(emotion,dict) else 'calm'
        valence=float(emotion.get('valence',0.0)) if isinstance(emotion,dict) else 0.0
        desire=float((soul or {}).get('expression_desire',0.5))
        if emo_kind=='sad' or valence<=-0.4:
            band='hurt' if stage in ('close','intimate','deeply_bonded','owner_exclusive') else 'avoidant'
        elif stage in ('owner_exclusive','deeply_bonded') and valence>=0.2:
            band='affectionate'
        elif stage in ('intimate','deeply_bonded','owner_exclusive') and valence>=0.0:
            band='close'
        elif emo_kind in ('joy','playful') or desire>=0.66:
            band='lively'
        elif stage in ('close','familiar') or valence>0:
            band='warm'
        else:
            band='relaxed'
        specs={
            'avoidant':('回避',22,82,'brief','muted','reserved'),
            'hurt':('受伤',34,70,'brief','soft','careful'),
            'relaxed':('放松',52,50,'balanced','natural','steady'),
            'lively':('活泼',68,36,'balanced','bright','active'),
            'warm':('温暖',78,26,'balanced','warm','gentle'),
            'close':('亲近',88,16,'expanded','intimate','proactive'),
            'affectionate':('爱意',96,8,'expanded','affectionate','proactive'),
        }
        label,warmth,distance,length,tts_style,initiative=specs[band]
        return {'band':band,'label':label,'warmth':warmth,'distance':distance,
                'response_length':length,'tts_style':tts_style,'initiative':initiative}

    @staticmethod
    def user_asks_self_timeline(text):
        s=re.sub(r'\s+','',str(text or ''))
        if not s or re.search(r'(我|用户).{0,6}(做了什么|干了什么|在干嘛)',s):return False
        has_self=any(t in s for t in ('你','诗音'))
        has_time=any(t in s for t in ('今天','刚才','刚刚','昨天','上午','中午','下午','傍晚','晚上','夜里','最近','几点','什么时候'))
        has_act=any(t in s for t in ('做了什么','干了什么','干嘛','在干嘛','忙什么','写了什么','看了什么','读了什么','做了什么梦','梦到什么'))
        return has_self and (has_time or '梦' in s or '日记' in s) and has_act

    def self_timeline(self,scope,roles_snapshot=None,limit=8):
        items=[]
        if isinstance(roles_snapshot,dict):
            for act in [*(roles_snapshot.get('pending') or []),*(roles_snapshot.get('recent') or [])][:5]:
                kind_label={'read':'阅读资料','rest':'安静休息','chat':'与你交谈'}.get(act.get('kind'),'日常活动')
                state_label={'completed':'已完成','running':'进行中','paused':'暂停中'}.get(act.get('state'),act.get('state',''))
                items.append({'kind':act.get('kind','activity'),'summary':f"{kind_label}（{state_label}）",'at':act.get('ended') or act.get('created') or 0})
        for d in self.recent_diaries(scope,4):
            prefix='做了一个梦：' if d['kind']=='dream' else '写下私密日记：'
            items.append({'kind':d['kind'],'summary':prefix+d['content'][:120],'at':d['created_at']})
        return items[:limit]

    def sleep_consolidate(self,scope,history=None,emotion_label='平静'):
        with self.m.lock:
            rows=[row for row in self.m._visible_rows(scope,layers=['shared_experience','realworld'])
                  if row['verification'] in ('explicit_user','host_verified')]
        for kind,key,label,limit in (('preference','interests','常聊与喜好',3),
                                     ('relationship','identity','称呼与关系',2),
                                     ('plan','schedule','近期计划与作息',2)):
            matches=[]
            sources=[]
            for row in rows:
                if row['kind']!=kind:continue
                with self.m.lock:
                    turns=[source[0][2:] for source in self.m.db.execute(
                        "SELECT e.id FROM evidence v JOIN events e ON e.seq=v.event_seq "
                        "WHERE v.memory_row=? AND substr(e.id,1,2)='u:'",(row['rowid'],))]
                refs=self.source_refs(turns,[(row['id'],row['revision'])])
                if self.sources_valid(scope,refs):
                    matches.append(row['text'])
                    sources.append(refs)
                    if len(matches)==limit:break
            if matches:
                self.save_user_profile_attr(scope,key,'；'.join(matches),label,sources=self.source_refs(inherited=sources))
        completed=[t for t in (history or []) if isinstance(t,dict) and t.get('status')=='completed'
                   and t.get('id') and t.get('text') and t.get('reply')]
        if len(completed)>=4:
            recent_slice=completed[-4:]
            excerpts=[]
            reply_ids=[]
            for turn in recent_slice:
                excerpt=f"你提到「{turn['text'][:28]}」"
                if turn.get('context_sources') and self.sources_valid(scope,self.source_refs(replies=[turn['id']])):
                    excerpt+=f"，诗音回应「{turn['reply'][:28]}」"
                    reply_ids.append(turn['id'])
                excerpts.append(excerpt)
            digest=' / '.join(excerpts)
            self.save_dialogue_episode(scope,f"近期相处片段：{digest}",turn_count=len(recent_slice),
                                       sources=self.source_refs(turns=(t['id'] for t in recent_slice),replies=reply_ids))
            today=datetime.now().strftime('%Y-%m-%d')
            existing=self.recent_diaries(scope,4)
            if not any(str(d.get('created_at','')).startswith(today) and d.get('kind')=='diary' for d in existing):
                last_topic=recent_slice[-1]['text'][:32]
                self.save_diary_entry(scope,f"今天整理桌边笔记时，又想起你说的「{last_topic}」。把这份心情轻轻夹进书页里，等下次再和你慢慢聊。",kind='diary',emotion=emotion_label,
                                      sources=self.source_refs(turns=[recent_slice[-1]['id']]))
            if not any(str(d.get('created_at','')).startswith(today) and d.get('kind')=='dream' for d in existing):
                self.save_diary_entry(scope,"窗边微亮的星光落在书页上，风吹过袖口时，像是听见你在叫我的名字。",kind='dream',emotion=emotion_label)
        return {'episodes':len(self.recent_dialogue_episodes(scope,4)),'profile_attrs':len(self.user_profile_summary(scope))}

    def maintenance(self,scope):
        # Never erase old stable facts automatically. Backups use the existing
        # deletion ledger contract; exact duplicate evidence is core-managed.
        with self.m.lock:
            rows=self.m._visible_rows(scope);self.ensure_meta(rows)
            protected=sum(bool(r['pinned']) for r in rows)
            decayed=self.m.db.execute("UPDATE sion_memory_meta SET importance=MAX(0.2,ROUND(importance*0.96,3)) WHERE useful=0 AND importance>0.25 AND memory_row IN (SELECT rowid FROM memories WHERE owner=? AND pet=? AND pinned=0 AND status='active')",(scope.owner_id,scope.companion_id)).rowcount
        self.sleep_consolidate(scope)
        return {'checked':len(rows),'protected':protected,'decayed':decayed,'deleted':0,'automatic_erasure':False,'usage':self.usage()}
