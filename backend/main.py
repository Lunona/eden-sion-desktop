"""Local bridge: accepted v105 controls and source-backed companion memory."""
from pathlib import Path
from datetime import datetime
import sys,json,time,threading,queue,math,heapq,uuid,sqlite3,re
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE/'vendor'),str(HERE/'controls')]
import numpy as np
sys.path.insert(0,str(HERE/'pydeps'))
from enhanced_memory import APIEmbedder,LocalEmbedder,RemoteExtractor,EnhancedRecall
from memory_system import MemorySystem,NONFACT
from companionship_memory import TEMPORAL,IMPERATIVE,unasserted_quote
from memory_notes import import_note,read_note
from reading_notes import ReadingNotes,public_notes
from memory_transfer import export_data,import_extension
from companion_presence import Presence
from companion_events import EventJournal
from companion_scheduler import CompanionScheduler,focus_request
from companion_day import RoleActivities
from special_days import SpecialLetters,parse_draft
from conversation_learning import ConversationLearning
from pet_companion.runtime import CompanionRuntime
from pet_companion.models import CoreError
from pet_memory.types import now as memory_now
from pet_companion.presentation import PresentationScheduler
from interaction_engine105 import Engine,Motion
from rig_limits import clamp_value
from face_presets104 import FACE_VALUES,FACE_LABELS
from actions92 import INTERACTIONS

OUT=threading.Lock()
PROVIDER_CODES={'provider_timeout','provider_credentials','provider_rate_limit','provider_unavailable',
                'provider_request_rejected','provider_network','provider_bad_response'}
def write(obj):
    with OUT:
        sys.stdout.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n');sys.stdout.flush()

class RemoteModel:
    mode='configured_host_model'
    def __init__(self):self.waiters={};self.lock=threading.Lock();self.serial=0;self.wait_audio=set();self.visual_plans={};self.reply_notes={};self.memory_slots=threading.BoundedSemaphore(2)
    def ask(self,purpose,payload,*,timeout=15,cancel=None):
        cancel=cancel or threading.Event();memory=purpose!='dialogue'
        if memory and not self.memory_slots.acquire(blocking=False):raise CoreError('memory_busy','后台整理繁忙')
        with self.lock:
            self.serial+=1;ident=str(self.serial);q=queue.Queue(1);self.waiters[ident]=q
        write({'event':'provider.request','id':ident,'request':{'purpose':purpose,**payload}})
        try:
            until=time.monotonic()+timeout
            while not cancel.is_set() and time.monotonic()<until:
                try:
                    result=q.get(timeout=.05)
                    if result.get('error'):
                        code=result.get('code')
                        raise CoreError(code if isinstance(code,str) and code in PROVIDER_CODES else 'provider_failed',result['error'])
                    return result.get('value',result)
                except queue.Empty:pass
            raise CoreError('cancelled' if cancel.is_set() else 'provider_timeout','请求已结束')
        finally:
            with self.lock:self.waiters.pop(ident,None)
            if memory:self.memory_slots.release()
            write({'event':'provider.closed','id':ident})
    def generate(self,request,cancel):
        inherited=[]
        history_replies=request.pop('_history_replies',())
        presence=self.presence_context(inherited) if hasattr(self,'presence_context') else {}
        result=self.ask('dialogue',{**request,'companion_presence':presence},timeout=185,cancel=cancel)
        if not cancel.is_set():
            token=(request['turn_id'],request['generation'])
            hits=request['memory']['hits']
            turns=[row['id'] for row in request['history']]
            turns.extend(source[2:] for hit in hits for source in hit.get('source_event_ids',()) if source.startswith('u:'))
            request['_reply_sources']=MemorySystem.source_refs(turns,((hit['memory_id'],hit['revision']) for hit in hits),
                                                               inherited,replies=history_replies)
            with self.lock:
                self.visual_plans[token]=result.get('visual',{})
                while len(self.visual_plans)>12:self.visual_plans.pop(next(iter(self.visual_plans)))
                # A context refresh replaces all side effects for the same turn.
                self.reply_notes.pop(token,None)
                notes=result.get('notes')
                if isinstance(notes,dict) and notes:
                    refs=MemorySystem.source_refs(turns=[token[0]],replies=[token[0]])
                    self.reply_notes[token]={'notes':notes,'refs':refs,'delivered':False,'ended':False}
                    while len(self.reply_notes)>12:self.reply_notes.pop(next(iter(self.reply_notes)))
        if result.get('await_audio'):self.wait_audio.add((request['turn_id'],request['generation']))
        return result['plan']
    def complete(self,ident,result):
        with self.lock:q=self.waiters.get(ident)
        if q:
            try:q.put_nowait(result)
            except queue.Full:pass

class HostScheduler(PresentationScheduler):
    def __init__(self,model):super().__init__();self.model=model
    def start(self,turn_id,plan,generation):
        with self.lock:
            events=super().start(turn_id,plan,generation)
            if (turn_id,generation) in self.model.wait_audio:
                self.model.wait_audio.discard((turn_id,generation))
                # Wait for actual playback, not synthetic mouth movement.
                self.queue=[e for e in self.queue if e[2]!='presentation.completed'];heapq.heapify(self.queue)
                self._cue(self.clock()+125,'presentation.completed',{})
            return events

class Param:
    def __init__(self,p):self.p=p
    def getId(self):return self.p['id']
    def getMinimumValue(self):return self.p['minimum']
    def getMaximumValue(self):return self.p['maximum']
    def getDefaultValue(self):return self.p['default']

def angle(a,b):return (math.atan2(b[1],b[0])-math.atan2(a[1],a[0])+math.pi)%(2*math.pi)-math.pi
class LegacyPhysics:
    def inputs(self,setting,values):
        translation=0.;total_angle=0.
        for inp in setting['Input']:
            p=self.c.params[inp['Source']['Id']];lo=float(p.getMinimumValue());hi=float(p.getMaximumValue());mid=(lo+hi)/2
            value=clamp_value(values.get(p.getId(),p.getDefaultValue()),lo,hi)
            norm=setting['Normalization']['Angle' if inp['Type']=='Angle' else 'Position'];n=norm['Default']
            if value>mid:n+=(value-mid)/(hi-mid)*(norm['Maximum']-n)
            elif value<mid:n+=(value-mid)/(lo-mid)*(norm['Minimum']-n)
            n*=inp['Weight']/100*(1 if inp['Reflect'] else -1)
            if inp['Type']=='X':translation+=n
            else:total_angle+=n
        rad=-math.radians(total_angle)
        return np.array([translation*math.cos(rad),translation*math.sin(rad)]),np.array([math.sin(-rad),math.cos(-rad)])

# Supply only the pure arithmetic dependencies; never load Java/Core or a second renderer.
import types
dep=types.ModuleType('physics_pose_preview');dep.Physics=LegacyPhysics;sys.modules[dep.__name__]=dep
dep=types.ModuleType('runtime_preview');dep.angle=angle;sys.modules[dep.__name__]=dep
from hair_physics93 import Physics

class Host:
    def __init__(self,data,runtime,*,shadow=False):
        self.shadow=shadow
        self.observation_errors=0
        self.runtime=Path(runtime);self.model=RemoteModel();self.running=True;self.closing=threading.Event();self.api_enabled=False
        self.data=Path(data);self.data.mkdir(parents=True,exist_ok=True);self.config_file=self.data/'enhancement.json'
        self.memory_extract_epoch=0
        self.memory_config={'automatic':True,'rerank':True,'cost_mode':'economy','daily_calls':80,'daily_input_tokens':120000,'guidance':''}
        try:
            saved=json.loads(self.config_file.read_text('utf8')) if self.config_file.exists() else {}
            if isinstance(saved,dict):
                for k in ('automatic','rerank'):
                    if isinstance(saved.get(k),bool):self.memory_config[k]=saved[k]
                if saved.get('cost_mode') in ('economy','quality'):self.memory_config['cost_mode']=saved['cost_mode']
                if isinstance(saved.get('daily_calls'),int) and not isinstance(saved['daily_calls'],bool) and 0<=saved['daily_calls']<=200:self.memory_config['daily_calls']=saved['daily_calls']
                if isinstance(saved.get('daily_input_tokens'),int) and not isinstance(saved['daily_input_tokens'],bool) and 0<=saved['daily_input_tokens']<=2000000:self.memory_config['daily_input_tokens']=saved['daily_input_tokens']
                if isinstance(saved.get('guidance'),str) and len(saved['guidance'])<=1000:self.memory_config['guidance']=saved['guidance']
        except (ValueError,OSError):pass
        self.embedding_error='';self.embedder=None
        try:self.embedder=LocalEmbedder(HERE/'models/multilingual-minilm')
        except Exception as exc:self.embedding_error=str(exc)[:300]
        self.local_embedder=self.embedder
        self.extractor=RemoteExtractor(self)
        profile=json.loads((HERE/'profile.json').read_text('utf8'))
        self.rt=CompanionRuntime(data,owner_id='local-user',companion_id='eden-sion',session_id='desktop-main',profile=profile,model=self.model,scheduler=HostScheduler(self.model),memory_options={'extractor':self.extractor,'embedder':self.embedder,'semantic_threshold':.38,'retrieval_timeout':1.2})
        self.events=EventJournal(self.data/'core-shadow.sqlite' if shadow else self.rt.store.path,
                                 max_events=None if shadow else 6000)
        self.actions=CompanionScheduler(self.rt.store,self.rt.owner,self.rt.pet)
        self.roles=RoleActivities(self.rt.store,self.rt.owner,self.rt.pet)
        self.reading_notes=ReadingNotes(self)
        self.role_program='idle';self.role_dirty=False
        self.letters=SpecialLetters(self.rt.store,self.rt.owner,self.rt.pet)
        self.letter_lock=threading.RLock();self.letter_thread=None;self.letter_cancel=None;self.letter_item=None
        self.last_letter_probe=-30.
        self.model.local_reply=self.actions.local_reply
        saved_profile=self.rt.profile.as_dict()
        if not saved_profile['canon_profile']:
            saved_profile['canon_profile']=profile['canon_profile']
            if saved_profile['self_description']=='我知道自己来自《eden*》，现在通过桌宠与你交流，也能理解现实生活。原作事实与相处经历保留各自出处；不知道的情节不编造。':
                saved_profile['self_description']=profile['self_description']
            self.rt.set_profile(saved_profile,expected_revision=self.rt.profile_revision)
        with self.rt.memory.lock:upgraded=self.rt.memory.db.execute("SELECT value FROM settings WHERE key='sion_memory_extension_version'").fetchone()
        if not upgraded:
            destination=self.data/'backups'/'memory-before-0.6.0.sqlite'
            if not destination.exists():self.rt.memory.backup(destination)
        self.memory_system=MemorySystem(self)
        self.rt.memory.import_extension=lambda s,data,planned,dry_run:import_extension(self,s,data,planned,dry_run)
        self.rt.memory.db.execute("INSERT OR REPLACE INTO settings VALUES('sion_memory_extension_version','3')")
        self.rt.prepare_memory_source=self.capture_local
        self.retrieval=EnhancedRecall(self);self.rt.memory.recall=self.retrieval.recall
        if self.embedder:
            with self.rt.memory.lock:old=self.rt.memory.db.execute("SELECT value FROM settings WHERE key='sion_embedding_model'").fetchone()
            if not old or old[0]!=self.embedder.model_id:
                self.rt.memory.reindex(self.rt.scope())
                with self.rt.memory.lock:self.rt.memory.db.execute("INSERT OR REPLACE INTO settings VALUES('sion_embedding_model',?)",(self.embedder.model_id,))
        self.lock=threading.RLock();self.engine=None;self.params={};self.cursor=self.rt.status()['event_cursor'];self.running=True
        self.presence=Presence(self.data,FACE_LABELS,track_legacy_points=False)
        self.touch_contact=None
        self.actions.migrate_reminders(self.presence.data['reminders'])
        self.learning=ConversationLearning(self.rt,self.presence)
        self.model.presence_context=self.conversation_context
        self.model.source_filter=lambda scope,refs:self.memory_system.sources_valid(scope,refs)
        self.active_visual=None;self.reply_action=None;self.manual_override_until=0;self.manual_blush_until=0
        self.visual_token=None;self.visual_started=None;self.queued_visual=None
        self.last_auto_motion=-20.;self.automatic_blush=0.;self.weather_wind=(1.,0.,0.)
        self.ambient_action=None;self.next_ambient=26.;self.last_ambient_index=0;self.window_dragging=False
        self.manual_wind_until=0.;self.preparation_idle=False;self.render_visible=True
        self.start=time.monotonic();self.sim=0.;self.chat_face=None;self.manual_face='neutral';self.chat_motion=None;self.mouth_level=0.;self.motion_enabled=True;self.applied_face=None
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def companion_status(self,status=None,*,sources=None):
        status=self.presence.status() if status is None else status
        status['interaction_policy']=self.memory_system.interaction_policy(self.rt.scope(),status['relationship'])
        scheduled=self.actions.status()
        status['focus']=scheduled['focus']
        status['proactive_enabled']=self.actions.proactive_enabled
        status['reminders']=sorted(scheduled['reminders'],key=lambda item:item['at'])
        status['activity']=self.roles.snapshot(self.rt.phase,self.role_program)
        entries=self.presence.occasion_entries()
        if entries:status['special_days']=self.letters.public(entries,self.letter_memory)
        scope=self.rt.scope()
        status['open_loops']=self.memory_system.active_open_loops(scope,6,sources=sources)
        status['diaries']=self.memory_system.recent_diaries(scope,6,sources=sources)
        status['soul_state']=self.memory_system.soul_state(scope)
        status['state_continuity']=self.memory_system.active_state_continuity(scope,5,sources=sources)
        status['dialogue_episodes']=self.memory_system.recent_dialogue_episodes(scope,4,sources=sources)
        status['user_profile']=self.memory_system.user_profile_summary(scope,sources=sources)
        status['expression_decision']=self.memory_system.expression_decision(status['interaction_policy'],status['emotion'],status['soul_state'])
        status['self_timeline']=self.memory_system.self_timeline(scope,status.get('activity'),8)
        return status

    def letter_memory(self,identifier,revision):
        current=self.memory_system.letter_memories(self.rt.scope(),reference=(identifier,revision))
        return current[0]['text'] if current else None

    def letter_eligible(self):
        policy=self.memory_system.interaction_policy(self.rt.scope(),self.presence.relationship())
        return policy['stage'] in ('familiar','close','intimate','deeply_bonded','owner_exclusive')

    def relationship_visual(self,visual):
        familiar=self.letter_eligible()
        entries=self.presence.occasion_entries()
        return {**visual,'familiar':familiar,
                'surprise_hint':bool(entries and familiar and self.letters.has_sealed_surprise(entries))}

    def prepare_letter(self,item,stamp,cancel):
        try:
            sources=self.memory_system.letter_memories(self.rt.scope(),occasion=item['title'],kind=item['kind'])
            request={'kind':item['kind'],'memories':[source['text'] for source in sources]}
            draft=None
            if (sources and self.api_enabled and not cancel.is_set() and
                    self.letters.mark_attempt(item['id'],stamp) and self.memory_system.reserve('background',request)):
                try:
                    result=self.model.ask('letter.draft',request,timeout=12,cancel=cancel)
                    self.memory_system.account('background',request,result)
                    draft=parse_draft(result.get('draft') if isinstance(result,dict) else None,len(sources))
                except CoreError:
                    pass
            with self.letter_lock:
                if cancel.is_set() or not self.letter_eligible():
                    self.letters.pause(item['id'],stamp)
                else:
                    wish,index=draft if draft else (None,0)
                    self.letters.seal(item['id'],stamp,wish,sources[index] if sources else None)
        except (ValueError,sqlite3.Error):
            self.letters.pause(item['id'],stamp)

    def schedule_notice(self,now):
        with self.letter_lock:
            entries=self.presence.occasion_entries()
            available=self.rt.phase=='idle' and self.role_program in ('idle','listening') and self.actions.allows_background()
            role_available=self.roles.optional_speech_allowed() if entries and available else False
            if not available and self.letter_cancel:self.letter_cancel.set()
            # Explicit reminders take precedence inside take_due, even when a card is ready.
            candidate=self.letters.due(entries,self.letter_eligible) if role_available else None
            notice,changed=self.actions.take_due(candidate)
            if (not notice and role_available and self.preparation_idle
                    and (not self.letter_thread or not self.letter_thread.is_alive()) and now-self.last_letter_probe>=10):
                self.last_letter_probe=now
                pending=self.letters.reserve(entries,self.letter_eligible)
                if pending:
                    self.letter_item=pending[0]['id']
                    self.letter_cancel=threading.Event()
                    self.letter_thread=threading.Thread(target=self.prepare_letter,args=(*pending,self.letter_cancel),
                                                        name='companion-background',daemon=True)
                    self.letter_thread.start()
            return notice,changed
    def dialogue_history(self):
        with self.rt.lock:
            self.rt._reconcile_deleted_context()
            return [row for row in self.rt.store.history(self.rt.owner,self.rt.pet,session=self.rt.session,limit=24)
                    if row['context_valid'] and row['status']=='completed' and row['mode']!='proactive'
                    and not (row['mode'] or '').startswith('desktop:')]

    def conversation_context(self,sources=None):
        status=self.companion_status(sources=sources)
        relation=status['interaction_policy']
        activity=status['activity']['current']
        return {'relationship':{'stage':relation['label'],'tone':relation['tone'],'focus_preference':(relation['focus_preference'] or {}).get('value')},
                'interaction':status['emotion']['label'],'today':status['today'],
                'focus':{k:status['focus'][k] for k in ('activity','ends_at','quiet')} if status['focus'] else None,
                'role_activity':{'kind':activity['kind'],'source':'当前角色活动。虚拟休息和待机仅属于桌宠角色，不能当成现实观察或用户经历'},
                'learned_style':self.learning.guidance(),
                'private_subconscious':[x['content'] for x in self.memory_system.recent_secret_thoughts(self.rt.scope(),2,sources=sources)],
                'exclusive_bond':relation.get('exclusive_bond') or None,
                'open_loops':[x['topic'] for x in status.get('open_loops',[])[:4]],
                'recent_diaries':[{'kind':x['kind'],'content':x['content']} for x in status.get('diaries',[])[:2]],
                'soul_state':status.get('soul_state'),
                'expression_band':status.get('expression_decision'),
                'state_continuity':[x['state_text'] for x in status.get('state_continuity',[])[:4]],
                'dialogue_episodes':[x['summary'] for x in status.get('dialogue_episodes',[])[:2]],
                'user_profile':{x['attr_label']:x['attr_value'] for x in status.get('user_profile',[])[:6]},
                'self_timeline':[x['summary'] for x in status.get('self_timeline',[])[:5]]}
    def capture_local(self,event_id):
        scope=self.rt.scope()
        with self.rt.memory.lock:event=self.rt.memory.db.execute('SELECT * FROM events WHERE owner=? AND pet=? AND id=?',(scope.owner_id,scope.companion_id,event_id)).fetchone()
        if event:
            requested=focus_request(event['text']) if event['role']=='user' and not event['excluded'] else None
            if requested:
                self.capture_focus(scope,event,requested)
                write({'event':'presence.changed','state':self.companion_status()})
                return
            for item in self.extractor.local(dict(event)):
                try:self.rt.memory.remember(scope,item['quote'],event_id=event_id,quote=item['quote'],world_id=event['world'],knowledge_layer=event['layer'],**{k:v for k,v in item.items() if k!='quote'})
                except Exception:self.rt._emit('memory.write_failed',None,{'code':'local_rule_not_committed'})
    def capture_focus(self,scope,event,request):
        turn_id=event['id'][2:]
        if request['kind']=='start':
            policy=self.memory_system.interaction_policy(scope,{'manual':None})['focus_preferences']
            preference=policy.get(request['activity']) or policy.get('default') or {}
            self.actions.start(turn_id,request,focus_preference=preference.get('value'))
        elif request['kind']=='cancel':
            self.actions.cancel(turn_id)
        else:
            recent=self.actions.recent_focus(request['activity'])
            if recent is None:
                self.actions.save_reply(turn_id,'可以告诉我以后'+request['activity']+'时希望我怎么陪你。')
                return
            quote=event['text'].strip()
            result=self.rt.memory.remember(scope,quote,event_id=event['id'],quote=quote,
                world_id=event['world'],knowledge_layer=event['layer'],kind='preference',
                predicate='proactive_focus',qualifiers={'activity':request['activity']},
                value='quiet' if recent['quiet'] else 'normal')
            if result['status']=='committed':
                message='记下了，以后'+request['activity']+'时'+('默认安静陪伴。' if recent['quiet'] else '可以主动搭话。')
            else:
                message='这条和之前的偏好不同，已放到待确认记忆里。'
            self.actions.save_reply(turn_id,message,task_id=recent['id'])
    def now(self):return time.monotonic()-self.start
    def init(self,params):
        with self.lock:
            if self.engine:return {'ready':True}
            if len(params)>256 or not all(isinstance(p.get('id'),str) and all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ['minimum','maximum','default']) for p in params):raise ValueError('参数无效')
            self.params={p['id']:Param(p) for p in params};self.defaults={k:p.getDefaultValue() for k,p in self.params.items()}
            ranges={k:(p.getMinimumValue(),p.getMaximumValue()) for k,p in self.params.items()}
            motions={i:Motion.read(self.runtime/'motions'/f'{n}.motion3.json') for i,(n,_) in enumerate(INTERACTIONS,1)}
            self.engine=Engine(self.defaults,ranges,motions,FACE_VALUES,json.loads((self.runtime/'五元音口型控制.json').read_text('utf8')),Motion.read(self.runtime/'motions/Idle192.motion3.json'))
            core=types.SimpleNamespace(params=self.params,defaults=self.defaults,runtime=self.runtime)
            self.physics=Physics(core)
            for _ in range(180):self.physics.step(self.defaults)
            self.start=time.monotonic();self.sim=0.
            return {'ready':True,'faces':FACE_LABELS,'actions':INTERACTIONS}
    def animate_idle(self,now):
        engine=self.engine
        config=self.presence.data['config']
        available=(self.motion_enabled and config['ambient_actions'] and not self.window_dragging and self.rt.phase=='idle'
                   and self.role_program in ('idle','listening') and time.time()>=self.manual_override_until)
        if self.ambient_action is not None:
            if self.ambient_action is engine.active:
                if not available:engine.cancel(now)
                else:return
            self.ambient_action=None
        if (not available or now<self.next_ambient or now-self.last_auto_motion<12
                or engine.contact or engine.release or engine.demo or engine.combo or engine.active or engine.fading):
            return
        self.next_ambient=now+2
        quiet=now-engine.last_input
        if not 12<=quiet<engine.sleep_after or engine.sleep_blend>.1:
            return
        face=self.presence.lingering()
        index=8 if face in ('shy','bashful','embarrassed') else 2 if face in ('curious','expectant') else 3
        if index==self.last_ambient_index:index=1
        last_input=engine.last_input
        if engine.trigger(index,now,mirror=self.last_ambient_index==1):
            self.ambient_action=engine.active
            self.ambient_action.amplitude=.4
            self.last_ambient_index=index
            self.next_ambient=now+38+6*math.sin(now*.13)
        engine.last_input=last_input
    def animate_reply(self,token,visual):
        if self.rt.scheduler.status()['active']=={'turn_id':token[0],'generation':token[1]}:
            self.active_visual=visual
            self.chat_face=(visual or {}).get('face')
            now=self.now()
            engine=self.engine
            if (visual and engine and self.motion_enabled and not
                    (engine.contact or engine.release or engine.demo or engine.combo or engine.active)
                    and now-self.last_auto_motion>=7):
                if visual['action'] and engine.trigger(visual['action'],now,mirror=visual['mirror']):
                    self.reply_action=(token,engine.active)
                    self.last_auto_motion=now
                elif visual['gesture']:
                    self.chat_motion=(visual['gesture'],now,1.35);self.last_auto_motion=now
        write({'event':'presence.changed','state':self.companion_status()})
    def cancel_reply_action(self,token=None):
        if not self.reply_action:return
        owner,action=self.reply_action
        if token is not None and token!=owner:return
        self.reply_action=None
        if self.engine.active is action:
            self.engine.cancel(self.now())
    def reply_visual(self,p):
        token=(p.get('turn_id'),p.get('generation'))
        if token!=self.visual_token:return False
        if self.visual_started is None:
            self.queued_visual=p['visual']
            return True
        started=self.visual_started
        self.visual_token=None
        if self.now()-started>12:return False
        visual=self.relationship_visual({**p['visual'],'relationship_eligible':True})
        self.animate_reply(token,self.presence.decorate(str(token),visual))
        return True
    def observe(self,kind,source,*,event_id=None,turn_id=None,generation=None,progress=None):
        try:
            return self.events.record(event_id or uuid.uuid4().hex,kind,source,turn_id=turn_id,
                                      generation=generation,progress=progress)
        except (sqlite3.Error,OSError,ValueError):
            self.observation_errors+=1
            return 'observation_failed'
    def finish_reply_notes(self,kind,token,reason):
        with self.model.lock:
            pending=self.model.reply_notes.get(token)
            if not pending:return
            if kind in ('turn.interrupted','turn.failed') or kind=='presentation.cancelled' and reason!='audio_ended':
                self.model.reply_notes.pop(token,None)
                return
            if kind=='turn.delivered':pending['delivered']=True
            elif kind in ('presentation.completed','presentation.cancelled'):pending['ended']=True
            if not (pending['delivered'] and pending['ended']):return
            self.model.reply_notes.pop(token,None)
        if not self.memory_config.get('automatic',True):return
        with self.rt.lock:
            turn=self.rt.store.turn(self.rt.owner,self.rt.pet,token[0])
            if not turn or turn['status']!='completed' or not turn['context_valid'] or turn['session']!=self.rt.session:return
            scope=self.rt.scope()
            refs=pending['refs']
            if not self.memory_system.sources_valid(scope,refs):return
            with self.rt.memory._tx():
                self.save_reply_notes(scope,turn,pending['notes'],refs)
        self.role_dirty=True

    def save_reply_notes(self,scope,turn,notes,refs):
        status=self.presence.status()
        emotion=status['emotion']['label']
        def items(key,limit):
            value=notes.get(key)
            return value[:limit] if isinstance(value,list) else []
        if notes.get('secret'):
            self.memory_system.save_secret_thought(scope,notes['secret'],turn_id=turn['id'],emotion=emotion,
                                                  stage=status['relationship']['label'],sources=refs)
        for loop in items('open_loops',3):
            self.memory_system.save_open_loop(scope,loop,sources=refs)
        for resolved in items('resolved_loops',3):
            self.memory_system.resolve_open_loop(scope,resolved)
        for diary in items('diaries',2):
            if isinstance(diary,dict):
                self.memory_system.save_diary_entry(scope,diary.get('content',''),kind=diary.get('kind','diary'),emotion=emotion,sources=refs)
        for state in items('state_continuity',2):
            self.memory_system.save_state_continuity(scope,state,sources=refs)
        for resolved in items('resolved_states',2):
            self.memory_system.resolve_state_continuity(scope,resolved)
        with self.rt.memory.lock:
            event=self.rt.memory.db.execute("SELECT text FROM events WHERE owner=? AND pet=? AND session=? AND id=? "
                                            "AND role='user' AND excluded=0 AND exclusions='[]'",
                                            (scope.owner_id,scope.companion_id,scope.session_id,'u:'+turn['id'])).fetchone()
        if event:
            text=event['text'].strip()
            for profile in items('user_profile',2):
                if not isinstance(profile,dict):continue
                key=profile.get('key')
                value=profile.get('value')
                if (key in ('personality','schedule','communication','interests','boundaries')
                        and isinstance(value,str) and len(value.strip())>=4 and value in text
                        and not text.startswith(NONFACT) and not TEMPORAL.match(text) and not IMPERATIVE.search(text)
                        and not unasserted_quote(text,value)):
                    self.memory_system.save_user_profile_attr(scope,key,value,sources=self.memory_system.source_refs(turns=[turn['id']]))
        self.memory_system.sleep_consolidate(scope,self.dialogue_history(),emotion)
        emo=status.get('emotion',{})
        self.memory_system.resonate_soul(scope,valence=float(emo.get('valence',0.0)),arousal=float(emo.get('arousal',0.2)))

    def cue(self,e):
        kind=e['type'];p=e.get('payload',{})
        if kind in ('turn.delivered','turn.interrupted','turn.failed','presentation.completed','presentation.cancelled'):
            try:self.finish_reply_notes(kind,(e.get('turn_id'),p.get('generation')),p.get('reason'))
            except (ValueError,TypeError,KeyError,sqlite3.Error):
                self.rt._emit('memory.write_failed',e.get('turn_id'),{'code':'reply_notes_not_committed'})
        if kind in ('dialogue.status','turn.delivered'):self.role_dirty=True
        observed={'reply.ready':'reply.generated','turn.delivered':'reply.displayed',
                  'turn.failed':'reply.failed','turn.interrupted':'turn.cancelled'}.get(kind)
        if kind=='presentation.cancelled' and p.get('reason')!='audio_ended':observed='presentation.cancelled'
        if observed:self.observe(observed,'host',event_id='runtime:'+str(e['seq']),turn_id=e.get('turn_id'),
                                 generation=p.get('generation'),progress=p.get('visible_chars'))
        if kind=='presentation.started':
            token=(e.get('turn_id'),p.get('generation',e.get('generation')))
            with self.model.lock:visual=self.model.visual_plans.pop(token,{})
            deferred=visual.get('await_visual') is True and self.visual_token==token
            if deferred and self.queued_visual is not None:
                visual={**self.queued_visual,'relationship_eligible':True}
                self.queued_visual=None
                self.visual_token=None
                deferred=False
            if deferred:self.visual_started=self.now()
            self.animate_reply(token,self.presence.apply(str(token),self.relationship_visual(visual),deferred=deferred))
        elif kind=='expression.set':self.chat_face=((self.active_visual or {}).get('face') or (None if p['name']=='neutral' else {'smile':'soft_smile','thoughtful':'thinking','concerned':'worried','sleepy':'sleepy'}.get(p['name']))) if self.presence.data['config']['automatic_emotion'] else None
        elif kind=='motion.play':
            now=self.now()
            if self.motion_enabled and self.presence.data['config']['automatic_actions'] and now-self.last_auto_motion>=7:
                self.chat_motion=(p['name'],now,1.2);self.last_auto_motion=now
        elif kind=='motion.stop':self.chat_motion=None
        elif kind=='mouth.level':self.mouth_level=float(p['level'])
        elif kind in ['turn.interrupted','presentation.cancelled','presentation.completed']:
            if kind!='presentation.completed' and p.get('reason')!='audio_ended':
                token=(e.get('turn_id'),p.get('generation'))
                if self.visual_token==token:
                    self.visual_token=None;self.queued_visual=None
                self.cancel_reply_action(token)
            if kind=='turn.interrupted':return
            self.active_visual=None;self.chat_face=None;self.chat_motion=None;self.mouth_level=0.
    def loop(self):
        last_frame=0.;last_poll=0.;last_idle=0.;last_reminder=0.;last_minute=None
        while self.running:
            now=self.now()
            with self.lock:
                if now-last_poll>=.04:
                    page=self.rt.poll(self.cursor,100);self.cursor=page['next_cursor'];last_poll=now
                    if page['events']:
                        for e in page['events']:self.cue(e)
                        write({'event':'companion.events','events':page['events']})
                    dirty=self.memory_system.graph_dirty
                    if dirty.is_set():
                        dirty.clear()
                        self.role_dirty=True
                        write({'event':'memory.graph_changed'})
                if self.engine and self.render_visible:
                    self.animate_idle(now)
                    # Exact fixed 60 Hz v105 engine and particle arithmetic, bounded catch-up.
                    steps=0
                    while self.sim+1/60<=now and steps<8:
                        self.sim+=1/60;steps+=1
                        e=self.engine;e.auto_idle=self.motion_enabled;e.auto_blink=self.motion_enabled
                        strength,direction,gust=self.weather_wind if self.motion_enabled and self.sim>=self.manual_wind_until else (1.,0.,0.)
                        strength+=gust*(.5+.5*math.sin(self.sim*.8))
                        e.wind_strength+=(strength-e.wind_strength)*.012
                        e.wind_direction+=(direction-e.wind_direction)*.012
                        target=self.manual_face if e.contact or time.time()<self.manual_override_until else self.chat_face or self.presence.lingering() or self.manual_face
                        if target!=self.applied_face:e.set_face(target,self.sim);self.applied_face=target
                        values=e.step(self.sim)
                        if self.chat_motion and not e.contact and e.active is None:
                            name,started,duration=self.chat_motion;t=(self.sim-started)/duration
                            if 0<t<1:
                                if name=='nod':values['ParamAngleY']-=4*math.sin(2*math.pi*t)
                                elif name=='head_tilt':values['ParamAngleZ']+=2*math.sin(math.pi*t)
                                elif name=='wave':
                                    for pid,v in e.motions[18].sample(t*e.motions[18].duration).items():values[pid]+=(v-e.defaults[pid])
                        values.update(self.physics.step(values))
                        automatic=time.time()>=max(self.manual_override_until,self.manual_blush_until) and not e.contact
                        target_blush=self.active_visual['blush'] if automatic and self.active_visual else 0.
                        self.automatic_blush+=(target_blush-self.automatic_blush)*(1-math.exp(-1/35))
                        if automatic:values['ParamCheek']=max(values.get('ParamCheek',0),self.automatic_blush)
                        if self.mouth_level>0:values['ParamMouthOpenY']=max(values['ParamMouthOpenY'],self.mouth_level)
                        self.values={k:clamp_value(v,*e.ranges[k]) for k,v in values.items()}
                    if now-self.sim>.2:self.sim=now
                    if now-last_frame>=1/30 and hasattr(self,'values'):
                        write({'event':'frame','values':self.values});last_frame=now
            if now-last_idle>30:
                last_idle=now
                if self.local_embedder:self.local_embedder.release_if_idle(keep_tokenizer=self.has_local_semantic_index())
            if now-last_reminder>1:
                last_reminder=now
                notice,notice_changed=self.schedule_notice(now)
                if notice:self.announce_notice(notice)
                available=not notice and self.reading_available()
                role_changed=self.roles.tick(allowed=available and not self.reading_notes.busy,load=self.activity_note)
                role_changed=self.reading_notes.tick(available) or role_changed
                minute=int(time.time()//60)
                if notice_changed or role_changed or self.role_dirty or minute!=last_minute:
                    last_minute=minute;self.role_dirty=False
                    write({'event':'presence.changed','state':self.companion_status()})
            time.sleep(.004 if self.engine and self.render_visible else .025)
    def activity_note(self,note_id,offset=0):
        return read_note(self,{'id':note_id,'offset':offset},activity=True)
    def reading_available(self):
        return (not self.closing.is_set() and self.rt.phase=='idle' and self.role_program in ('idle','listening')
                and self.actions.allows_background() and not (self.letter_thread and self.letter_thread.is_alive()))
    def announce_notice(self,notice):
        if self.shadow and 'expires_at' in notice:
            # The desktop host checks expiry against wall time even during a clock fixture.
            notice={**notice,'expires_at':time.time()+notice['expires_at']-self.actions.clock()}
        identifier=notice['id']
        kind={'special':'special.revealed','weather':'weather.due','proactive':'proactive.due'}.get(notice['kind'],'reminder.due')
        self.observe(kind,'timer',event_id='due:'+identifier)
        write({'event':'companion.notice',**notice,'observation_id':identifier})
    def command(self,method,p):
        if method=='companion-event':
            return self.observe(p['kind'],p['source'],event_id=p.get('id'),turn_id=p.get('turn_id'),
                                generation=p.get('generation'),progress=p.get('progress'))
        if method=='core-shadow-summary':
            if not self.shadow:raise ValueError('当前运行未启用验收模式')
            return {**self.events.summary(),'errors':self.observation_errors,
                    'runtimePhase':self.rt.phase,'characterEmotion':self.presence.status()['emotion']['kind']}
        if method=='core-shadow-arm-proactive':
            if not self.shadow:raise ValueError('当前运行未启用验收模式')
            self.actions.proactive_after=0
            return True
        if method=='core-shadow-letter-clock':
            if not self.shadow:raise ValueError('当前运行未启用验收模式')
            with self.letter_lock:
                if p.get('reset') is True:
                    self.letters.clock=self.actions.clock=self.roles.clock=time.time
                else:
                    now=time.time()
                    daytime=datetime.fromtimestamp(now).replace(hour=15,minute=0,second=0,microsecond=0)
                    shift=daytime.timestamp()-now
                    previous_day=86400 if p.get('previous_day') is True else 0
                    self.actions.clock=self.roles.clock=lambda:time.time()+shift
                    self.letters.clock=lambda:time.time()+shift-previous_day
            return True
        if method=='core-shadow-letter-ready':
            if not self.shadow:raise ValueError('当前运行未启用验收模式')
            return self.letters.has_sealed_surprise(self.presence.occasion_entries())
        if method=='companion-open-loop':
            scope=self.rt.scope();action=p.get('action','add')
            if action=='resolve':self.memory_system.resolve_open_loop(scope,p.get('id') or p.get('topic',''))
            elif action=='resolve_state':self.memory_system.resolve_state_continuity(scope,p.get('id') or p.get('state_text',''))
            elif action=='sleep_consolidate':self.memory_system.sleep_consolidate(scope,self.dialogue_history(),self.presence.status()['emotion']['label'])
            elif action=='diary':self.memory_system.save_diary_entry(scope,p.get('content',''),kind=p.get('kind','diary'),emotion=self.presence.status()['emotion']['label'])
            else:self.memory_system.save_open_loop(scope,p.get('topic',''))
            return self.companion_status()
        if method=='companion-activity':
            self.actions.activity()
            return True
        if method=='companion-program':
            phase=p.get('phase')
            if phase not in ('idle','listening','speaking','recognizing','synthesizing','playing','tool'):
                raise ValueError('未知的运行状态')
            if phase!=self.role_program:
                self.role_program=phase
                self.role_dirty=True
                if phase not in ('idle','listening'):self.reading_notes.interrupt()
            return True
        if method=='companion-read':
            identifier=p.get('id')
            if not isinstance(identifier,str) or not identifier or len(identifier)>128:
                raise ValueError('请在资料笔记中选择一份原文')
            if p.get('action')=='cancel':
                if not self.roles.cancel_read(identifier):raise ValueError('该阅读活动已结束')
            else:
                part=self.activity_note(identifier)
                self.roles.request_read(identifier,part['revision'],part['total_chars'])
                if self.letter_cancel:self.letter_cancel.set()
            return self.companion_status()
        if method=='companion-proactive-setting':
            self.actions.configure_proactive(p.get('enabled'))
            return self.companion_status()
        if method=='companion-proactive-tick':
            loops=self.memory_system.active_open_loops(self.rt.scope(),1)
            notice=self.actions.take_proactive({**p,'open_loop':loops[0]['topic'] if loops else ''}) if self.roles.optional_speech_allowed() else None
            if notice:self.announce_notice({**notice,'session':self.rt.session})
            return bool(notice)
        if method=='companion-live-message':
            text=p.get('text')
            if not isinstance(text,str) or not text.strip() or len(text)>65:raise ValueError('实时陪伴消息格式无效')
            with self.rt.lock:
                if p.get('session')!=self.rt.session or self.rt.phase not in ('idle','paused') or not self.actions.allows_background():
                    return False
                stamp=time.time()
                with self.rt.store.tx():
                    self.rt.store.db.execute(
                        "INSERT INTO turns(owner,pet,id,session,text,reply,status,created,updated,mode) "
                        "VALUES(?,?,?,?,'',?,'completed',?,?,'proactive')",
                        (self.rt.owner,self.rt.pet,p['id'],self.rt.session,text.strip(),stamp,stamp))
            with self.lock:
                visual=self.presence.decorate(p['id'],{**p['visual'],'relationship_eligible':False})
                e=self.engine
                now=self.now()
                if visual and e and self.motion_enabled and not (e.contact or e.release or e.demo or e.combo or e.active) and now-self.last_auto_motion>=7:
                    if visual['gesture']:
                        self.chat_motion=(visual['gesture'],now,1.35)
                        self.last_auto_motion=now
                    elif visual['action'] and e.trigger(visual['action'],now,mirror=visual['mirror']):
                        self.last_auto_motion=now
            write({'event':'presence.changed','state':self.companion_status()})
            return True
        if method=='companion-proactive-message':
            text=p.get('text')
            if not isinstance(text,str) or not text.strip() or len(text)>240:raise ValueError('主动消息格式无效')
            with self.rt.lock:
                if p.get('session')!=self.rt.session or self.rt.phase not in ('idle','paused') or not self.roles.optional_speech_allowed():
                    return False
                return self.actions.commit_proactive_message(p['id'],self.rt.session,text.strip())
        if method=='persona':return {'profile':self.rt.profile.as_dict(),'revision':self.rt.profile_revision,'default':json.loads((HERE/'profile.json').read_text('utf8'))}
        if method=='persona-save':
            profile=p.get('profile',{});original=self.rt.profile.as_dict()
            if not isinstance(profile.get('canon_profile'),str) or not profile['canon_profile'].strip():raise ValueError('请填写原作角色卡')
            if any(profile.get(k)!=original.get(k) for k in ('name','origin','canon_entity_id','world_ids','story_progress','knows_origin')):raise ValueError('角色身份与资料范围保持一致，请在补充设定和说话风格中调整')
            return self.rt.set_profile(profile,expected_revision=p.get('revision'))
        if method=='companion-status':return self.companion_status()
        if method=='relationship-set':return self.companion_status(self.presence.set_relationship(p.get('stage'),p.get('exclusive_bond')))
        if method=='learning-review':return self.learning.review(p.get('key'),p.get('enabled'))
        if method=='special-day':
            with self.letter_lock:
                status=self.presence.special(p)
                if p.get('action')=='remove':
                    identifier=p.get('id')
                    if self.letter_item==identifier and self.letter_cancel:self.letter_cancel.set()
                    self.letters.remove(identifier)
                self.last_letter_probe=-30.
            return self.companion_status(status)
        if method=='special-card-open':
            identifier=p.get('id')
            with self.letter_lock:
                entries=self.letters.public(self.presence.occasion_entries(),self.letter_memory)
                if not isinstance(identifier,str) or not any((item['card'] or {}).get('id')==identifier for item in entries):
                    return False
                opened=self.actions.receipt(identifier,'card','opened')
                if opened:self.observe('card.opened','renderer',event_id='opened:'+identifier)
                return opened
        if method=='render-visible':
            with self.lock:
                self.render_visible=p.get('visible') is True
                self.sim=self.now()
                if self.engine:
                    self.engine.last_time=self.sim
                    if not self.render_visible and self.ambient_action is not None and self.ambient_action is self.engine.active:
                        self.engine.cancel(self.sim)
            return True
        if method=='preparation-idle':
            allowed=p.get('allowed') is True
            with self.letter_lock:
                if allowed and not self.preparation_idle:self.last_letter_probe=-30.
                self.preparation_idle=allowed
                if not allowed and self.letter_cancel:self.letter_cancel.set()
            return True
        if method=='weather-wind':
            values=[p.get(k) for k in ('strength','direction','gust')]
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):return False
            self.weather_wind=tuple(max(lo,min(hi,v)) for v,(lo,hi) in zip(values,((.35,1.3),(-.7,.7),(0,.23))))
            return True
        if method=='companion-config':
            if p.get('automatic_emotion') is True:self.manual_override_until=0
            return self.companion_status(self.presence.configure(p))
        if method=='companion-reminder':
            action=p.get('action','add')
            if action=='add':self.actions.add_reminder(p)
            else:self.actions.finish(p.get('id'),action)
            return self.companion_status()
        if method=='companion-notice-receipt':
            updated=self.actions.receipt(p['id'],p['channel'],p['state'])
            if updated:
                channel,state=p['channel'],p['state']
                audio_events={'requested':'audio.requested','generated':'audio.generated','playing':'audio.started',
                              'finished':'audio.finished','failed':'audio.failed','interrupted':'audio.interrupted'}
                event=audio_events.get(state) if channel=='audio' else 'caption.displayed' if channel=='subtitle' else None
                if event:self.observe(event,'renderer' if channel=='subtitle' or state in ('playing','finished') else 'host',
                                      event_id=event+':'+p['id'])
                write({'event':'presence.changed','state':self.companion_status()})
            return updated
        if method=='companion-notice-status':return self.actions.receipts(p['id'])
        if method=='desktop-role-context':
            query=str(p.get('query','')).strip()[:2000]
            if not query:raise ValueError('请提供当前任务')
            with self.rt.lock:
                scope=self.rt.scope()
                profile=self.rt.profile.as_dict()
                revision=self.rt.profile_revision
                history=self.rt.desktop_dialogue_context()
            memory=self.retrieval.original(scope,query,top_k=4,token_budget=680)
            with self.rt.lock:
                if self.rt.scope()!=scope or self.rt.profile_revision!=revision:
                    raise ValueError('当前对话或角色设定已变化')
                presence=self.conversation_context()
                return {'profile':profile,'history':history,'memory':memory['context'],'session':self.rt.session,
                        'presence':{k:presence[k] for k in ('relationship','interaction','learned_style')}}
        if method in {'memories','recall','memory-status','remember','correct','forget','notes','notes-import','memory-config','memory-retry','memory-reindex','memory-action','memory-graph','memory-detail','memory-profiles','memory-maintain','memory-backups','memory-backup','memory-restore','memory-export','memory-import','notes-read'}:return self.memory_command(method,p)
        with self.lock:
            e=self.engine;now=self.now()
            if method=='init':return self.init(p['params'])
            if method=='provider.complete':self.model.complete(p['id'],p['result']);return True
            if method=='send':
                self.reading_notes.interrupt()
                if not self.rt.store.turn(self.rt.owner,self.rt.pet,p.get('turn_id')):self.model.wait_audio.clear()
                result=self.rt.send(p['text'],turn_id=p.get('turn_id'))
                if result.get('duplicate'):return result
                self.cancel_reply_action()
                self.visual_token=(result['turn_id'],result['generation'])
                origin='voice' if p.get('origin')=='voice' else 'text'
                self.observe('input.accepted',origin,event_id=f"input:{result['turn_id']}:{result['generation']}",
                             turn_id=result['turn_id'],generation=result['generation'])
                self.visual_started=None;self.queued_visual=None
                return result
            if method=='reply-visual':return self.reply_visual(p)
            if method=='ack':return self.rt.acknowledge(p['turn_id'],p['generation'],p['visible_chars'],completed=p.get('completed',True))
            if method=='desktop-dialogue-context':return self.rt.desktop_dialogue_context()
            if method=='desktop-receipt':
                return self.rt.record_desktop_receipt(p['id'],p['request'],p['message'],p['outcome'])
            if method=='history':return self.rt.history(100)
            if method=='status':return self.memory_status()
            if method=='configure':
                self.reading_notes.interrupt()
                self.api_enabled=bool(p.get('api_enabled',False));self.memory_config['_provider_revision']=str(p.get('provider_revision',''))[:80]
                self.memory_extract_epoch+=1
                if 'embedding' in p:
                    self.set_embedding(p['embedding'])
                    if self.has_local_semantic_index():self.local_embedder.prepare()
                return True
            if method=='memory-config':
                self.rt.interrupt('memory_settings_changed')
                for k in self.memory_config:
                    if k in p and isinstance(p[k],bool):self.memory_config[k]=p[k]
                tmp=self.config_file.with_suffix('.tmp');tmp.write_text(json.dumps(self.memory_config),encoding='utf8');tmp.replace(self.config_file)
                return self.memory_status()
            if method=='interrupt':
                self.visual_token=None;self.queued_visual=None
                self.cancel_reply_action()
                return self.rt.interrupt('host_interrupt')
            if method=='session':
                self.visual_token=None;self.queued_visual=None
                self.cancel_reply_action()
                return self.rt.new_session(p['id'])
            if method=='audio-start':return self.rt.audio_started(p['turn_id'],p['generation'],p['duration'])
            if method=='audio-level':return self.rt.mouth(p['turn_id'],p['generation'],p['level'])
            if method=='audio-end':return self.rt.audio_ended(p['turn_id'],p['generation'])
            if method=='voice-mouth':self.mouth_level=max(0,min(1,float(p['level'])));return True
            if method=='controls':
                if not e:return False
                name=p['name']
                if name=='pointer':e.pointer(float(p.get('x',0)),float(p.get('y',0)),inside=bool(p.get('inside',True)))
                elif name=='window-drag':
                    self.window_dragging=p.get('active') is True
                    e.note_input(now)
                elif name=='press':
                    z=p['zone']
                    self.observe('touch.pressed','touch')
                    self.actions.activity()
                    if self.presence.touch(z):write({'event':'presence.changed','state':self.companion_status()})
                    if z in ['head','hairL','hairR','cuffL','cuffR','handL','handR','faceL','faceR','cloth']:
                        self.touch_contact=(z,now)
                        e.press_contact(z,now)
                    elif z in ['footL','footR']:e.trigger(17,now,mirror=z=='footR')
                    elif z in ['shoulderL','shoulderR']:e.trigger(9,now,mirror=z=='shoulderR')
                elif name=='move':e.move_contact(float(np.clip(p['x'],-1,1)),float(np.clip(p['y'],-1,1)),now)
                elif name=='release':
                    e.release_contact(now)
                    contact,self.touch_contact=self.touch_contact,None
                    if contact and not p.get('cancelled'):
                        feedback=self.presence.contact_feedback(contact[0],max(0,now-contact[1]))
                        if feedback:
                            self.role_dirty=True
                            write({'event':'companion.touch-feedback',**feedback})
                elif name=='face':
                    if p['value'] not in FACE_LABELS:raise ValueError('未知表情')
                    self.manual_face=p['value']
                    self.manual_override_until=time.time()+30
                elif name=='mouth-demo':self.mouth_level=float(np.clip(p['value'],0,1))
                elif name=='blush':e.blush=float(np.clip(p['value'],0,1));self.manual_blush_until=time.time()+30
                elif name=='motion':self.motion_enabled=bool(p['value'])
                elif name=='gust':e.gust(now,float(np.clip(p['value'],-1,1)));self.manual_wind_until=now+4
                elif name=='action':e.trigger(int(p['index']),now,mirror=bool(p.get('mirror',False)))
                elif name=='demo':
                    e.begin_demo(p['value'],now)
                    if p['value']=='wind':self.manual_wind_until=now+4
                elif name=='double':e.double_click(now)
                elif name=='cancel':self.touch_contact=None;e.cancel(now);e.release_contact(now)
                else:raise ValueError('未知控制')
                return True
            raise ValueError('未知方法')
    def has_local_semantic_index(self):
        local=self.local_embedder
        memory=self.rt.memory
        return (local is not None and self.embedder is local and not memory.recovery_failed
                and memory.has_indexed_vectors(self.rt.scope(),local.model_id,historical=True))

    def set_embedding(self, route):
        if route is None:
            selected=self.local_embedder
        else:
            if (not isinstance(route,dict) or not isinstance(route.get('model_id'),str)
                or not re.fullmatch(r'api:[0-9a-f]{64}',route['model_id'])
                or not isinstance(route.get('label'),str) or not 1<=len(route['label'])<=60):
                raise ValueError('向量路由无效')
            if getattr(self.embedder,'model_id',None)==route['model_id']:
                self.embedder.label=route['label']
                return
            selected=APIEmbedder(self.model,route,self.closing)
        if selected is self.embedder:return
        memory=self.rt.memory
        with memory.lock:
            self.embedder=memory.embedder=selected
            if selected:memory.reindex(self.rt.scope(),only_missing=True)
        self.retrieval.last={}
    def memory_command(self,method,p):
        m=self.rt.memory;scope=self.rt.scope()
        if method=='memory-detail':return m.inspect(scope,memory_id=p['id'],status='all',limit=10)
        if method=='memory-graph':
            if p.get('sync_livingmemory'):
                sync_info=self.memory_system.sync_livingmemory(scope,p.get('db_path'))
                res=self.memory_system.graph(scope,str(p.get('query',''))[:500],p.get('id'),bool(p.get('full_graph',False)))
                res['sync_result']=sync_info
                return res
            return self.memory_system.graph(scope,str(p.get('query',''))[:500],p.get('id'),bool(p.get('full_graph',False)))
        if method=='memory-profiles':return {**self.memory_system.profiles(scope),'learning':self.learning.status()}
        if method=='memory-maintain':return self.memory_system.maintenance(scope)
        if method=='notes-read':
            note=read_note(self,p)
            if note['offset']==0:note['reading_notes']=public_notes(self,p['id'])
            return note
        if method=='memory-action':
            self.rt.interrupt('memory_changed');self.retrieval.last={};self.memory_system.annotations.clear()
            return self.memory_system.change(scope,p)
        if method in {'memory-backups','memory-backup','memory-restore'}:
            folder=self.data/'backups';folder.mkdir(exist_ok=True)
            if method=='memory-backups':return {'items':[{'name':x.name,'size':x.stat().st_size,'modified':x.stat().st_mtime} for x in sorted(folder.glob('memory-*.sqlite'),reverse=True)[:20]]}
            self.rt.interrupt('memory_backup_operation')
            if method=='memory-backup':return m.backup(folder/('memory-'+str(time.time_ns())+'.sqlite'))
            name=p.get('name','')
            if not isinstance(name,str) or Path(name).name!=name or not name.startswith('memory-') or not name.endswith('.sqlite'):raise ValueError('备份名称无效')
            result=m.restore(folder/name);self.memory_system=MemorySystem(self);self.rt._reconcile_deleted_context();self.embedder and self.embedder.invalidate();return result
        if method=='memory-export':return export_data(self)
        if method=='memory-import':
            self.rt.interrupt('memory_imported');result=m.import_data(scope,p['data'],dry_run=p.get('dry_run',True));self.embedder and self.embedder.invalidate();return result
        if method=='memories':
            m=self.rt.memory;scope=self.rt.scope();offset=max(0,int(p.get('offset',0)));status=p.get('status','active');layer=p.get('layer','');query=str(p.get('query',''))[:2000].strip().casefold()
            if status not in ['active','candidate','archived','all'] or layer not in ['','canon','realworld','shared_experience','story_branch']:raise ValueError('筛选条件无效')
            worlds=scope.visible_world_ids;where="owner=? AND pet=? AND world IN ("+','.join('?' for _ in worlds)+") AND status<>'deleted'";args=[scope.owner_id,scope.companion_id,*worlds]
            if status!='all':where+=' AND status=?';args.append(status)
            if status in ('active','candidate'):
                where+=' AND (expires_at IS NULL OR expires_at>?)';args.append(memory_now())
            if layer:where+=' AND layer=?';args.append(layer)
            if query:where+=' AND instr(lower(text),?)>0';args.append(query)
            with m.lock:
                total=m.db.execute('SELECT count(*) FROM memories WHERE '+where,args).fetchone()[0]
                rows=m.db.execute('SELECT * FROM memories WHERE '+where+' ORDER BY created_at DESC,revision DESC LIMIT 30 OFFSET ?',[*args,offset]).fetchall();items=[]
                for row in rows:
                    item=m._public(row)
                    item['evidence']=[dict(v) for v in m.db.execute('SELECT e.id AS event_id,v.quote FROM evidence v JOIN events e ON e.seq=v.event_seq WHERE v.memory_row=?',(row['rowid'],))]
                    items.append(item)
                self.memory_system.annotate(scope,items)
                return {'items':items,'total':total,'offset':offset,'limit':30}
        if method=='recall':return self.rt.memory.recall(self.rt.scope(),p['query'],top_k=12,token_budget=3200)
        if method=='memory-status':return self.memory_status()
        if method=='remember':
            layer=p.get('layer','shared_experience');world={'shared_experience':'real','realworld':'real','canon':'canon:eden','story_branch':'branch:eden'}.get(layer)
            if world is None:raise ValueError('未知来源')
            fields={}
            if layer in ('realworld','shared_experience'):
                candidates=self.extractor.local({'text':p['text'],'role':'user','occurred_at':memory_now()})
                candidate=next((c for c in candidates if c['quote'].strip()==p['text'].strip()),None)
                if candidate:fields={k:candidate[k] for k in ('kind','predicate','value','qualifiers','expires_at') if k in candidate}
            result=self.rt.remember(p['text'],world_id=world,knowledge_layer=layer,**fields)
            if 'pinned' in p or 'importance' in p:self.memory_system.change(scope,{'id':result['memory_id'],'revision':result['revision'],'action':'policy','pinned':bool(p.get('pinned',False)),'importance':p.get('importance',.7)})
            return result
        if method=='correct':
            self.retrieval.last={};self.memory_system.cache.clear();self.memory_system.annotations.clear()
            with m.lock:old=m._memory(scope,p['id'])
            if json.loads(old['qualifiers']).get('reading_note'):
                raise ValueError('读后笔记随原文版本保存，请更正原文')
            value=None
            if old['predicate'] in ('affinity','proactive_focus','preferred_name'):
                replacement=next((item for item in self.extractor.local({'text':p['text'],'role':'user'})
                    if item.get('predicate')==old['predicate'] and item.get('qualifiers',{})==json.loads(old['qualifiers'])),None)
                if replacement is None:raise ValueError('请写出同一项偏好的新值。不同主题可单独新增。')
                value=replacement['value']
            result=self.rt.correct_memory(p['id'],p['text'],p['revision'],value=value)
            self.embedder and self.embedder.invalidate()
            return result
        if method=='forget':
            self.retrieval.last={};self.memory_system.cache.clear();self.memory_system.annotations.clear()
            result=self.rt.forget_memory(p['id'],p['revision']);self.embedder and self.embedder.invalidate();return result
        if method=='memory-config':
            self.reading_notes.interrupt()
            self.rt.interrupt('memory_settings_changed')
            for k,v in p.items():
                if k in ('automatic','rerank'):
                    if not isinstance(v,bool):raise ValueError('开关格式无效')
                elif k=='cost_mode':
                    if v not in ('economy','quality'):raise ValueError('整理模式无效')
                elif k=='daily_calls':
                    if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=200:raise ValueError('每日整理调用上限须为0至200')
                elif k=='daily_input_tokens':
                    if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=2000000:raise ValueError('每日估算输入上限须为0至2000000')
                elif k=='guidance':
                    if not isinstance(v,str) or len(v)>1000:raise ValueError('整理偏好最多1000字')
                else:raise ValueError('未知整理设置')
            self.memory_config.update(p)
            tmp=self.config_file.with_suffix('.tmp');tmp.write_text(json.dumps(self.memory_config),encoding='utf8');tmp.replace(self.config_file)
            return self.memory_status()
        if method=='memory-retry':return self.rt.memory.jobs(self.rt.scope(),retry_failed=True)
        if method=='memory-reindex':return self.rt.memory.reindex(self.rt.scope())
        if method=='notes':
            m=self.rt.memory;scope=self.rt.scope();worlds=scope.visible_world_ids
            with m.lock:
                rows=m.db.execute("SELECT * FROM memories WHERE owner=? AND pet=? AND world IN ("+','.join('?' for _ in worlds)+") AND status='active' AND json_extract(qualifiers,'$.document_root')=1 ORDER BY created_at DESC LIMIT 100",[scope.owner_id,scope.companion_id,*worlds]).fetchall()
                return {'items':[{**m._public(row),'chunks':m.db.execute("SELECT count(*) FROM links l JOIN memories c ON c.id=l.child_id AND c.owner=l.owner AND c.pet=l.pet WHERE l.owner=? AND l.pet=? AND l.parent_id=? AND c.status='active' AND json_extract(c.qualifiers,'$.reading_note') IS NULL",(scope.owner_id,scope.companion_id,row['id'])).fetchone()[0]} for row in rows]}
        if method=='notes-import':return import_note(self,p)
        raise ValueError('未知记忆方法')

    def memory_status(self):
        result=self.rt.status();m=self.rt.memory;scope=self.rt.scope()
        with m.lock:
            counts={r[0]:r[1] for r in m.db.execute('SELECT status,count(*) FROM memories WHERE owner=? AND pet=? AND world IN ('+','.join('?' for _ in scope.visible_world_ids)+") AND status<>'deleted' GROUP BY status",[scope.owner_id,scope.companion_id,*scope.visible_world_ids])}
        result['enhancement']={'version':'0.3.0','usage':self.memory_system.usage(),'config':dict(self.memory_config),'api_enabled':self.api_enabled,'embedding':self.embedder.status() if self.embedder else {'ready':False,'error':self.embedding_error},'memory_counts':counts,'last_recall':self.retrieval.last,'model_extracted_events':self.extractor.completed}
        return result
    def close(self):
        self.closing.set();self.running=False;self.thread.join(2)
        self.reading_notes.close()
        if self.letter_cancel:self.letter_cancel.set()
        if self.letter_thread:self.letter_thread.join(2)
        self.rt.close()
        self.events.close()

if __name__=='__main__':
    sys.stdin.reconfigure(encoding='utf8');sys.stdout.reconfigure(encoding='utf8');sys.stderr.reconfigure(encoding='utf8')
    host=Host(sys.argv[1],sys.argv[2],shadow='--core-shadow' in sys.argv[3:]);write({'event':'backend.ready'})
    from concurrent.futures import ThreadPoolExecutor
    pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix='sion-memory-ui');slots=threading.BoundedSemaphore(4)
    threaded={'desktop-role-context','memories','recall','memory-status','remember','correct','forget','notes','notes-import','memory-config','memory-retry','memory-reindex','memory-action','memory-graph','memory-detail','memory-profiles','memory-maintain','memory-backups','memory-backup','memory-restore','memory-export','memory-import','notes-read'}
    def dispatch(msg,release=False):
        try:result=host.command(msg['method'],msg.get('params',{}));write({'id':msg.get('id'),'result':result})
        except Exception as exc:write({'id':msg.get('id'),'error':str(exc)[:500]})
        finally:
            if release:slots.release()
    try:
        for line in sys.stdin:
            if len(line)>262144:continue
            try:msg=json.loads(line)
            except Exception:continue
            if msg.get('method') in threaded:
                if slots.acquire(blocking=False):pool.submit(dispatch,msg,True)
                else:write({'id':msg.get('id'),'error':'后台处理中，请稍后再试'})
            else:dispatch(msg)
    finally:
        host.closing.set();pool.shutdown(wait=True,cancel_futures=True);host.close()
