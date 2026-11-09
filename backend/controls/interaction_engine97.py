"""Offline interaction state machine, separate from rendering and Cubism files."""
from dataclasses import dataclass
import json,math,re
from pathlib import Path
import numpy as np
from rig_limits import clamp_value

def smooth(x):
 x=float(np.clip(x,0,1));return x*x*(3-2*x)

class Motion:
 def __init__(self,data):
  self.duration=float(data['Meta']['Duration']);self.curves={}
  for curve in data['Curves']:
   seg=curve['Segments'];assert all(seg[i]==0 for i in range(2,len(seg),3))
   self.curves[curve['Id']]=(np.array([seg[0]]+[seg[i+1] for i in range(2,len(seg),3)]),np.array([seg[1]]+[seg[i+2] for i in range(2,len(seg),3)]))
 @classmethod
 def read(cls,path):return cls(json.loads(Path(path).read_text('utf-8')))
 def sample(self,t):return {pid:float(np.interp(t,ts,vs)) for pid,(ts,vs) in self.curves.items()}

def mirrored(values):
 out={}
 for pid,value in values.items():
  dest=pid
  for pattern in [r'^(Param(?:Arm|Elbow|Wrist|HandRelax|Leg|Knee|FootAngle|LegSway|HairTouch))([LR])$',r'^(ParamEye)([LR])(Open|Smile)$',r'^(ParamBrow)([LR])(X|Y|Angle|Form)$']:
   m=re.match(pattern,pid)
   if m:
    dest=m[1]+('R' if m[2]=='L' else 'L')+(m[3] if m.lastindex==3 else '');break
  negate=pid in ['ParamAngleX','ParamAngleZ','ParamBodyAngleX','ParamBodyAngleZ','ParamHipX','ParamWaistX','ParamWaistZ','ParamEyeBallX'] or bool(re.match(r'^Param(?:Wrist|FootAngle|HairTouch)[LR]$',pid)) or bool(re.match(r'^ParamBrow[LR](?:X|Angle)$',pid))
  out[dest]=-value if negate else value
 return out

@dataclass
class Action:
 index:int
 start:float
 mirror:bool=False
 hold:bool=False
 released_at:float|None=None
 release_from:float=4.
 amplitude:float=1.

class Engine:
 def __init__(self,defaults,ranges,motions,faces,vowels,idle=None):
  self.defaults=dict(defaults);self.ranges=dict(ranges);self.motions=motions;self.faces=faces;self.vowels=vowels;self.idle=idle
  self.active=None;self.fading=None;self.cooldowns={};self.expression='neutral';self.face_from=dict(faces['neutral']);self.face_target=dict(self.face_from);self.face_changed=-10.
  self.blush=0.;self.vowel=None;self.strength=1.;self.auto_idle=True;self.idle_blend=1.;self.idle_pose_blend=1.;self.idle_leg_blend=1.;self.auto_blink=True;self.auto_speech=False;self.gaze=np.zeros(2);self.head_gaze=np.zeros(2);self.gaze_target=np.zeros(2);self.last_time=0.;self.dragging=False;self.drag=np.zeros(2);self.drag_target=np.zeros(2);self.drag_release=None;self.last_values=dict(defaults);self.last_label='自然待机'
 def face_values(self,now):
  mix=smooth((now-self.face_changed)/.4);return {pid:self.face_from[pid]+(value-self.face_from[pid])*mix for pid,value in self.face_target.items()}
 def set_face(self,name,now):
  if name not in self.faces:raise KeyError(name)
  self.face_from=self.face_values(now);self.face_target=dict(self.faces[name]);self.face_changed=now;self.expression=name
 def _raw_action(self,now):
  a=self.active
  if a is None:return {}
  t=now-a.start
  if a.hold and a.released_at is None:t=min(t,2.)
  if a.released_at is not None:t=a.release_from+now-a.released_at
  if t>=self.motions[a.index].duration:
   self.active=None;return {}
  values=self.motions[a.index].sample(max(0,t));delta={pid:(value-self.defaults[pid])*a.amplitude for pid,value in values.items()}
  return mirrored(delta) if a.mirror else delta
 def action_delta(self,now):
  result=self._raw_action(now)
  if self.fading is not None:
   start,duration,values=self.fading;fade=1-smooth((now-start)/duration)
   if fade<=0:self.fading=None
   else:
    for pid,value in values.items():result[pid]=result.get(pid,0)+value*fade
  return result
 def trigger(self,index,now,mirror=False,hold=False):
  if index not in self.motions:raise KeyError(index)
  key=(index,mirror)
  if now-self.cooldowns.get(key,-100)<.35:return False
  old=self.action_delta(now);self.fading=(now,.3,old) if old else None;self.active=Action(index,now,mirror,hold,release_from=3.2 if index==14 else 4.);self.cooldowns[key]=now;self.last_label=f'互动 {index:02d}'+(' · 保持中' if hold else '')
  return True
 def release_hold(self,now):
  if self.active and self.active.hold and self.active.released_at is None:
   values=self.action_delta(now);self.active=None;self.fading=(now,1.4,values);self.last_label='已松开 · 回到自然'
 def cancel(self,now):
  old=self.action_delta(now);self.active=None;self.fading=(now,.45,old) if old else None;self.last_label='回到自然'
  if self.dragging:self.stop_drag(now)
 def pointer(self,x,y,inside=True):self.gaze_target=np.array([float(np.clip(x,-1,1)),float(np.clip(-y,-1,1))]) if inside else np.zeros(2)
 def start_drag(self,now):
  self.cancel(now);self.dragging=True;self.drag[:]=0;self.drag_target[:]=0;self.drag_release=None;self.last_label='拖动跟随'
 def update_drag(self,x,y):self.drag_target=np.clip([x,y],-1,1)
 def drag_values(self,x,y):
  return {'ParamAngleX':20*x,'ParamAngleZ':11*x,'ParamBodyAngleX':3.6*x,'ParamBodyAngleZ':3.5*x,'ParamHipX':.32*x,'ParamWaistZ':.18*x,'ParamHipY':.3*max(y,0),'ParamBodyAngleY':2.5*y,'ParamAngleY':-9*y}
 def stop_drag(self,now):
  if self.dragging:
   # Even a quick mouse stroke can begin and end between two render ticks.
   self.drag+=(self.drag_target-self.drag)*(1-math.exp(-10*max(1/60,now-self.last_time)))
   self.drag_release=(now,self.drag_values(*self.drag));self.dragging=False;self.drag_target[:]=0;self.last_label='已松开 · 惯性回位'
 def reset(self,now):
  self.active=None;self.fading=None;self.cooldowns.clear();self.blush=0.;self.vowel=None;self.set_face('neutral',now);self.gaze_target[:]=0;self.dragging=False;self.drag_release=None;self.last_label='自然待机'
 def step(self,now):
  dt=float(np.clip(now-self.last_time,0,.1));self.last_time=now
  self.gaze+=(self.gaze_target-self.gaze)*(1-math.exp(-8*dt));self.head_gaze+=(self.gaze_target-self.head_gaze)*(1-math.exp(-3*dt));base=dict(self.defaults)
  self.idle_blend+=((1. if self.auto_idle else 0.)-self.idle_blend)*(1-math.exp(-4*dt))
  self.idle_pose_blend+=((.25 if self.active or self.fading or self.dragging or self.drag_release else 1.)-self.idle_pose_blend)*(1-math.exp(-4*dt))
  self.idle_leg_blend+=((0. if self.active or self.fading or self.dragging or self.drag_release else 1.)-self.idle_leg_blend)*(1-math.exp(-6*dt))
  if self.idle:
   for pid,value in self.idle.sample(now%self.idle.duration).items():
    blend=self.idle_leg_blend if re.match(r'^Param(?:Leg|Knee|FootAngle)[LR]$',pid) else ((.65+.35*self.idle_pose_blend) if pid=='ParamIdleWind' else (1. if pid in ['ParamBreath','ParamEyeLOpen','ParamEyeROpen'] else self.idle_pose_blend))
    base[pid]=self.defaults[pid]+(value-self.defaults[pid])*self.idle_blend*blend
  if not self.auto_blink:base['ParamEyeLOpen']=base['ParamEyeROpen']=1.
  base['ParamEyeBallX']=.8*self.gaze[0];base['ParamEyeBallY']=.65*self.gaze[1]
  base['ParamAngleX']+=14*self.head_gaze[0];base['ParamAngleY']+=6*self.head_gaze[1];base['ParamAngleZ']+=4*self.head_gaze[0]
  for pid,value in self.face_values(now).items():
   if pid in ['ParamEyeLOpen','ParamEyeROpen']:base[pid]*=value
   elif pid=='ParamMouthOpenY':base[pid]+=value
   else:base[pid]=value
  base['ParamCheek']=float(np.clip(self.blush,0,1))
  delta=self.action_delta(now);gain=float(np.clip(self.strength,.6,1.))
  # A purposeful gesture gradually takes ownership from pointer-following.
  ownership=min(1.,max(abs(delta.get('ParamAngleX',0))/10,abs(delta.get('ParamAngleY',0))/10,abs(delta.get('ParamEyeBallX',0))/.45))
  if 'ParamAngleX' in delta:base['ParamAngleX']-=14*self.head_gaze[0]*ownership
  if 'ParamAngleY' in delta:base['ParamAngleY']-=6*self.head_gaze[1]*ownership
  if 'ParamAngleZ' in delta:base['ParamAngleZ']-=4*self.head_gaze[0]*ownership
  if 'ParamEyeBallX' in delta:base['ParamEyeBallX']*=1-ownership
  if 'ParamEyeBallY' in delta:base['ParamEyeBallY']*=1-ownership
  for pid,value in delta.items():
   value*=gain
   if pid in ['ParamEyeLOpen','ParamEyeROpen']:base[pid]*=max(0,1+value)
   elif pid=='ParamCheek':base[pid]+=(1-base[pid])*max(0,value)
   else:base[pid]+=value
  if self.dragging:
   self.drag+=(self.drag_target-self.drag)*(1-math.exp(-10*dt))
   for pid,value in self.drag_values(*self.drag).items():base[pid]+=value
  elif self.drag_release:
   started,values=self.drag_release;t=now-started
   if t>=1.2:self.drag_release=None;self.drag[:]=0
   else:
    fade=math.exp(-4.5*t)*math.cos(7*t)*(1-smooth(t/1.2))
    for pid,value in values.items():base[pid]+=value*fade
  vowel=self.vowel
  if self.auto_speech:vowel=list(self.vowels)[int(now/1.3)%5]
  if vowel:
   for pid,value in self.vowels[vowel].items():base[pid]=value
  result={pid:clamp_value(value,*self.ranges[pid]) for pid,value in base.items()}
  self.last_values=result
  if self.active is None and self.fading is None and not self.dragging and not self.drag_release:self.last_label='自然待机'
  return result
