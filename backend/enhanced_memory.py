"""Sion memory 0.2: local semantic retrieval, source-grounded extraction and reranking.

The retrieval/lifecycle design was compared with local LivingMemory 2.7 and Angel
Memory 1.6.8. Implementation below is original; existing source/deletion contracts
remain authoritative. No AstrBot credentials, private memories or DBs are read.
"""
from pathlib import Path
from collections import OrderedDict,deque
import hashlib,json,time,threading,os,re
import numpy as np
from pet_memory.extraction import RuleExtractor
from pet_memory.types import dumps, vector
from pet_companion.models import CoreError
from memory_notes import document_source,related_passages
from reading_notes import note_evidence

INTERPRETATION_QUERY=re.compile(r'解读|读后感|读完.{0,32}(?:怎么看|怎么想|理解|感想)|怎么看.{0,24}(?:资料|文档|原文)')

class LocalEmbedder:
    model_id='sion:minilm-multilingual:e8f8c211:q8-avx2:mean128'
    def __init__(self,path):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
        self.lock=threading.RLock();self.query_cache=OrderedDict();self.vector_cache=OrderedDict();self.timings=deque(maxlen=120)
        self.tokenizer_path=Path(path)/'tokenizer.json'
        if not self.tokenizer_path.is_file():raise FileNotFoundError('本地语义分词器文件缺失')
        self.tokenizer_factory=Tokenizer.from_file
        self.tokenizer=None
        self.tokenizer_error=None
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        self.model_path=str(Path(path)/'model_quint8_avx2.onnx');self.options=options;self.ort=ort
        if not Path(self.model_path).is_file():raise FileNotFoundError('本地语义模型文件缺失')
        self.session=None;self.last_used=time.monotonic();self.loads=0
    def _load_tokenizer(self):
        if self.tokenizer is None:
            try:
                tokenizer=self.tokenizer_factory(str(self.tokenizer_path))
                tokenizer.enable_truncation(max_length=128)
                tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
            except Exception as exc:
                self.tokenizer_error=str(exc)[:300]
                raise
            self.tokenizer=tokenizer
            self.tokenizer_error=None
        return self.tokenizer
    def prepare(self):
        with self.lock:
            try:self._load_tokenizer()
            except Exception:return False
            return True
    def embed(self,text):
        key=hashlib.sha256(text.encode('utf8')).digest()
        with self.lock:
            self.last_used=time.monotonic()
            if key in self.query_cache:
                self.query_cache.move_to_end(key);return self.query_cache[key].tolist()
            tokenizer=self._load_tokenizer()
            if self.session is None:
                self.session=self.ort.InferenceSession(self.model_path,sess_options=self.options,providers=['CPUExecutionProvider']);self.inputs={x.name for x in self.session.get_inputs()};self.loads+=1
            start=time.perf_counter();enc=tokenizer.encode(text)
            batch={'input_ids':np.array([enc.ids],dtype=np.int64),'attention_mask':np.array([enc.attention_mask],dtype=np.int64),'token_type_ids':np.array([enc.type_ids],dtype=np.int64)}
            output=self.session.run(None,{k:v for k,v in batch.items() if k in self.inputs})[0]
            if output.ndim==3:
                mask=batch['attention_mask'][...,None].astype(np.float32);value=(output*mask).sum(axis=1)[0]/max(float(mask.sum()),1.)
            else:value=output[0]
            value=value.astype(np.float32);value/=max(float(np.linalg.norm(value)),1e-12)
            self.query_cache[key]=value
            if len(self.query_cache)>256:self.query_cache.popitem(last=False)
            self.timings.append((time.perf_counter()-start)*1000)
            return value.tolist()
    embed_query=embed
    def rank_stored(self,query,cursor,threshold,deadline):
        # Decode each persisted vector once. Subsequent queries use contiguous
        # float arrays, rather than repeated Python cosine loops and JSON parses.
        candidates=[];partial=False;ids=[];vectors=[]
        q=np.asarray(query,dtype=np.float32)
        def flush():
            if vectors:
                scores=np.einsum('ij,j->i',np.stack(vectors),q,optimize=False)
                candidates.extend((float(score),rid) for rid,score in zip(ids,scores) if score>=threshold)
                ids.clear();vectors.clear()
        with self.lock:
            for rid,stored in cursor:
                if time.monotonic()>deadline:partial=True;break
                if not stored:continue
                # rowids can be reused by a restored database; content identity
                # prevents a stale vector from ranking a different fact.
                key=(rid,hashlib.sha256(stored.encode()).digest())
                value=self.vector_cache.get(key)
                if value is None:
                    value=np.array(json.loads(stored),dtype=np.float32)
                    if value.shape!=q.shape or not np.isfinite(value).all():continue
                    value/=max(float(np.linalg.norm(value)),1e-12);self.vector_cache[key]=value
                    if len(self.vector_cache)>16000:self.vector_cache.popitem(last=False)
                else:self.vector_cache.move_to_end(key)
                ids.append(rid);vectors.append(value)
                if len(vectors)>=512:flush()
            flush()
        candidates.sort(reverse=True);return candidates,partial
    def invalidate(self):
        with self.lock:self.vector_cache.clear();self.query_cache.clear()
    def token_count(self,text):
        with self.lock:
            self.last_used=time.monotonic()
            tokenizer=self._load_tokenizer()
            tokenizer.no_truncation()
            try:return len(tokenizer.encode(text).ids)
            finally:tokenizer.enable_truncation(max_length=128)
    def release_if_idle(self,seconds=600,*,keep_tokenizer=False):
        if time.monotonic()-self.last_used<seconds or not self.lock.acquire(blocking=False):return False
        try:
            if self.session is None and (self.tokenizer is None or keep_tokenizer):return False
            if time.monotonic()-self.last_used<seconds:return False
            self.session=None
            if not keep_tokenizer:self.tokenizer=None
            self.vector_cache.clear();self.query_cache.clear();return True
        finally:self.lock.release()
    def status(self):
        return {'ready':self.tokenizer_error is None,'error':self.tokenizer_error,'loaded':self.session is not None,'loads':self.loads,'idle_release_seconds':600,'model':'多语言 MiniLM · 量化版','dimensions':384,'device':'CPU','threads':2,'last_embedding_ms':round(self.timings[-1],1) if self.timings else None,'cached_vectors':len(self.vector_cache),'cache_bytes':sum(v.nbytes for v in self.vector_cache.values())+sum(v.nbytes for v in self.query_cache.values())}

class APIEmbedder:
    def __init__(self, model, route, cancel):
        self.model, self.cancel = model, cancel
        self.model_id, self.label = route['model_id'], route['label']
        self.dimensions = self.last_ms = None
        self.cache = OrderedDict()
        self.cache_generation = 0
        self.lock = threading.RLock()

    def _embed(self, text, query):
        key = hashlib.sha256(text.encode('utf8')).digest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return list(self.cache[key])
            generation = self.cache_generation
        start = time.monotonic()
        value = vector(self.model.ask('memory.embedding', {'model_id':self.model_id,'text':text,'query':query},
                                      timeout=1.18 if query else 12, cancel=self.cancel))
        with self.lock:
            if self.dimensions is not None and self.dimensions != len(value):
                raise CoreError('provider_bad_response','同一向量模型返回了不同维度')
            self.dimensions = len(value)
            self.last_ms = round((time.monotonic()-start)*1000,1)
            if generation == self.cache_generation:
                self.cache[key] = tuple(value)
                if len(self.cache)>128:self.cache.popitem(last=False)
        return value

    def embed(self, text):
        return self._embed(text, False)

    def embed_query(self, text):
        return self._embed(text, True)

    def invalidate(self):
        with self.lock:
            self.cache_generation += 1
            self.cache.clear()

    def status(self):
        with self.lock:
            return {'ready':True,'loaded':bool(self.dimensions),'remote':True,'model':self.label,
                    'dimensions':self.dimensions,'device':'API','last_embedding_ms':self.last_ms,
                    'cached_vectors':len(self.cache)}

class LegacyRemoteExtractor:
    batch_wait_seconds=3.0
    def __init__(self,host):self.host=host;self.rules=RuleExtractor();self.last_error='';self.completed=0
    def extract(self,event):return self.extract_batch([event])[event['id']]
    def extract_batch(self,events):
        result={e['id']:[{k:v for k,v in c.items() if k in {'quote','kind','subject'}} for c in self.rules.extract(e)] for e in events};h=self.host
        selected=[e for e in events if e['role']=='user' and len(e['text'].strip())>=6 and not e['text'].strip().startswith(('例如','比如','假设','假如','“','"'))]
        if not h.memory_config.get('automatic',True) or not h.api_enabled or not selected:return result
        # Finish the visible reply first; background extraction must not delay
        # the response or repeatedly invalidate the in-flight dialogue snapshot.
        end=time.monotonic()+45
        while hasattr(h,'rt') and h.rt.phase in {'thinking','waiting_for_provider','ready'} and time.monotonic()<end:
            if not h.running:raise CoreError('cancelled','已退出')
            time.sleep(.08)
        answer=h.model.ask('memory.extract',{'events':[{'id':e['id'],'text':e['text'],'role':e['role'],'knowledge_layer':e['layer']} for e in selected]},timeout=15,cancel=h.closing)
        if not isinstance(answer,dict) or not isinstance(answer.get('events'),list):raise CoreError('invalid_extraction','整理结果格式无效')
        expected={e['id']:e for e in selected};seen=set()
        for row in answer['events']:
            eid=row.get('event_id')
            if eid not in expected or eid in seen:raise CoreError('invalid_extraction','整理来源不匹配')
            seen.add(eid);items=row.get('memories',[])
            if not isinstance(items,list) or len(items)>10:raise CoreError('invalid_extraction','整理条目过多')
            clean=[]
            for item in items:
                quote=item.get('quote');kind=item.get('kind');subject=item.get('subject','user')
                if not isinstance(quote,str) or not quote.strip() or quote not in expected[eid]['text'] or kind not in {'preference','episode','relationship','plan','temporary','note'} or subject not in {'user','companion'}:raise CoreError('invalid_extraction','整理条目缺少有效原文')
                clean.append({'quote':quote,'kind':kind,'subject':subject})
            # Merge deterministic explicit/name extraction with model-selected
            # literal source spans. Model text never becomes fabricated evidence.
            by_quote={x['quote']:x for x in [*clean,*result[eid]]};result[eid]=list(by_quote.values())[:20]
        if seen!=set(expected):raise CoreError('invalid_extraction','整理来源不完整')
        self.completed+=len(selected);self.last_error='';return result

class EnhancedRecall:
    def __init__(self,host):
        self.host=host;self.original=host.rt.memory.recall;self.timings=deque(maxlen=100);self.last={}
        self.rerank_cache=OrderedDict();self.cache_lock=threading.RLock()
    def recall(self,scope,query,**options):
        start=time.perf_counter();budget=options.get('token_budget',1200);wanted=options.get('top_k',8)
        interpret=isinstance(query,str) and bool(INTERPRETATION_QUERY.search(query))
        options['include_reading_interpretations']=interpret
        pool=dict(options)
        if not isinstance(wanted,int) or not 1<=wanted<=30:return self.original(scope,query,**options)
        if not isinstance(budget,int) or budget<=0:return self.original(scope,query,**options)
        pool.update(top_k=30,token_budget=max(budget,10000));base=self.original(scope,query,**pool);hits=base['hits'];reranked=False;degraded=list(base['degraded_channels']);rerank_status='local'
        h=self.host;cancel=h.closing
        scope=h.rt.memory._scope(scope)
        if options.get('current_event_id') and h.rt.current and 'u:'+h.rt.current['turn_id']==options['current_event_id']:cancel=h.rt.current['cancel']
        economy=h.memory_config.get('cost_mode','economy')=='economy'
        gap=hits[0].get('score',0)-hits[1].get('score',0) if len(hits)>1 else 1.
        reasons=set(hits[0].get('match_reasons',[])) if hits else set()
        confident=('entity_or_exact' in reasons and gap>=.004) or ({'keyword','semantic'}<=reasons and gap>=.008)
        ambiguous=len(hits)>1 and not confident
        submitted=hits[:8 if economy else 20]
        request={'query':query,'candidates':[{'id':m['memory_id'],'text':m['text'][:600],'source':m['knowledge_layer'],'world':m['world_id']} for m in submitted]}
        if h.memory_config.get('guidance'):request['guidance']=h.memory_config['guidance']
        system=getattr(h,'memory_system',None)
        eligible=h.memory_config.get('rerank',True) and h.api_enabled and 2<=len(hits)<=30 and not cancel.is_set() and (not economy or ambiguous)
        cache_key=hashlib.sha256(dumps([scope.owner_id,scope.companion_id,scope.session_id,list(scope.visible_world_ids),base['snapshot_version'],options,h.memory_config,request,[(m['memory_id'],m['revision']) for m in hits]]).encode()).digest()
        ids=None
        if eligible:
            with self.cache_lock:
                cached=self.rerank_cache.get(cache_key)
                if cached and cached[0]>time.monotonic():
                    ids=list(cached[1]);self.rerank_cache.move_to_end(cache_key);rerank_status='cached'
                elif cached:self.rerank_cache.pop(cache_key,None)
        if eligible and ids is None and (system is None or system.reserve('rerank',request)):
            try:
                answer=h.model.ask('memory.rerank',request,timeout=7,cancel=cancel)
                if system:system.account('rerank',request,answer)
                ids=answer.get('ids');allowed={m['memory_id'] for m in submitted}
                if not isinstance(ids,list) or any(not isinstance(x,str) or x not in allowed for x in ids) or len(set(ids))!=len(ids):raise ValueError('重排结果无效')
                if cancel.is_set():raise ValueError('重排已取消')
                rerank_status='model'
            except Exception:ids=None;degraded.append('rerank_unavailable');rerank_status='failed'
        elif eligible and ids is None:rerank_status='budget'
        extra_passages=[]
        with h.rt.memory.lock:
            if h.rt.memory._state(scope)[0]!=base['snapshot_version']:
                with self.cache_lock:self.rerank_cache.clear()
                # A local refresh still needs the same source checks and budget.
                base=self.original(scope,query,**pool)
                hits=base['hits']
                degraded=list(base['degraded_channels'])
                rerank_status='snapshot_changed'
                ids=None
            if ids is not None and not cancel.is_set():
                if rerank_status=='model':
                    with self.cache_lock:
                        self.rerank_cache[cache_key]=(time.monotonic()+600,tuple(ids))
                        while len(self.rerank_cache)>128:self.rerank_cache.popitem(last=False)
                by_id={m['memory_id']:m for m in hits}
                # An inexpensive top-8 request cannot judge the remaining pool.
                hits=[by_id[mid] for mid in ids]+hits[len(submitted):];reranked=True
            if system:
                system.annotate(scope,hits,query=query)
                eligible_hits=[]
                for item in hits:
                    if item.get('qualifiers',{}).get('reading_note')=='interpretation':
                        evidence=note_evidence(h.rt.memory,scope,item)
                        if not evidence:continue
                        item['reading_interpretation']=evidence
                    location=document_source(h.rt.memory,scope,item)
                    if location:item['document_source']=location
                    eligible_hits.append(item)
                hits=eligible_hits
                if interpret:hits.sort(key=lambda item:not item.get('reading_interpretation'))
                if hits and hits[0].get('document_source') and not any(
                        options.get(key) for key in ('as_of','time_from','time_to')):
                    extra_passages=related_passages(h.rt.memory,scope,hits[0],hits[0]['document_source'],
                                                   query,{item['memory_id'] for item in hits})
            context=json.loads(base['context']) if base['context'] else {'identity':None,'current_turn':[],'memories':[]}
            parts={(m['memory_id'],m['revision']):m for m in context['memories']};context['memories']=[]
            if extra_passages:
                hits=[hits[0],*(item for item,_ in extra_passages),*hits[1:]]
                parts.update({(item['memory_id'],item['revision']):part for item,part in extra_passages})
            if options.get('current_event_id'):
                excerpt_versions={item['document_source']['version_id'] for item in hits if item.get('document_source')
                                  and item.get('qualifiers',{}).get('document_root') is not True}
                hits=[item for item in hits if not (item.get('qualifiers',{}).get('document_root') is True
                      and item['memory_id'] in excerpt_versions)]
                profile=getattr(h.rt,'profile',None)
                if profile and context.get('identity'):
                    persona=profile.as_dict()
                    if all(persona.get(key)==value for key,value in context['identity'].items()):
                        context['identity']=None
                context['current_turn']=[claim for claim in context['current_turn'] if not (
                    claim.get('status')=='current_user_statement' and
                    claim.get('event_id')==options['current_event_id'] and
                    isinstance(claim.get('text'),str) and claim['text'] in query)]
            counter=h.rt.memory.token_counter or (lambda text:len(text.encode('utf8')))
            if counter(dumps(context))>budget:context['identity']=None
            if counter(dumps(context))>budget:context['current_turn']=[]
            chosen=[]
            for item in hits:
                part=parts.get((item['memory_id'],item['revision']))
                if part is None:continue
                if item.get('category'):part={**part,'category':item['category']}
                if item.get('document_source'):
                    if options.get('current_event_id'):
                        part={key:part[key] for key in ('memory_id','revision','text','world_id','knowledge_layer')}
                    part['document_source']=item['document_source']
                if item.get('reading_interpretation'):
                    part={key:part[key] for key in ('memory_id','revision','text','world_id','knowledge_layer')}
                    part['reading_interpretation']=item['reading_interpretation']
                context['memories'].append(part)
                if counter(dumps(context))>budget:context['memories'].pop();continue
                chosen.append(item)
                if len(chosen)>=wanted:break
            rendered=dumps(context) if counter(dumps(context))<=budget else ''
            base.update(hits=chosen,context=rendered,status='ok' if chosen else 'no_match',degraded_channels=degraded,reranked=reranked,rerank_status=rerank_status)
            base['token_usage'].update(used=counter(rendered) if rendered else 0,budget=budget)
        elapsed=(time.perf_counter()-start)*1000;self.timings.append(elapsed);self.last={'query':query[:160],'hits':len(chosen),'reranked':reranked,'rerank_status':rerank_status,'milliseconds':round(elapsed,1),'degraded':degraded}
        return base

class RemoteExtractor(LegacyRemoteExtractor):
    batch_wait_seconds=6.0
    structured_rules=True
    def __init__(self,host):
        super().__init__(host);self.result_cache=OrderedDict();self.result_lock=threading.RLock()

    def ready_to_commit(self):
        return getattr(self.host.rt,'phase','idle') in {'idle','paused'}

    def local(self,event):
        from companionship_memory import local_candidates
        from companion_scheduler import focus_request
        from memory_system import IMPORTANT,NONFACT,explicit_payload
        text=event['text'].strip()
        if event['role']=='user' and focus_request(text):return []
        if text.startswith(NONFACT):return []
        explicit=explicit_payload(event)
        if event['role']=='user' and IMPORTANT.match(text) and not explicit:return []
        return local_candidates(event,self.rules,explicit)

    def _generation(self,events):
        from pet_memory import Scope
        m=self.host.rt.memory
        with m.lock:
            return tuple((e.get('owner'),e.get('pet'),m._state(Scope(e['owner'],e['pet'],(e['world'],),e['session']))[1]) for e in events)

    def extract_batch(self,events):
        import math
        from companionship_memory import TEMPORAL, IMPERATIVE, remote_candidate, unasserted_quote
        from companion_scheduler import focus_request
        from memory_system import NONFACT,IMPORTANT,explicit_payload
        h=self.host;system=getattr(h,'memory_system',None)
        if h.closing.is_set():raise CoreError('cancelled','已退出')
        if not self.ready_to_commit():raise CoreError('memory_deferred','对话结束后继续整理')
        result={e['id']:self.local(e) for e in events}
        economy=h.memory_config.get('cost_mode','economy')=='economy'
        selected=[e for e in events if e['role']=='user' and len(e['text'].strip())>=6
                  and not e['text'].strip().startswith(NONFACT)
                  and not TEMPORAL.match(e['text'].strip()) and not IMPERATIVE.search(e['text'].strip())
                  and not focus_request(e['text'])
                  and not (IMPORTANT.match(e['text'].strip()) and not explicit_payload(e))
                  and (not economy or (not result[e['id']] and len(e['text'].strip())>=6))]
        if not h.memory_config.get('automatic',True) or not h.api_enabled or not selected:return result
        generation=self._generation(selected)
        request={'events':[{'id':e['id'],'text':e['text'],'role':e['role'],'knowledge_layer':e['layer']} for e in selected]}
        guidance=h.memory_config.get('guidance','')
        if guidance:request['guidance']=guidance
        epoch=getattr(h,'memory_extract_epoch',0)
        event_sources=[(e.get('seq'),e.get('world'),e.get('session')) for e in selected]
        key=hashlib.sha256(dumps([generation,epoch,event_sources,request]).encode()).digest()
        with self.result_lock:
            for stale in list(self.result_cache):
                if self.result_cache[stale][0]<time.monotonic():self.result_cache.pop(stale,None)
            cached=self.result_cache.get(key)
            packed=cached[1] if cached else None
        if packed is None:
            if system and not system.reserve('extract',request):return result
            answer=h.model.ask('memory.extract',request,timeout=15,cancel=h.closing)
            if system:system.account('extract',request,answer)
            if not isinstance(answer,dict) or not isinstance(answer.get('events'),list):raise CoreError('invalid_extraction','整理格式无效')
            expected={e['id']:e for e in selected};seen=set();packed={}
            # Validate the whole response before publishing any annotations.
            for row in answer['events']:
                if not isinstance(row,dict):raise CoreError('invalid_extraction','整理格式无效')
                eid=row.get('event_id')
                if eid not in expected or eid in seen:raise CoreError('invalid_extraction','来源不匹配')
                seen.add(eid);items=row.get('memories',[])
                if not isinstance(items,list) or len(items)>10:raise CoreError('invalid_extraction','条目过多')
                packed[eid]=[]
                for item in items:
                    if not isinstance(item,dict):raise CoreError('invalid_extraction','条目无效')
                    quote=item.get('quote');kind=item.get('kind');subject=item.get('subject','user')
                    if not isinstance(quote,str) or not quote.strip() or quote not in expected[eid]['text'] or kind not in {'preference','episode','relationship','plan','temporary','note'} or subject not in {'user','companion'}:raise CoreError('invalid_extraction','缺少有效原文')
                    # A literal quote in a question, quotation or example is not an assertion.
                    source=expected[eid]['text']
                    if quote.strip().startswith(NONFACT) or unasserted_quote(source,quote):continue
                    a=source.index(quote)
                    score=item.get('importance',.5);topics=item.get('topics',[])
                    if not isinstance(score,(int,float)) or isinstance(score,bool) or not math.isfinite(score) or not 0<=score<=1 or not isinstance(topics,list) or len(topics)>6 or any(not isinstance(t,str) or not 1<len(t.strip())<=24 for t in topics):raise CoreError('invalid_extraction','重要程度或主题缺少依据')
                    packed[eid].append((a,a+len(quote),kind,subject,score,[t.strip() for t in topics]))
            if seen!=set(expected):raise CoreError('invalid_extraction','整理来源不完整')
            if generation!=self._generation(selected) or epoch!=getattr(h,'memory_extract_epoch',0) or guidance!=h.memory_config.get('guidance','') or h.closing.is_set():
                with self.result_lock:self.result_cache.clear()
                raise CoreError('memory_deferred','来源或配置变化，稍后重新检查')
            # Cache only offsets and labels for this exact batch, never source text
            # or generated facts. A new event always gets its own validation.
            with self.result_lock:
                self.result_cache[key]=(time.monotonic()+600,packed)
                while len(self.result_cache)>64:self.result_cache.popitem(last=False)
            self.completed+=len(selected)
        if not self.ready_to_commit():raise CoreError('memory_deferred','对话结束后继续整理')
        if generation!=self._generation(selected) or epoch!=getattr(h,'memory_extract_epoch',0) or guidance!=h.memory_config.get('guidance',''):
            raise CoreError('memory_deferred','来源或配置变化，稍后重新检查')
        annotations=[]
        for event in selected:
            eid=event['id']
            clean=[]
            for a,b,kind,subject,score,topic_spans in packed[eid]:
                quote=event['text'][a:b]
                candidate=remote_candidate(event,quote,kind,subject,score)
                if candidate is None:continue
                clean.append(candidate)
                annotations.append((event,quote,{'importance':score,'topics':list(topic_spans)}))
            # Local structured fields (notably preferred_name) win equal spans.
            result[eid]=list({x['quote']:x for x in [*clean,*result[eid]]}.values())[:20]
        if system:system.stage_annotations(annotations)
        self.last_error='';return result
