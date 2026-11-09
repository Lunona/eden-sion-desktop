"""Stable head contact: one gentle lean while the hand strokes back and forth."""
import math
import numpy as np
from interaction_engine104 import Engine as PreviousEngine,Motion,EXTENSIONS,smooth
from rig_limits import clamp_value

class Engine(PreviousEngine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.pet_focus=0.
        self.pet_roll=0.

    def stroke_head(self,amount,now,direction=1.):
        # Stroke direction changes quickly; the head does not reverse its lean
        # every time the hand changes direction.
        super().stroke_head(amount,now,direction=1.)

    def _contact_delta(self,zone,vector,age):
        layer=super()._contact_delta(zone,vector,age)
        if zone=='head':
            layer['ParamAngleZ']=smooth(age/.65)*(1.0+.7*self.pet_roll)
        return layer

    def step(self,now):
        dt=float(np.clip(now-self.last_time,0,.1))
        head_contact=self.contact is not None and self.contact['zone']=='head'
        head_release=self.release is not None and self.release[2]=='head'
        target=1. if (head_contact or head_release) and self.active is None else 0.
        self.pet_focus+=(target-self.pet_focus)*(1-math.exp(-6*dt))
        hand_x=float(self.contact_vector[0]) if head_contact else 0.
        self.pet_roll+=(hand_x-self.pet_roll)*(1-math.exp(-2*dt))
        values=super().step(now)
        action=self.action_delta(now)
        ownership=min(1.,max(abs(action.get('ParamAngleX',0))/10,
                            abs(action.get('ParamAngleY',0))/10,
                            abs(action.get('ParamEyeBallX',0))/.45))
        weight=.94*self.pet_focus*(1-ownership)
        values['ParamAngleX']-=14*self.head_gaze[0]*weight
        values['ParamAngleY']-=6*self.head_gaze[1]*weight
        values['ParamAngleZ']-=4*self.head_gaze[0]*weight
        self.last_values={k:clamp_value(v,*self.ranges[k]) for k,v in values.items()}
        return dict(self.last_values)

    def reset(self,now):
        super().reset(now)
        self.pet_focus=0.;self.pet_roll=0.
