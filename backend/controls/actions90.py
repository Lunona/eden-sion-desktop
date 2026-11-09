"""Readable primary gestures, held long enough to see at full-body scale."""
import math
import numpy as np
from actions89 import smooth,blink,fullbody,face_review,idle

def hold(t,end=4.0):return smooth((t-.2)/1.1)*(1-smooth((t-end)/1.6))
def interaction(index,t,c=None):
 e=hold(t);rub=math.sin(t*math.tau/1.9)
 def tap(start):
  x=t-start
  if x<0:return 0.
  return math.sin(5.5*x)*math.exp(-1.65*x)
 release=1-smooth((t-4.3)/1.2)
 pulse=(tap(.45)+.8*tap(2.25))*release
 if index==1:
  s=math.sin((t-.25)*math.tau/5.5)*e
  return dict(ParamEyeBallX=.85*s,ParamEyeBallY=.3*math.sin(t*math.tau/5)*e,ParamAngleX=18*s,ParamAngleZ=8*s,ParamBodyAngleX=3*s)
 if index==2:
  return dict(ParamEyeBallY=.6*e,ParamAngleY=15*e,ParamAngleZ=-5*e,ParamBodyAngleY=3.5*e,ParamBrowLY=.65*e,ParamBrowRY=.65*e,ParamMouthOpenY=.17*e,ParamMouthForm=.2*e)
 if index==3:
  return dict(ParamEyeBallX=.85*e,ParamAngleX=23*e,ParamAngleZ=11*e,ParamBodyAngleX=4*e,ParamBodyAngleZ=2.2*e)
 if index==4:
  return dict(ParamEyeLOpen=1-.9*e,ParamEyeROpen=1-.9*e,ParamEyeLSmile=.85*e,ParamEyeRSmile=.85*e,ParamAngleZ=(-14+3*rub)*e,ParamAngleY=-5*e,ParamBodyAngleZ=-1.5*e,ParamMouthForm=.7*e)
 if index==5:
  b=min(blink(t,.55),blink(t,2.35))
  return dict(ParamEyeLOpen=b,ParamEyeROpen=b,ParamAngleY=-17*pulse,ParamAngleZ=5*pulse,ParamBodyAngleY=3*pulse,ParamHipY=.09*max(0,pulse),ParamBrowLY=.3*abs(pulse),ParamBrowRY=.3*abs(pulse))
 if index==6:
  return dict(ParamAngleY=-14*e,ParamAngleZ=9*e,ParamHipY=.23*e,ParamBodyAngleY=2.3*e,ParamEyeLOpen=1-.78*e,ParamEyeROpen=1-.78*e,ParamEyeLSmile=.25*e,ParamEyeRSmile=.25*e,ParamMouthForm=.3*e)
 if index==7:
  return dict(ParamEyeBallX=-.65*e,ParamAngleX=-13*e,ParamAngleZ=15*e,ParamBodyAngleZ=1.4*e,ParamEyeLOpen=1-.95*e,ParamEyeROpen=1-.15*e,ParamBrowLY=.4*e,ParamBrowRY=.1*e,ParamMouthForm=.4*e)
 if index==8:
  return dict(ParamCheek=.9*e,ParamEyeBallY=-.55*e,ParamAngleY=-8*e,ParamAngleZ=-11*e,ParamEyeLOpen=1-.35*e,ParamEyeROpen=1-.35*e,ParamMouthForm=.45*e,ParamBrowLForm=.35*e,ParamBrowRForm=.35*e,ParamArmL=.2*e,ParamArmR=-.2*e)
 if index==9:
  return dict(ParamAngleX=-17*e,ParamAngleZ=8*e,ParamEyeBallX=-.8*e,ParamBodyAngleZ=-4.2*e,ParamArmL=.5*e,ParamElbowL=.2*e,ParamBrowLY=.55*e,ParamBrowRY=.2*e)
 if index==10:
  q=.55*hold(t,2.9)+.6*tap(.4)*release
  return dict(ParamBodyAngleY=4*q,ParamBodyAngleZ=4.8*q,ParamBodyAngleX=-3*q,ParamHipX=-.18*q,ParamAngleZ=-7*q,ParamHandRelaxL=.5*abs(q),ParamHandRelaxR=.5*abs(q),ParamMouthOpenY=.1*abs(q))
 if index==11:
  return dict(ParamArmL=.75*e,ParamWristL=-.8*e,ParamElbowL=-.6*e,ParamHandRelaxL=.75*e,ParamEyeBallX=-.65*e,ParamEyeBallY=-.4*e,ParamAngleX=-10*e,ParamAngleZ=7*e,ParamMouthForm=.45*e)
 if index==12:
  return dict(ParamArmR=.8*e,ParamElbowR=-.55*e,ParamWristR=.5*e,ParamHandRelaxR=.5*e,ParamBodyAngleZ=2.8*e,ParamEyeBallX=.7*e,ParamAngleX=10*e,ParamAngleZ=-6*e)
 if index==13:
  return dict(ParamHairTouchL=-.98*e*(.9+.1*rub),ParamEyeBallX=-.5*e,ParamAngleX=-8*e,ParamAngleZ=5*e,ParamMouthForm=.3*e)
 if index==14:
  return dict(ParamHairTouchR=.98*hold(t,3.2),ParamEyeBallX=.5*e,ParamAngleX=8*e,ParamAngleZ=-5*e,ParamEyeLOpen=1-.15*e,ParamEyeROpen=1-.15*e)
 if index==15:
  u=math.sin(t*math.tau/5.8)*e
  return dict(ParamAngleX=20*u,ParamAngleZ=13.5*u,ParamBodyAngleX=4.2*u,ParamBodyAngleZ=4*u,ParamHipX=.45*u,ParamWaistZ=.25*u,ParamEyeBallX=.75*u)
 if index==16:
  q=(.5-.5*math.cos(t*math.tau/3.4))*e
  return dict(ParamHipY=.48*q,ParamBodyAngleY=4*q,ParamAngleY=-9*q,ParamWaistX=.1*q,ParamEyeBallY=-.6*q)
 if index==17:
  return dict(ParamKneeL=.85*e,ParamLegL=.16*e,ParamFootAngleL=-.45*e,ParamHipX=.12*e,ParamBodyAngleZ=-.6*e,ParamEyeBallY=-.75*e,ParamAngleY=-11*e,ParamArmR=.1*e)
 if index==18:
  return dict(ParamArmL=1.*e,ParamElbowL=-.95*e,ParamWristL=.95*math.sin(t*math.tau/1.3)*e,ParamHandRelaxL=.45*e,ParamMouthForm=.8*e,ParamEyeLSmile=.6*e,ParamEyeRSmile=.6*e,ParamAngleZ=-5*e,ParamBodyAngleZ=-1.8*e)
 raise ValueError(index)

from actions89 import INTERACTIONS as OLD_INTERACTIONS
INTERACTIONS=[(name.replace('89','90'),label) for name,label in OLD_INTERACTIONS]
