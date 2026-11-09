"""Standing gestures with clear primary poses and explicit release phases."""
import math
from actions89 import smooth,blink,idle,face_review
from actions90 import interaction as previous,fullbody as previous_fullbody,INTERACTIONS as BEFORE

INTERACTIONS=[(name.replace('90','92'),label.replace('轻微上下','上下').replace('招手回应','抬臂摆手回应')) for name,label in BEFORE]
VOWELS={
 'A':{'ParamMouthOpenY':.82,'ParamMouthForm':0.,'ParamMouthWidth':.15},
 'I':{'ParamMouthOpenY':.20,'ParamMouthForm':.65,'ParamMouthWidth':1.},
 'U':{'ParamMouthOpenY':.27,'ParamMouthForm':-.8,'ParamMouthWidth':-1.},
 'E':{'ParamMouthOpenY':.46,'ParamMouthForm':.75,'ParamMouthWidth':.85},
 'O':{'ParamMouthOpenY':.84,'ParamMouthForm':0.,'ParamMouthWidth':-1.}}

def interaction(index,t,c=None):
 o=previous(index,t,c)
 e=smooth((t-.2)/1.1)*(1-smooth((t-4)/1.6))
 if index==2:o.update(ParamMouthWidth=-.2*e)
 if index==5:
  def tap(start):
   x=t-start
   return math.sin(5.5*x)*math.exp(-1.65*x) if x>=0 else 0.
  p=(tap(.45)+.8*tap(2.25))*(1-smooth((t-4.3)/1.2))
  o.update(ParamAngleY=-21*p,ParamAngleZ=-10*p,ParamHipY=.13*max(p,0))
 if index==6:o.update(ParamAngleY=-20*e,ParamAngleZ=9*e,ParamHipY=.3*e)
 if index==7:o.update(ParamAngleZ=16*e,ParamAngleX=-16*e)
 if index==8:o.update(ParamMouthOpenY=.08*e,ParamMouthWidth=.3*e)
 if index==10:o['ParamMouthWidth']=-.25*min(1,abs(o.get('ParamMouthOpenY',0))*8)
 if index==11:o.update(ParamArmL=.45*e,ParamElbowL=-.25*e,ParamWristL=-.55*e)
 if index==12:o.update(ParamArmR=.45*e,ParamElbowR=-.3*e,ParamWristR=.25*e)
 if index==18:o.update(ParamArmL=.4*e,ParamElbowL=-.5*e,ParamWristL=.8*math.sin(t*math.tau/1.3)*e,ParamMouthOpenY=.1*e,ParamMouthWidth=.45*e)
 return o

def fullbody(t,c=None):
 o=previous_fullbody(t,c);phase=min(int(t//8),5);x=t%8;e=smooth(x/.6)*(1-smooth((x-6.2)/1.3));s=math.sin(x*math.tau/5)*e
 if phase==3:o.update(ParamArmL=.55*s,ParamArmR=-.45*s,ParamElbowL=-.45*(.5+.5*math.sin(x*math.tau/5))*e,ParamElbowR=-.4*(.5+.5*math.sin(x*math.tau/5+1))*e,ParamWristL=.65*s,ParamWristR=-.6*s)
 return o

def vowel_review(t,c=None):
 phase=min(int(t//3),4);v=VOWELS[list(VOWELS)[phase]];x=t%3;e=smooth(x/.4)*(1-smooth((x-2.3)/.6))
 return {pid:value*e for pid,value in v.items()}
