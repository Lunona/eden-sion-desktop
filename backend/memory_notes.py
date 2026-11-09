"""Line-addressed source documents with bounded indexing windows."""
import re,uuid,hashlib,json,heapq
from pet_memory.types import MemoryError,now,require,terms

def chunks(text,title='',measure=None):
    output=[];pending=[];start=1
    prefix='['+title[:24]+'] '
    def fits(value):return (measure(prefix+value)<=124 if measure else len(prefix+value)<=120)
    def emit(values,line):
        if values:output.append({'text':'\n'.join(values),'line_start':line,'line_end':line+len(values)-1,'column_start':0})
    for number,line in enumerate(text.splitlines(),1):
        if not line.strip():
            emit(pending,start);pending=[];continue
        if not fits(line):
            emit(pending,start);pending=[];offset=0
            while offset<len(line):
                lo,hi=1,len(line)-offset
                while lo<hi:
                    mid=(lo+hi+1)//2
                    if fits(line[offset:offset+mid]):lo=mid
                    else:hi=mid-1
                part=line[offset:offset+lo]
                output.append({'text':part,'line_start':number,'line_end':number,'column_start':offset});offset+=lo
            continue
        if pending and not fits('\n'.join(pending+[line])):
            emit(pending,start);pending=[]
        if not pending:start=number
        pending.append(line)
    emit(pending,start)
    return output

def import_note(host,p):
    title=str(p.get('title','未命名资料')).strip()[:80] or '未命名资料';text=str(p.get('text',''));layer=p.get('layer','realworld')
    require(bool(text.strip()) and len(text)<=32000,'invalid_input','资料须为1至32000字')
    world={'shared_experience':'real','realworld':'real','canon':'canon:eden','story_branch':'branch:eden'}.get(layer)
    require(bool(world),'invalid_input','未知资料来源')
    host.rt.interrupt('notes_imported');scope=host.rt.scope();m=host.rt.memory
    parts=chunks(text,title,host.embedder.token_count if host.embedder else None)
    subject='companion' if layer=='canon' else 'user'
    with m._tx():
        old=m._memory(scope,p['replace_id']) if p.get('replace_id') else None
        if old:
            require(old['revision']==p.get('revision'),'revision_conflict','资料已变化，请刷新')
            require(old['world']==world and old['layer']==layer and m.db.execute('SELECT 1 FROM sion_documents WHERE memory_row=?',(old['rowid'],)).fetchone(),'invalid_input','只能在同一来源中更新资料原文')
        def store(body,qualifiers,parents=None,pinned=False):
            ev=m._event(scope,'note_'+uuid.uuid4().hex,body,'document',world,layer,None)
            return m._store(scope,body,ev,0,len(body),kind='note',subject=subject,qualifiers=qualifiers,parent_ids=parents,pinned=pinned)
        digest=hashlib.sha256((title+'\0'+text).encode('utf8')).hexdigest()
        root=store('资料：'+title+'\n'+text[:120],{'document_root':True,'document_digest':digest},pinned=bool(old and old['pinned']))
        if root.get('duplicate'):
            return {**root,'chunks':len(parts),'lines':len(text.splitlines())}
        row=m._memory(scope,root['memory_id']);m.db.execute('INSERT INTO sion_documents(memory_row,title,body) VALUES(?,?,?)',(row['rowid'],title,text))
        if old:
            meta=m.db.execute('SELECT importance,useful,unhelpful,updated_at FROM sion_memory_meta WHERE memory_row=?',(old['rowid'],)).fetchone()
            if meta:m.db.execute('INSERT OR REPLACE INTO sion_memory_meta VALUES(?,?,?,?,?)',(row['rowid'],*meta))
        for i,part in enumerate(parts):store('['+title[:24]+'] '+part['text'],{'document_id':root['memory_id'],'part':i+1,'line_start':part['line_start'],'line_end':part['line_end'],'column_start':part['column_start']},[root['memory_id']])
        if old:
            ids=m._descendants(scope,[old['id']])
            for mid in ids:m.db.execute("UPDATE memories SET status='archived' WHERE owner=? AND pet=? AND id=? AND status='active'",(scope.owner_id,scope.companion_id,mid))
            m._bump(scope,True)
    host.rt._emit('memory.added',None,{'memory_id':root['memory_id'],'knowledge_layer':layer,'document':True})
    return {**root,'chunks':len(parts),'lines':len(text.splitlines())}

def read_note(host,p,*,activity=False):
    m=host.rt.memory;s=host.rt.scope()
    with m.lock:
        row=m._memory(s,p['id']);doc=m.db.execute('SELECT * FROM sion_documents WHERE memory_row=?',(row['rowid'],)).fetchone()
        require(doc is not None,'legacy_note','旧资料只有摘要与片段，请重新导入原文以启用完整阅读')
        offset=max(0,int(p.get('offset',0)));body=doc['body'];part=body[offset:offset+6000]
        end=offset+len(part)
        result={'title':doc['title'],'text':part,'offset':offset,'next_offset':end,'has_more':end<len(body),'line_start':body[:offset].count('\n')+1,'total_chars':len(body),'total_lines':len(body.splitlines()),'revision':row['revision']}
        if activity:
            require(row['status']=='active','inactive_memory','只有当前有效的资料可以安排阅读')
            start=offset
            if offset and body[offset-1]!='\n':
                newline=body.find('\n',offset,end)
                start=end if newline<0 else newline+1
            end_of_line=end
            if start<end<len(body) and body[end-1]!='\n':
                newline=body.find('\n',end)
                end_of_line=len(body) if newline<0 else newline
            result['heading_text']=body[start:end_of_line] if start<end else ''
        return result

def document_source(memory,scope,item):
    qualifiers=item.get('qualifiers',{})
    root_id=item['memory_id'] if qualifiers.get('document_root') is True else qualifiers.get('document_id')
    if not isinstance(root_id,str):
        return None
    try:
        root=memory._memory(scope,root_id)
    except MemoryError:
        return None
    if root['status']!='active' or root['world']!=item['world_id'] or root['layer']!=item['knowledge_layer']:
        return None
    doc=memory.db.execute('SELECT title,body FROM sion_documents WHERE memory_row=?',(root['rowid'],)).fetchone()
    if doc is None:
        return None
    title,body=doc
    if qualifiers.get('document_root') is True:
        start,end,column=1,max(1,len(body[:120].splitlines())),0
        if item['text']!='资料：'+title+'\n'+body[:120]:
            return None
    else:
        start,end,column=(qualifiers.get(key) for key in ('line_start','line_end','column_start'))
        if any(type(value) is not int for value in (start,end,column)):
            return None
        lines=body.splitlines()
        if not 1<=start<=end<=len(lines) or column<0:
            return None
        prefix='['+title[:24]+'] '
        if not item['text'].startswith(prefix):
            return None
        quote=item['text'][len(prefix):]
        excerpt='\n'.join(lines[start-1:end])
        if start==end:
            excerpt=excerpt[column:column+len(quote)]
        if quote!=excerpt:
            return None
    return {'title':title,'version_id':root_id,'revision':root['revision'],'line_start':start,
            'line_end':end,'column_start':column}

def related_passages(memory,scope,anchor,source,query,seen):
    root_id=source['version_id']
    generic=set(terms('资料 文档 原文 交接 标题 这份 当前 有效'))
    query_terms=set(terms(query))-set(terms(source['title']))-generic
    anchor_part=anchor.get('qualifiers',{}).get('part',0)
    if type(anchor_part) is not int:
        anchor_part=0
    rows=memory.db.execute("""SELECT child.* FROM links AS link JOIN memories AS child
        ON child.owner=link.owner AND child.pet=link.pet AND child.id=link.child_id
        WHERE link.owner=? AND link.pet=? AND link.parent_id=? AND child.status='active'
        AND child.kind='note' AND child.world=? AND child.layer=?
        AND child.valid_from<=? AND child.valid_to IS NULL AND child.expires_at IS NULL
        AND NOT EXISTS (SELECT 1 FROM links AS other WHERE other.owner=child.owner AND other.pet=child.pet
            AND other.child_id=child.id AND other.parent_id<>?)""",
        (scope.owner_id,scope.companion_id,root_id,anchor['world_id'],anchor['knowledge_layer'],now(),root_id))
    def candidates():
        for row in rows:
            if row['id'] in seen:
                continue
            metadata=json.loads(row['qualifiers'])
            part=metadata.get('part')
            if metadata.get('document_id')!=root_id or type(part) is not int or 'chapter' in metadata:
                continue
            prefix='['+source['title'][:24]+'] '
            overlap=len(query_terms & set(terms(row['text'].removeprefix(prefix))))
            yield ((-overlap,abs(part-anchor_part),part),row)

    result=[]
    for _,row in heapq.nsmallest(2,candidates(),key=lambda value:value[0]):
        item=memory._public(row)
        location=document_source(memory,scope,item)
        if location:
            item.update(match_reasons=['document_related'],score=anchor['score'],document_source=location)
            result.append((item,memory._context_item(row,item)))
    return result
