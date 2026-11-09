"""Visible limb feedback and richer facial combinations on the same rig."""
import math
import numpy as np
from interaction_engine98 import Engine as PreviousEngine, Motion, EXTENSIONS, smooth
from face_presets104 import FACE_BLUSH,FACE_GAZE
from rig_limits import clamp_value


class Engine(PreviousEngine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.expression_blush=0.
        self.expression_gaze=np.zeros(2)

    def set_face(self,name,now):
        super().set_face(name,now)
        self.note_input(now)

    def _contact_delta(self,zone,vector,age):
        # Distance-driven pulls can be complete between two render ticks.
        # Their onset must not vanish just because the mouse moved quickly.
        effective_age=age
        if zone.startswith(('hair','cuff')):
            effective_age=max(age,.25*smooth(float(np.linalg.norm(vector))/.15))
        layer=super()._contact_delta(zone,vector,effective_age)
        if zone.startswith('hair'):
            pid='ParamHairTouch'+zone[-1]
            layer[pid]*=1.3
        elif zone.startswith('cuff'):
            for pid in list(layer):
                if pid.startswith(('ParamArm','ParamElbow','ParamWrist','ParamHandRelax')):layer[pid]*=1.5
        elif zone.startswith('hand'):
            side=zone[-1];onset=smooth(age/.25);hold=.2+.8*smooth(age/2.5)
            layer['ParamWrist'+side]*=1.5
            layer['ParamHandRelax'+side]*=1.35
            layer['ParamElbow'+side]=.17*onset*hold
            layer['ParamArm'+side]=.07*onset*hold
        elif zone=='head':
            for pid in ['ParamEyeLSmile','ParamEyeRSmile','ParamMouthForm','ParamEyeLOpen','ParamEyeROpen']:
                layer[pid]*=1.45
            layer['ParamMouthOpenY']=.15*smooth(age/.25)*(.2+.8*smooth(age/2.5))
        return layer

    def release_contact(self,now):
        contact=self.contact
        tap=None
        if contact is not None:
            age=now-contact['start'];zone=contact['zone']
            distance=float(np.linalg.norm(self.contact_target))
            if age<.16 and distance>.1 and zone.startswith(('hair','cuff')):
                self.contact_vector=self.contact_target.copy()
            if age<.28 and distance<.08 and not contact['stroked']:
                if zone=='head':tap=(5,False)
                elif zone.startswith('hair'):tap=(13,zone.endswith('R'))
                elif zone.startswith('cuff'):tap=(12,zone.endswith('L'))
                elif zone.startswith('hand'):tap=(11,zone.endswith('R'))
        super().release_contact(now)
        if tap is not None:
            self.trigger(tap[0],now,mirror=tap[1])

    def step(self,now):
        dt=float(np.clip(now-self.last_time,0,.1))
        values=super().step(now)
        action=self.action_delta(now)
        for pid,value in action.items():
            gain=1.3 if pid.startswith(('ParamArm','ParamElbow','ParamWrist','ParamHandRelax','ParamHairTouch')) else 1.2 if pid.startswith(('ParamLeg','ParamKnee','ParamFootAngle')) else 1.
            if pid in values:values[pid]+=(gain-1)*value*self.strength
        amount=1-math.exp(-5*dt)
        self.expression_blush+=(FACE_BLUSH.get(self.expression,0.)-self.expression_blush)*amount
        self.expression_gaze+=(np.array(FACE_GAZE.get(self.expression,(0.,0.)))-self.expression_gaze)*amount
        values['ParamCheek']+=(1-values['ParamCheek'])*self.expression_blush
        if not self.contact and self.active is None:
            values['ParamEyeBallX']+=self.expression_gaze[0]
            values['ParamEyeBallY']+=self.expression_gaze[1]
        self.last_values={k:clamp_value(v,*self.ranges[k]) for k,v in values.items()}
        return dict(self.last_values)

    def reset(self,now):
        super().reset(now)
        self.expression_blush=0.
        self.expression_gaze[:]=0.
