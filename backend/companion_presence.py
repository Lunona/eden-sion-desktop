"""Bounded presentation state and explicit local reminders, independent of factual memory."""
from pathlib import Path
from collections import deque
from datetime import date,datetime
import time,json,threading,uuid,math,hashlib,re
from special_days import public_days, sanitize_days, update
from companion_day import day_plan

EMOTIONS={'calm':('平静',0.,.2,'neutral'),'joy':('开心',.7,.65,'happy'),'warm':('温柔',.5,.3,'soft_smile'),'care':('关切',-.2,.3,'worried'),'curious':('好奇',.2,.5,'curious'),'thoughtful':('思考',0.,.35,'thinking'),'shy':('害羞',.3,.5,'shy'),'surprise':('惊讶',.1,.8,'surprised'),'sad':('低落',-.5,.2,'downcast'),'sleepy':('困倦',0.,.1,'sleepy'),'playful':('俏皮',.6,.6,'wink_left')}
RELATIONSHIPS={
    'acquaintance':('初识','友好自然，保留相处空间，称呼用“你”或已确认的称呼。'),
    'familiar':('熟悉','轻松自然，可以接着聊共同经历，使用已确认的称呼。'),
    'close':('亲近','温暖自然，尊重对方当前节奏，使用已确认的称呼。'),
    'intimate':('亲密','表达可以更柔和，继续尊重当前请求与明确边界。'),
    'deeply_bonded':('羁绊','深厚默契与信赖，自然流露牵挂与偏爱，继续尊重当前节奏。'),
    'owner_exclusive':('唯一专属','彼此唯一的专属联结，语气亲昵自然，深刻铭记专属羁绊背景与共同约定。'),
}
RELATIONSHIP_STAGES=(('acquaintance',0),('familiar',200),('close',600),('intimate',900),('deeply_bonded',1100))
RELATIONSHIP_DAILY_CAP=12
RELATIONSHIP_POINTS={'support':4,'shared':3,'promise':3,'care':2}
HEAD_CONTACTS={'head','hairL','hairR','faceL','faceR'}
HAND_CONTACTS={'handL','handR'}
TOUCH_REPLIES={
    'care':('摸得有点久啦，让我缓一会儿，好吗？','ちょっと長かったね。少し休ませてくれる？',.52),
    'shy':('一直这样摸头，我会有点不好意思。','ずっと頭を撫でられると、少し照れるよ。',.63),
    'joy':('这样牵着手，感觉很安心。','こうして手をつないでいると、ほっとするね。',.54),
}

class Presence:
    def __init__(self,data,faces,clock=time.time,*,track_legacy_points=True):
        self.path=Path(data)/'presence.json';self.faces=faces;self.clock=clock;self.lock=threading.RLock();self.seen=[];self.last_touch=0
        self.track_legacy_points=track_legacy_points
        self.recent_head_contacts=deque(maxlen=4)
        self.next_touch_feedback=0
        self.touch_pause_until=0
        self.data={'config':{},'emotion':{'kind':'calm','intensity':0.,'at':0},'events':[],'reminders':[],'days':{},'relationship':{},'learning':{},'special_days':[]}
        self.last_hint=''
        if self.path.exists():
            try:
                saved=json.loads(self.path.read_text('utf8'))
                for key in self.data:
                    if isinstance(saved.get(key),type(self.data[key])):self.data[key]=saved[key]
            except (OSError,ValueError):pass
        defaults={'automatic_emotion':True,'automatic_actions':True,'ambient_actions':True,'afterglow':True}
        self.data['config']={k:self.data['config'].get(k,v) if isinstance(self.data['config'].get(k,v),bool) else v for k,v in defaults.items()}
        emotion=self.data['emotion'];kind=emotion.get('kind','calm');value=emotion.get('intensity',0);at=emotion.get('at',0)
        if kind not in EMOTIONS or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in (value,at)):emotion={'kind':'calm','intensity':0,'at':0}
        self.data['emotion']={'kind':emotion.get('kind','calm'),'intensity':max(0,min(1,emotion.get('intensity',0))),'at':max(0,min(self.clock(),emotion.get('at',0)))}
        self.data['events']=[x for x in self.data['events'] if isinstance(x,dict) and isinstance(x.get('label'),str) and isinstance(x.get('source'),str) and isinstance(x.get('at'),(int,float)) and math.isfinite(x['at'])][-40:]
        self.data['reminders']=[x for x in self.data['reminders'] if isinstance(x,dict) and isinstance(x.get('id'),str) and isinstance(x.get('title'),str) and isinstance(x.get('at'),(int,float)) and math.isfinite(x['at']) and x.get('status') in ('pending','notified','done','overdue')][:80]
        self.data['days']={k:{n:max(0,min(100000,v.get(n,0))) for n in ('replies','touches')} for k,v in self.data['days'].items() if isinstance(k,str) and isinstance(v,dict) and all(isinstance(v.get(n,0),int) and not isinstance(v.get(n,0),bool) for n in ('replies','touches'))}
        self.data['special_days']=sanitize_days(self.data['special_days'])
        relationship=self.data['relationship']
        recent=[day for day,value in self.data['days'].items() if value['replies']>0 and day<=self.day()]
        observed=relationship.get('days',len(recent))
        last=relationship.get('last_day',max(recent,default=''))
        manual=relationship.get('manual')
        # Preserve an already attained familiar stage without awarding points
        # for ordinary historical chat turns.
        score=relationship.get('score',200 if type(observed) is int and observed>=14 else 0)
        score_day=relationship.get('score_day','')
        score_day=score_day if isinstance(score_day,str) and score_day<=self.day() else ''
        positive=relationship.get('positive',0)
        ledger=relationship.get('ledger',[])
        ledger=[item for item in ledger if isinstance(item,dict) and
                all(isinstance(item.get(key),str) for key in ('day','turn','evidence'))][-128:] if isinstance(ledger,list) else []
        self.data['relationship']={
            'days':max(0,min(3650,observed)) if type(observed) is int else len(recent),
            'last_day':last if isinstance(last,str) and last<=self.day() else max(recent,default=''),
            'manual':manual if isinstance(manual,str) and manual in RELATIONSHIPS else None,
            'score':max(0,min(1200,score)) if type(score) is int else 0,
            'score_day':score_day,
            'positive':max(0,min(RELATIONSHIP_DAILY_CAP,positive)) if type(positive) is int else 0,
            'ledger':ledger,
            'exclusive_bond':str(relationship.get('exclusive_bond') or '').strip()[:600] if isinstance(relationship.get('exclusive_bond'),str) else '',
        }
    def day(self):
        return datetime.fromtimestamp(self.clock()).date().isoformat()
    def relationship(self):
        relation=self.data['relationship']
        score=relation['score']
        auto_stage=next(key for key,minimum in reversed(RELATIONSHIP_STAGES) if score>=minimum)
        stage=relation['manual'] or auto_stage
        label,tone=RELATIONSHIPS[stage]
        next_stage=next(((key,minimum) for key,minimum in RELATIONSHIP_STAGES if score<minimum),None)
        return {'stage':stage,'label':label,'tone':tone,'days':relation['days'],'manual':relation['manual'],
                'score':score,'daily_positive':relation['positive'] if relation['score_day']==self.day() else 0,
                'daily_cap':RELATIONSHIP_DAILY_CAP,
                'next_label':RELATIONSHIPS[next_stage[0]][0] if next_stage else None,
                'next_score':next_stage[1] if next_stage else None,
                'exclusive_bond':relation.get('exclusive_bond','')}
    def score_interaction(self,token,event):
        if not isinstance(event,dict) or not isinstance(event.get('kind'),str) or not isinstance(event.get('quote'),str):
            return
        value=RELATIONSHIP_POINTS.get(event['kind'],0)
        evidence=re.sub(r'[\W_]+','',event['quote']).casefold()
        if not value or not 6<=len(event['quote'])<=160 or not evidence:
            return
        relation=self.data['relationship'];day=self.day()
        if day<relation['score_day']:
            return
        key=hashlib.sha256(token.encode()).hexdigest()
        proof=hashlib.sha256(evidence.encode()).hexdigest()
        if any(item['turn']==key or item['day']==day and item['evidence']==proof for item in relation['ledger']):
            return
        today=relation['positive'] if day==relation['score_day'] else 0
        gain=min(value,RELATIONSHIP_DAILY_CAP-today,1200-relation['score'])
        if gain<=0:
            return
        relation.update(score=relation['score']+gain,score_day=day,positive=today+gain)
        relation['ledger']=(relation['ledger']+[{'day':day,'turn':key,'evidence':proof}])[-128:]
    def set_relationship(self,stage,exclusive_bond=None):
        if not isinstance(stage,str) or stage not in (*RELATIONSHIPS,'auto'):
            raise ValueError('请选择关系阶段')
        with self.lock:
            self.data['relationship']['manual']=None if stage=='auto' else stage
            if isinstance(exclusive_bond,str):
                self.data['relationship']['exclusive_bond']=exclusive_bond.strip()[:600]
            self.save()
            return self.status()
    def save(self):
        self.data['events']=self.data['events'][-40:];self.data['days']=dict(sorted(self.data['days'].items())[-60:]);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.data,ensure_ascii=False),'utf8');temp.replace(self.path)
    def count(self,kind):
        day=datetime.fromtimestamp(self.clock()).date().isoformat();entry=self.data['days'].setdefault(day,{'replies':0,'touches':0});entry[kind]+=1
    def add_event(self,label,source):self.data['events'].append({'id':uuid.uuid4().hex,'label':label,'source':source,'at':self.clock()})
    def apply(self,token,visual,*,deferred=False):
        with self.lock:
            if token in self.seen:return None
            self.seen=(self.seen+[token])[-128:];self.count('replies')
            relation=self.data['relationship']
            if visual.get('relationship_eligible') is True and self.day()>relation['last_day']:
                relation['days']=min(3650,relation['days']+1)
                relation['last_day']=self.day()
            if deferred:
                self.save()
                return None
            return self._apply_visual(token,visual)
    def decorate(self,token,visual):
        with self.lock:
            return self._apply_visual(token,visual)
    def _apply_visual(self,token,visual):
        if self.track_legacy_points and visual.get('relationship_eligible') is True:
            self.score_interaction(token,visual.get('relationship_event'))
        kind=visual.get('emotion','calm');kind=kind if kind in EMOTIONS else 'calm';intensity=visual.get('intensity',.45)
        if not isinstance(intensity,(int,float)) or isinstance(intensity,bool) or not math.isfinite(intensity):intensity=.45
        intensity=max(.1,min(.85,intensity))
        hint=kind in ('calm','warm','curious') and self.last_hint!=self.day() and visual.get('surprise_hint') is True and hashlib.sha256(token.encode()).digest()[0]<52
        if hint:self.last_hint=self.day();kind='shy';intensity=.48
        if self.data['config']['automatic_emotion']:
            self.data['emotion']={'kind':kind,'intensity':intensity,'at':self.clock()};self.add_event('交谈时显得'+EMOTIONS[kind][0],'dialogue')
        self.save()
        face='shy' if hint else visual.get('face');face=face if face in self.faces else EMOTIONS[kind][3]
        action=visual.get('action',0)
        enabled=self.data['config']['automatic_actions']
        action=action if enabled and type(action) is int and 0<=action<=18 else 0
        gesture=None
        if hint and enabled and not action:gesture='head_tilt'
        if enabled and not action and intensity>=.48:
            gesture=gesture or {'curious':'head_tilt','thoughtful':'head_tilt','surprise':'head_tilt',
                     'care':'nod','warm':'nod','joy':'nod'}.get(kind)
            if kind=='shy' and intensity>=.62:action=8
            if kind in ('joy','playful') and intensity>=.7 and visual.get('familiar') is True:action=18
        blush={'shy':.48,'warm':.12,'joy':.16,'playful':.14}.get(kind,0)*intensity
        return {'face':face if self.data['config']['automatic_emotion'] else None,
                'action':action,'gesture':gesture,
                'mirror':visual.get('side')=='right' or visual.get('side','auto')=='auto' and self.data['days'].get(self.day(),{}).get('replies',0)%2==0,
                'blush':blush if self.data['config']['automatic_emotion'] else 0}
    def touch(self,zone):
        with self.lock:
            if self.clock()-self.last_touch<12:return False
            self.last_touch=self.clock();self.count('touches');label={'head':'摸摸头','handL':'牵左手','handR':'牵右手','hairL':'理一理头发','hairR':'理一理头发'}.get(zone,'轻轻互动')
            self.add_event(label,'touch')
            if self.data['config']['automatic_emotion'] and self.clock()>=self.touch_pause_until:
                self.data['emotion']={'kind':'warm','intensity':.4,'at':self.clock()}
            self.save();return True
    def contact_feedback(self,zone,duration):
        with self.lock:
            now=self.clock()
            if not self.data['config']['automatic_emotion'] or now<self.touch_pause_until:
                return None
            head=zone in HEAD_CONTACTS
            if head:
                while self.recent_head_contacts and now-self.recent_head_contacts[0]>15:
                    self.recent_head_contacts.popleft()
                self.recent_head_contacts.append(now)
            if head and (duration>=5 or len(self.recent_head_contacts)>=4):
                kind='care'
                self.recent_head_contacts.clear()
                self.touch_pause_until=now+35
            elif now>=self.next_touch_feedback and duration>=1.8 and (head or zone in HAND_CONTACTS):
                kind='shy' if head else 'joy'
            else:
                return None
            text,japanese,intensity=TOUCH_REPLIES[kind]
            self.next_touch_feedback=now+25
            self.data['emotion']={'kind':kind,'intensity':intensity,'at':now}
            self.add_event({'care':'想歇一下','shy':'摸头时有点害羞','joy':'牵手时很开心'}[kind],'touch_feedback')
            self.save()
            return {'text':text,'japanese':japanese,'emotion':kind,'intensity':intensity}
    def lingering(self):
        with self.lock:
            e=self.data['emotion'];age=max(0,self.clock()-float(e.get('at',0)));intensity=float(e.get('intensity',0))*math.exp(-age/22)
            if not self.data['config']['automatic_emotion'] or not self.data['config']['afterglow'] or age>55 or intensity<.1:return None
            kind=e.get('kind','calm');return EMOTIONS.get(kind,EMOTIONS['calm'])[3]
    def status(self):
        with self.lock:
            e=self.data['emotion'];age=max(0,self.clock()-float(e.get('at',0)));level=float(e.get('intensity',0))*math.exp(-age/22);kind=e.get('kind','calm') if level>.1 else 'calm';kind=kind if kind in EMOTIONS else 'calm';label,valence,arousal,face=EMOTIONS[kind]
            day=self.day();days=self.data['days'];relationship=self.relationship()
            return {'config':dict(self.data['config']),'emotion':{'kind':kind,'label':label,'intensity':round(level,3),'valence':valence,'arousal':arousal,'face':face},'today':dict(days.get(day,{'replies':0,'touches':0})),'relationship':relationship,'familiarity':min(100,round(relationship['score']/2)),'events':list(reversed(self.data['events'][-16:])),'reminders':list(self.data['reminders']),'special_days':public_days(self.data['special_days'],date.fromisoformat(day)),'days':[{'day':k,**v} for k,v in sorted(days.items())[-7:]],'day_plan':day_plan(self.clock())}
    def configure(self,config):
        with self.lock:
            if not isinstance(config,dict) or any(k not in self.data['config'] or not isinstance(v,bool) for k,v in config.items()):raise ValueError('陪伴设置无效')
            self.data['config'].update(config);self.save();return self.status()
    def special(self,request):
        with self.lock:
            update(self.data['special_days'],request,date.fromisoformat(self.day()))
            self.save()
            return self.status()
    def occasion_entries(self):
        with self.lock:
            return [dict(item) for item in self.data['special_days']]
