"""Active controls only. Every demonstration releases to its neutral pose."""
import math
import numpy as np
def smooth(x):
    x=float(np.clip(x,0,1));return x*x*(3-2*x)
def hold(t,end=4.1):return smooth((t-.25)/.65)*(1-smooth((t-end)/1.1))
def blink(t,start):return float(np.interp(t,[start,start+.09,start+.17,start+.35],[1,0,0,1]))

def interaction(index,t,c=None):
    e=hold(t);rub=math.sin(t*math.tau/1.8);x=max(0,t-.4)
    pulse=math.sin(9*x)*math.exp(-2.7*x) if t>=.4 else 0
    if index==1:
        s=math.sin(t*math.tau/4)*e
        return dict(ParamEyeBallX=.65*s,ParamEyeBallY=.22*math.sin(t*math.tau/5)*e,ParamAngleX=7*math.sin(max(0,t-.25)*math.tau/4)*e,ParamAngleY=1.2*e)
    if index==2:
        return dict(ParamEyeBallY=.2*e,ParamAngleY=2*e,ParamBodyAngleY=1.3*e,ParamBrowLY=.18*e,ParamBrowRY=.18*e,ParamMouthForm=.25*e)
    if index==3:
        return dict(ParamEyeBallX=.6*e,ParamAngleX=9*e,ParamAngleZ=1.5*e,ParamBodyAngleX=1.1*e)
    if index==4:
        return dict(ParamEyeLOpen=1-.70*e,ParamEyeROpen=1-.70*e,ParamEyeLSmile=.55*e,ParamEyeRSmile=.55*e,ParamAngleZ=(-4+1.2*rub)*e,ParamAngleY=-2*e,ParamMouthForm=.55*e)
    if index==5:
        b=min(blink(t,.45),blink(t,1.1))
        return dict(ParamEyeLOpen=b,ParamEyeROpen=b,ParamAngleY=-4*pulse,ParamAngleZ=1.8*pulse,ParamBrowLY=.15*abs(pulse),ParamBrowRY=.15*abs(pulse))
    if index==6:
        return dict(ParamAngleY=-3.5*e,ParamAngleZ=-2.0*e,ParamEyeLOpen=1-.55*e,ParamEyeROpen=1-.55*e,ParamEyeLSmile=.25*e,ParamEyeRSmile=.25*e,ParamMouthForm=.2*e)
    if index==7:
        return dict(ParamEyeBallX=-.4*e,ParamAngleX=-4*e,ParamAngleZ=2*e,ParamEyeLOpen=min(blink(t,.45),1-.12*e),ParamBrowLY=.2*e,ParamBrowRY=.05*e,ParamMouthForm=.25*e)
    if index==8:
        return dict(ParamCheek=.72*e,ParamEyeBallY=-.35*e,ParamAngleY=-2*e,ParamAngleZ=3*e,ParamEyeLOpen=1-.2*e,ParamEyeROpen=1-.2*e,ParamMouthForm=.3*e,ParamBrowLForm=.15*e,ParamBrowRForm=.15*e)
    if index==9:
        return dict(ParamAngleX=-6*e,ParamEyeBallX=-.45*e,ParamBodyAngleZ=-1.8*e,ParamArmL=.08*e,ParamBrowLY=.22*e,ParamBrowRY=.1*e)
    if index==10:
        return dict(ParamBodyAngleY=2.6*pulse,ParamBodyAngleZ=3*pulse,ParamBodyAngleX=-2*pulse,ParamHipX=-.08*pulse,ParamAngleZ=-2*pulse,ParamHandRelaxL=.25*abs(pulse),ParamHandRelaxR=.25*abs(pulse))
    if index==11:
        return dict(ParamWristL=-.45*e,ParamElbowL=.13*e,ParamHandRelaxL=.55*e,ParamEyeBallX=-.45*e,ParamEyeBallY=-.4*e,ParamAngleX=-4*e,ParamMouthForm=.25*e)
    if index==12:
        return dict(ParamArmR=.18*e,ParamElbowR=.22*e,ParamWristR=.2*e,ParamHandRelaxR=.18*e,ParamBodyAngleZ=1.3*e,ParamEyeBallX=.45*e,ParamAngleX=4*e)
    if index==13:
        return dict(ParamHairTouchL=-.65*e*(.85+.15*rub),ParamEyeBallX=-.3*e,ParamAngleX=-2*e,ParamMouthForm=.15*e)
    if index==14:
        return dict(ParamHairTouchR=.85*hold(t,3.5),ParamEyeBallX=.3*e,ParamAngleX=2*e,ParamEyeLOpen=1-.1*e,ParamEyeROpen=1-.1*e)
    if index==15:
        u=float(np.interp(t,[0,.6,1.5,2.2,3.2,4,5.2,6],[0,.3,1,.7,-.8,-1,0,0]))*e
        return dict(ParamAngleX=10*u,ParamAngleZ=5*u,ParamBodyAngleX=2.8*u,ParamBodyAngleZ=3*u,ParamHipX=.32*u,ParamWaistZ=.2*u,ParamEyeBallX=.45*u)
    if index==16:
        q=(.5-.5*math.cos(t*math.tau/3))*e
        return dict(ParamHipY=.2*q,ParamBodyAngleY=2*q,ParamAngleY=-3*q,ParamWaistX=.08*q,ParamEyeBallY=-.3*q)
    if index==17:
        return dict(ParamKneeL=.62*e,ParamLegL=.1*e,ParamFootAngleL=-.22*e,ParamHipX=.12*e,ParamHipY=.04*e,ParamBodyAngleZ=-.6*e,ParamEyeBallY=-.55*e,ParamAngleY=-3.5*e)
    if index==18:
        return dict(ParamArmL=.22*e,ParamElbowL=.35*e,ParamWristL=.5*math.sin(t*math.tau/1.1)*e,ParamHandRelaxL=.3*e,ParamMouthForm=.6*e,ParamEyeLSmile=.4*e,ParamEyeRSmile=.4*e,ParamBodyAngleZ=-1*e)
    raise ValueError(index)

INTERACTIONS=[
 ('GazeFollow89','01 注视跟随'),('NoticeApproach89','02 靠近注意'),('LookAfter89','03 目送后回正'),
 ('StrokeHead89','04 轻摸头'),('PatHead89','05 轻拍头'),('HoldHead89','06 头顶按住与松开'),
 ('TapCheek89','07 轻点脸颊'),('ShyHover89','08 脸旁停留与害羞'),('TapShoulder89','09 轻点肩部'),
 ('TapCloth89','10 前襟轻点回弹'),('TouchHand89','11 碰手与手腕回应'),('PullSleeve89','12 袖口轻拉与释放'),
 ('StrokeHair89','13 左侧长发轻拨'),('ReleaseHair89','14 右侧发梢保持与释放'),
 ('DragSide89','15 左右拖动与重心'),('DragVertical89','16 轻微上下拖动'),('FootResponse89','17 脚边反应与抬脚'),('WaveHello89','18 招手回应')]

def fullbody(t,c=None):
    phase=min(int(t//8),5);x=t%8;e=smooth(x/.6)*(1-smooth((x-6.2)/1.3));s=math.sin(x*math.tau/5)*e
    o=dict(ParamHipX=0.,ParamHipY=0.,ParamWaistX=0.,ParamWaistZ=0.,ParamLegL=0.,ParamLegR=0.,ParamKneeL=0.,ParamKneeR=0.,ParamFootAngleL=0.,ParamFootAngleR=0.,ParamArmL=0.,ParamArmR=0.,ParamElbowL=0.,ParamElbowR=0.,ParamWristL=0.,ParamWristR=0.,ParamHandRelaxL=0.,ParamHandRelaxR=0.,ParamAngleX=0.,ParamAngleY=0.,ParamAngleZ=0.,ParamBodyAngleX=0.,ParamBodyAngleY=0.,ParamBodyAngleZ=0.,ParamHairTouchL=0.,ParamHairTouchR=0.,ParamBreath=0.)
    if phase==0:o.update(ParamHipX=.5*s,ParamHipY=.16*(.5-.5*math.cos(x*math.tau/5))*e,ParamWaistZ=.18*s,ParamWaistX=.16*s)
    if phase in [1,2]:
        side='L' if phase==1 else 'R';q=(.5-.5*math.cos(x*math.tau/5))*e
        o.update({'ParamKnee'+side:.7*q,'ParamLeg'+side:(.12 if side=='L' else -.12)*q,'ParamFootAngle'+side:(-.3 if side=='L' else .3)*q,'ParamHipX':(.12 if side=='L' else -.12)*q})
    if phase==3:o.update(ParamArmL=.22*s,ParamArmR=-.18*s,ParamElbowL=.35*(.5+.5*math.sin(x*math.tau/5))*e,ParamElbowR=.3*(.5+.5*math.sin(x*math.tau/5+1))*e,ParamWristL=.5*s,ParamWristR=-.45*s,ParamHandRelaxL=.5*e,ParamHandRelaxR=.4*e)
    if phase==4:o.update(ParamAngleX=15*s,ParamAngleY=9*math.sin(x*math.tau/6)*e,ParamAngleZ=10*math.sin(x*math.tau/7)*e,ParamBodyAngleX=3*s,ParamBodyAngleY=2*math.sin(x*math.tau/4)*e,ParamBodyAngleZ=3*math.sin(x*math.tau/6)*e,ParamBreath=.5*e)
    if phase==5:o.update(ParamHairTouchL=-.65*math.sin(x*math.pi/7)**2*e,ParamHairTouchR=.65*math.sin(x*math.pi/7)**2*e)
    return o

def face_review(t,c=None):
    o=dict(ParamEyeLOpen=1.,ParamEyeROpen=1.,ParamEyeLSmile=0.,ParamEyeRSmile=0.,ParamEyeBallX=0.,ParamEyeBallY=0.,ParamMouthForm=0.,ParamMouthOpenY=0.,ParamCheek=0.)
    for s in ['L','R']:
        for tail in ['X','Y','Angle','Form']:o['ParamBrow'+s+tail]=0.
    phase=min(int(t//4),7);x=t%4;e=smooth(x/.35)*(1-smooth((x-3)/.6))
    if phase==0:
        op=float(np.interp(x,[0,.5,1.2,2,2.5,3.2,4],[1,1,.5,0,0,.5,1]));o.update(ParamEyeLOpen=op,ParamEyeROpen=op)
    elif phase==1:o.update(ParamEyeBallX=.75*math.sin(x*math.tau/4)*e,ParamEyeBallY=.65*math.cos(x*math.tau/4)*e)
    elif phase==2:
        for s,sign in [('L',1),('R',-1)]:
            o.update({'ParamBrow'+s+'Y':.6*math.sin(x*math.tau/4)*e,'ParamBrow'+s+'X':.5*sign*math.sin(x*math.tau/4)*e,'ParamBrow'+s+'Angle':.6*sign*math.cos(x*math.tau/4)*e,'ParamBrow'+s+'Form':.6*math.sin(x*math.tau/3)*e})
    elif phase==3:o.update(ParamMouthOpenY=.65*(.5-.5*math.cos(x*math.tau/1.1))*e,ParamMouthForm=.7*math.sin(x*math.tau/4)*e)
    elif phase==4:o['ParamCheek']=(.5-.5*math.cos(x*math.tau/4))*e
    elif phase==5:o.update(ParamEyeLSmile=.7*e,ParamEyeRSmile=.7*e,ParamMouthForm=.7*e,ParamCheek=.35*e)
    elif phase==6:o.update(ParamEyeLOpen=1-.45*e,ParamEyeROpen=1-.45*e,ParamBrowLY=.25*e,ParamBrowRY=.15*e,ParamBrowLAngle=-.4*e,ParamBrowRAngle=.4*e,ParamMouthForm=-.3*e)
    return o

def idle(t,c=None,variant=0):
    o=dict(ParamBreath=.45+.35*math.sin(t*math.tau/4),ParamAngleX=2*math.sin(t*math.tau/12),ParamAngleY=.8*math.sin(t*math.tau/24),ParamAngleZ=1*math.sin(t*math.tau/8),ParamEyeLOpen=min(blink(t,3),blink(t,9),blink(t,16),blink(t,21)),ParamEyeROpen=min(blink(t,3),blink(t,9),blink(t,16),blink(t,21)))
    if variant==1:o.update(ParamEyeBallX=.35*math.sin(t*math.tau/12),ParamEyeBallY=.12*math.sin(t*math.tau/8),ParamAngleX=4*math.sin(t*math.tau/12))
    if variant==2:o.update(ParamEyeLOpen=.75*o['ParamEyeLOpen'],ParamEyeROpen=.75*o['ParamEyeROpen'],ParamAngleY=-1+.5*math.sin(t*math.tau/8),ParamMouthForm=.15)
    return o
