"""Portable current memories plus source documents; import participates in core transaction."""
import hashlib, math
from pet_memory.types import require, now
from reading_notes import note_evidence

def export_data(host):
    m=host.rt.memory;s=host.rt.scope()
    with m.lock:
        data=m.export(s);extras=[]
        for item in data['memories']:
            if item['status']!='active':continue
            row=m._memory(s,item['memory_id']);meta=m.db.execute('SELECT * FROM sion_memory_meta WHERE memory_row=?',(row['rowid'],)).fetchone()
            doc=m.db.execute('SELECT title,body FROM sion_documents WHERE memory_row=?',(row['rowid'],)).fetchone()
            x={'memory_id':item['memory_id']}
            if meta:x.update(importance=meta['importance'],useful=meta['useful'],unhelpful=meta['unhelpful'])
            if doc:x['document']=dict(doc)
            extras.append(x)
        data['sion_extension']={'version':1,'items':extras}
        return data

def import_extension(host,s,data,planned,dry_run):
    extension=data.get('sion_extension')
    if extension is None:return
    require(isinstance(extension,dict) and extension.get('version')==1 and isinstance(extension.get('items'),list) and len(extension['items'])<=50000,'invalid_import','扩展记忆格式无效')
    all_items={x['memory_id']:x for x in data['memories']};allowed={x['memory_id'] for x in planned};seen=set();validated=[];total=0
    for x in extension['items']:
        require(isinstance(x,dict) and isinstance(x.get('memory_id'),str) and x['memory_id'] in all_items and x['memory_id'] not in seen,'invalid_import','扩展记忆缺少对应条目或重复')
        mid=x['memory_id'];seen.add(mid)
        score=x.get('importance',.5);good=x.get('useful',0);bad=x.get('unhelpful',0)
        require(isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score) and 0<=score<=1 and all(isinstance(v,int) and not isinstance(v,bool) and 0<=v<=1000000 for v in (good,bad)),'invalid_import','重要程度或反馈计数无效')
        doc=x.get('document');item=all_items[mid]
        if doc is not None:
            require(isinstance(doc,dict) and isinstance(doc.get('title'),str) and 0<len(doc['title'])<=80 and isinstance(doc.get('body'),str) and 0<len(doc['body'])<=32000 and item['qualifiers'].get('document_root') is True,'invalid_import','资料原文无效')
            digest=hashlib.sha256((doc['title']+'\0'+doc['body']).encode('utf8')).hexdigest()
            require(item['qualifiers'].get('document_digest')==digest,'invalid_import','资料原文与来源摘要不匹配')
            total+=len(doc['body']);require(total<=16*1024*1024,'invalid_import','资料原文总量过大')
        if mid in allowed:validated.append((mid,score,good,bad,doc))
    if dry_run:return
    m=host.rt.memory
    for mid,score,good,bad,doc in validated:
        row=m._memory(s,mid)
        m.db.execute('INSERT OR REPLACE INTO sion_memory_meta VALUES(?,?,?,?,?)',(row['rowid'],score,good,bad,now()))
        if doc:m.db.execute('INSERT OR REPLACE INTO sion_documents(memory_row,title,body) VALUES(?,?,?)',(row['rowid'],doc['title'],doc['body']))
    for item in planned:
        parent=item['qualifiers'].get('document_id')
        if not parent:continue
        root=all_items.get(parent)
        require(root is not None and root['qualifiers'].get('document_root') is True and root['world_id']==item['world_id'] and root['knowledge_layer']==item['knowledge_layer'],'invalid_import','资料片段缺少相同来源的原文')
        target=m._memory(s,parent)
        require(target['world']==item['world_id'] and target['layer']==item['knowledge_layer'],'invalid_import','资料原文范围不一致')
        m.db.execute('INSERT OR IGNORE INTO links(owner,pet,parent_id,child_id) VALUES(?,?,?,?)',(s.owner_id,s.companion_id,parent,item['memory_id']))
        if item['qualifiers'].get('reading_note'):
            note=m._public(m._memory(s,item['memory_id']))
            require(note_evidence(m,s,note) is not None,'invalid_import','读后笔记的原文依据无效')
