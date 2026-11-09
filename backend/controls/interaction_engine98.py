"""Continuous input feedback; rendering-independent, bounded event history."""
from collections import deque
import math
import numpy as np
from interaction_engine97 import Engine as BaseEngine, Motion, mirrored, smooth
from rig_limits import clamp_value

EXTENSIONS = [
    ('pet', '连续摸头'), ('cheeks', '左右点脸'), ('hold', '长按回应'),
    ('hair', '拖发与余摆'), ('sleeve', '拉袖回弹'), ('hand', '碰手与收指'),
    ('wind', '阵风'), ('sleep', '困倦与哈欠'), ('double', '双击回应'),
    ('proximity', '靠近与离开')]

ZONE_LABELS = {'head': '摸头', 'faceL': '左脸', 'faceR': '右脸',
               'hairL': '左侧长发', 'hairR': '右侧长发',
               'cuffL': '左侧袖口', 'cuffR': '右侧袖口',
               'handL': '左手', 'handR': '右手', 'cloth': '衣料'}


class Engine(BaseEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.contact = None
        self.contact_vector = np.zeros(2)
        self.contact_target = np.zeros(2)
        self.contact_velocity = np.zeros(2)
        self.release = None
        self.contact_fading = None
        self.tap_times = deque(maxlen=6)
        self.cheek_response = None
        self.pet_reward = 0.
        self.pet_direction = 1.
        self.last_stroke = -10.
        self.last_input = 0.
        self.proximity = 0.
        self.proximity_target = 0.
        self.pointer_inside = False
        self._pointer_sample = None
        self.auto_drowsy = True
        self.sleep_blend = 0.
        self.sleep_after = 60.
        self.wind_strength = 1.
        self.wind_direction = 0.
        self.wind_gusts = deque(maxlen=8)
        self.combo = None
        self.demo = None
        self.events = deque(maxlen=128)
        self.kneel = 0.
        self.kneel_target = 0.

    def note_input(self, now):
        self.last_input = now

    def trigger(self, index, now, mirror=False, hold=False):
        if now-self.cooldowns.get((index, mirror), -100) < .35:
            return False
        if self.contact or self.release or self.demo or self.combo:
            self.cancel(now)
        self.note_input(now)
        return super().trigger(index, now, mirror, hold)

    def pointer(self, x, y, inside=True):
        sample = (x, y, True) if inside else (0., 0., False)
        if sample == self._pointer_sample:
            return
        self._pointer_sample = sample
        old = self.gaze_target.copy()
        super().pointer(x, y, inside)
        self.pointer_inside = inside
        self.proximity_target = math.exp(-2.6*(x*x+y*y)) if inside else 0.
        if np.linalg.norm(self.gaze_target-old) > .015:
            self.note_input(self.last_time)

    def stroke_head(self, amount, now, direction=1.):
        self.note_input(now)
        self.pet_reward = min(1., self.pet_reward + .13*abs(amount))
        self.pet_direction = float(np.clip(direction, -1, 1))
        self.last_stroke = now
        self.events.append(('stroke', round(now, 3), round(self.pet_reward, 3)))

    def press_contact(self, zone, now, *, from_demo=False):
        if not from_demo and (self.demo or self.active or self.contact or self.release or self.combo):
            self.cancel(now)
        self.note_input(now)
        self.contact = {'zone': zone, 'start': now, 'move_time': now,
                        'last_target': np.zeros(2), 'stroked': False}
        self.contact_vector[:] = 0
        self.contact_target[:] = 0
        self.contact_velocity[:] = 0
        self.release = None
        self.events.append(('press', zone, round(now, 3)))
        if zone in ['faceL', 'faceR']:
            self.tap_times.append(now)
            count = sum(now-t < 3. for t in self.tap_times)
            self.cheek_response = (now, zone[-1], min(count, 3))

    def move_contact(self, x, y, now):
        if self.contact is None:
            return
        self.note_input(now)
        target = np.clip([x, y], -1, 1)
        previous = self.contact['last_target']
        dt = max(1/120, now-self.contact['move_time'])
        velocity = np.clip((target-previous)/dt, -4, 4)
        self.contact_velocity = .5*self.contact_velocity+.5*velocity
        if self.contact['zone'] == 'head' and abs(target[0]-previous[0]) > .025:
            self.stroke_head(abs(target[0]-previous[0])*3, now, np.sign(target[0]-previous[0]))
            self.contact['stroked'] = True
        self.contact_target = target
        self.contact['last_target'] = target.copy()
        self.contact['move_time'] = now

    def _contact_delta(self, zone, vector, age):
        x, y = vector
        hold = .2+.8*smooth(age/2.5)
        onset = smooth(age/.25)
        side = zone[-1] if zone.endswith(('L', 'R')) else 'L'
        sign = -1. if side == 'L' else 1.
        if zone == 'head':
            return {'ParamAngleZ': onset*(1.2+2*hold)*self.pet_direction,
                    'ParamEyeLOpen': -.32*onset*hold, 'ParamEyeROpen': -.32*onset*hold,
                    'ParamEyeLSmile': .5*onset*hold, 'ParamEyeRSmile': .5*onset*hold,
                    'ParamMouthForm': .5*onset*hold, 'ParamCheek': .18*onset*hold}
        if zone.startswith('hair'):
            return {f'ParamHairTouch{side}': onset*(.22*hold+sign*.7*x),
                    'ParamIdleWind': .25*x*onset,
                    'ParamAngleZ': 1.6*x*onset, 'ParamEyeBallX': sign*.2*onset}
        if zone.startswith('cuff'):
            return {f'ParamArm{side}': onset*(.08*hold+sign*.2*x),
                    f'ParamElbow{side}': onset*(.12*hold+.22*y),
                    f'ParamWrist{side}': onset*.32*x,
                    f'ParamHandRelax{side}': onset*.28*hold,
                    'ParamBodyAngleZ': .65*x*onset}
        if zone.startswith('hand'):
            return {f'ParamWrist{side}': -sign*onset*(.18+.24*hold),
                    f'ParamHandRelax{side}': onset*(.25+.38*hold),
                    'ParamEyeBallX': sign*.45*onset, 'ParamEyeBallY': -.3*onset,
                    'ParamAngleX': sign*4*onset, 'ParamMouthForm': .35*onset}
        if zone == 'cloth':
            return {'ParamBodyAngleZ': 1.5*x*onset, 'ParamWaistZ': .1*x*onset,
                    'ParamCheek': .12*onset*hold}
        return {}

    def release_contact(self, now):
        if self.contact is None:
            return
        # Account for a complete gesture between render ticks.
        dt = max(1/60, now-self.last_time)
        self.contact_vector += (self.contact_target-self.contact_vector)*(1-math.exp(-10*dt))
        zone = self.contact['zone']
        age = now-self.contact['start']
        self.release = (now, self._contact_delta(zone, self.contact_vector, age),
                        zone, self.contact_velocity.copy())
        if zone == 'head' and not self.contact['stroked'] and age < .28:
            self.stroke_head(.5, now)
        self.events.append(('release', zone, round(age, 3)))
        self.contact = None
        self.contact_target[:] = 0

    def gust(self, now, direction=1.):
        self.note_input(now)
        self.wind_gusts.append((now, float(np.clip(direction, -1, 1))))

    def double_click(self, now):
        self.note_input(now)
        self.combo = now

    def begin_demo(self, name, now):
        if name not in dict(EXTENSIONS):
            raise KeyError(name)
        self.cancel(now)
        self.demo = (name, now)
        self._demo_tap_index = -1
        self._demo_gust_index = -1
        self.note_input(now)
        self.events.append(('demo', name, round(now, 3)))

    def _demo_step(self, now):
        if self.demo is None:
            return
        name, start = self.demo
        t = now-start
        if t < 0:
            return
        if t > 7.:
            self.release_contact(now)
            self.demo = None
            return
        side = 'L' if t < 3.5 else 'R'
        local = t if side == 'L' else t-3.5
        zones = {'pet': 'head', 'hold': 'head', 'hair': 'hair'+side,
                 'sleeve': 'cuff'+side, 'hand': 'hand'+side}
        if name in zones:
            zone = zones[name]
            if local < 2.5:
                if self.contact is None or self.contact['zone'] != zone:
                    self.press_contact(zone, now, from_demo=True)
                if name == 'pet':
                    self.move_contact(.7*math.sin(t*8), 0, now)
                elif name in ['hair', 'sleeve']:
                    self.move_contact((-.7 if side == 'L' else .7)*smooth(local/1.2), .35*math.sin(local*2), now)
            elif self.contact is not None:
                self.release_contact(now)
        elif name == 'cheeks':
            index = int(t/.8)
            if getattr(self, '_demo_tap_index', -1) != index:
                self._demo_tap_index = index
                self.press_contact('face'+side, now, from_demo=True)
                self.release_contact(now)
        elif name == 'wind':
            index = int(t/2.2)
            if getattr(self, '_demo_gust_index', -1) != index:
                self._demo_gust_index = index
                self.gust(now, 1. if index % 2 == 0 else -1.)
        elif name == 'double':
            if self.combo is None:
                self.double_click(now)
        elif name == 'proximity':
            self.pointer(.08 if t < 2 else .9, -.08 if t < 2 else .6, t < 4.5)
        elif name == 'sleep':
            self.last_input = start-self.sleep_after-7.

    def cancel(self, now):
        outgoing = None
        if self.contact:
            outgoing = self._contact_delta(self.contact['zone'], self.contact_vector,
                                            now-self.contact['start'])
        elif self.release:
            start, layer, zone, velocity = self.release
            t = now-start
            if 0 <= t < 2:
                fade = math.exp(-3.7*t)*math.cos(7*t)*(1-smooth(t/2.))
                outgoing = {k:v*fade for k,v in layer.items()}
        if outgoing:
            self.contact_fading = (now, outgoing)
        super().cancel(now)
        self.contact = None
        self.release = None
        self.demo = None
        self.combo = None
        self.cheek_response = None
        self.note_input(now)

    def reset(self, now):
        super().reset(now)
        self._pointer_sample = None
        self.contact = None
        self.release = None
        self.contact_fading = None
        self.demo = None
        self.combo = None
        self.cheek_response = None
        self.tap_times.clear()
        self.pet_reward = 0.
        self.sleep_blend = 0.
        self.wind_gusts.clear()
        self.wind_strength = 1.
        self.wind_direction = 0.
        self.kneel_target = 0.
        self.note_input(now)

    def step(self, now):
        before = self.last_time
        dt = float(np.clip(now-before, 0, .1))
        self._demo_step(now)
        values = super().step(now)
        delta = {}

        def add(layer, amount=1.):
            for pid, v in layer.items():
                delta[pid] = delta.get(pid, 0.)+v*amount

        if self.contact_fading:
            start, layer = self.contact_fading
            t = now-start
            if t >= .45:
                self.contact_fading = None
            else:
                add(layer, 1-smooth(t/.45))

        self.pet_reward *= math.exp(-dt/12.)
        pleasant = self.pet_reward
        add({'ParamCheek': .22*pleasant, 'ParamEyeLSmile': .55*pleasant,
             'ParamEyeRSmile': .55*pleasant, 'ParamMouthForm': .5*pleasant,
             'ParamEyeLOpen': -.2*pleasant, 'ParamEyeROpen': -.2*pleasant,
             'ParamAngleZ': 1.4*pleasant*self.pet_direction})
        if self.contact:
            self.contact_vector += (self.contact_target-self.contact_vector)*(1-math.exp(-10*dt))
            add(self._contact_delta(self.contact['zone'], self.contact_vector, now-self.contact['start']))
            self.last_label = '持续回应 · '+ZONE_LABELS.get(self.contact['zone'], '触碰')
        if self.release:
            start, layer, zone, velocity = self.release
            t = now-start
            if t >= 2.:
                self.release = None
            else:
                fade = math.exp(-3.7*t)*math.cos(7*t)*(1-smooth(t/2.))
                add(layer, fade)
                if zone.startswith('hair'):
                    add({f'ParamHairTouch{zone[-1]}': .12*velocity[0]*t*math.exp(-3.5*t)})
                elif zone.startswith('cuff'):
                    add({f'ParamWrist{zone[-1]}': .1*velocity[0]*t*math.exp(-3.5*t)})
        if self.cheek_response:
            start, side, level = self.cheek_response
            t = now-start
            if t >= 3.2:
                self.cheek_response = None
            else:
                weight = smooth(t/.18)*(1-smooth((t-1.5)/1.7))
                sign = -1 if side == 'L' else 1
                if level == 1:
                    add({f'ParamBrow{side}Y': .6, 'ParamAngleZ': sign*3., 'ParamMouthForm': .2}, weight)
                elif level == 2:
                    add({'ParamCheek': .55, 'ParamEyeLOpen': -.25, 'ParamEyeROpen': -.25,
                         'ParamMouthForm': .5, 'ParamAngleZ': sign*3.5}, weight)
                else:
                    add({'ParamAngleX': -sign*7., 'ParamAngleZ': -sign*3.,
                         'ParamCheek': .65, f'ParamEye{side}Open': -.32,
                         'ParamMouthForm': -.18, 'ParamBodyAngleZ': -sign*.6}, weight)
                self.last_label = ['点脸 · 疑惑', '点脸 · 害羞', '点脸 · 轻躲'][level-1]
        self.proximity += (self.proximity_target-self.proximity)*(1-math.exp(-3*dt))
        if not (self.active or self.contact or self.dragging):
            add({'ParamEyeLSmile': .14*self.proximity, 'ParamEyeRSmile': .14*self.proximity,
                 'ParamMouthForm': .2*self.proximity})
        if self.combo is not None:
            t = now-self.combo
            if t > 4.2:
                self.combo = None
            elif t < .75:
                add({'ParamBrowLY': .75, 'ParamBrowRY': .75, 'ParamMouthOpenY': .42,
                     'ParamMouthWidth': -.5}, math.sin(math.pi*t/.75))
            else:
                weight = smooth((t-.75)/.35)*(1-smooth((t-2.6)/1.6))
                add({'ParamEyeLSmile': .65, 'ParamEyeRSmile': .65,
                     'ParamEyeLOpen': -.25, 'ParamEyeROpen': -.25,
                     'ParamMouthForm': .8, 'ParamAngleY': 2.8*math.sin((t-.75)*4)}, weight)
            self.last_label = '双击 · 惊讶后微笑点头'
        quiet = now-self.last_input
        sleepy_target = smooth((quiet-self.sleep_after)/8) if self.auto_drowsy and not self.contact and self.active is None else 0.
        self.sleep_blend += (sleepy_target-self.sleep_blend)*(1-math.exp(-3*dt))
        if self.sleep_blend > .001:
            yawntime = max(0., quiet-self.sleep_after-7.) % 27.
            yawn = math.sin(math.pi*yawntime/3.)**2 if yawntime < 3. else 0.
            add({'ParamEyeLOpen': -.6, 'ParamEyeROpen': -.6, 'ParamBrowLY': -.2,
                 'ParamBrowRY': -.2, 'ParamMouthOpenY': .55*yawn,
                 'ParamMouthWidth': -.4*yawn, 'ParamAngleZ': 1.1*math.sin(now*.32)}, self.sleep_blend)
            self.last_label = '困倦 · 哈欠' if yawn > .2 else '困倦 · 轻晃'
        if self.auto_idle and quiet > 8 and self.active is None and not self.contact:
            # Deterministic varying timing, bounded and repeatable for QA.
            cycle = int(now/31.)
            p = (now % 31.)-(11.+2.5*math.sin(cycle*2.399))
            weight = math.sin(math.pi*p/4.)**2 if 0 < p < 4 else 0.
            add({'ParamBodyAngleZ': .55*weight*(1 if cycle % 2 else -1),
                 'ParamKneeL' if cycle % 2 else 'ParamKneeR': .065*weight})
        wind = values.get('ParamIdleWind', 0.)*self.wind_strength+.32*self.wind_direction*self.wind_strength
        while self.wind_gusts and now-self.wind_gusts[0][0] > 3.:
            self.wind_gusts.popleft()
        for start, direction in self.wind_gusts:
            t = now-start
            if 0 <= t < 3:
                wind += .65*direction*math.sin(math.pi*t/3.)**2
        values['ParamIdleWind'] = wind
        for pid, value in delta.items():
            if pid not in values:
                continue
            if pid in ['ParamEyeLOpen', 'ParamEyeROpen']:
                values[pid] *= max(0., 1+value)
            elif pid == 'ParamCheek':
                values[pid] += (1-values[pid])*max(0., value)
            else:
                values[pid] += value
        # Manual speech remains authoritative during any temporary expression.
        if self.vowel:
            values.update(self.vowels[self.vowel])
        self.kneel += (self.kneel_target-self.kneel)*(1-math.exp(-2*dt))
        if 'ParamPoseKneel' in values:
            values['ParamPoseKneel'] = self.kneel
        if self.kneel > 0:
            blend = 1-smooth(self.kneel)
            for pid in values:
                if pid.startswith(('ParamLeg', 'ParamKnee', 'ParamFootAngle', 'ParamArm', 'ParamElbow', 'ParamWrist')):
                    values[pid] *= blend
            values['ParamIdleWind'] *= 1-.55*self.kneel
        self.last_values = {pid: clamp_value(v, *self.ranges[pid]) for pid, v in values.items()}
        return dict(self.last_values)
