"""Distinct existing-art facial combinations; no replacement facial artwork."""
from face_presets92 import FACE_BASE

FACE_LABELS = {
 'neutral':'默认','soft_smile':'微笑','closed_smile':'闭眼笑','wink_left':'左眨眼','wink_right':'右眨眼',
 'worried':'担忧','serious':'严肃','happy':'开心笑','shy':'害羞','surprised':'惊讶',
 'curious':'疑惑','sleepy':'困倦','downcast':'失落','annoyed':'轻微不满',
 'laugh':'开怀笑','angry':'生气','pout':'嘟嘴','bashful':'羞怯低眼','expectant':'期待',
 'thinking':'思考','skeptical':'怀疑','embarrassed':'尴尬','yawning':'打哈欠','resting':'放松闭眼'}

FACE_VALUES = {
 'neutral':{},
 'soft_smile':{'ParamEyeLOpen':.87,'ParamEyeROpen':.87,'ParamEyeLSmile':.5,'ParamEyeRSmile':.5,'ParamMouthForm':.9,'ParamMouthOpenY':.18,'ParamMouthWidth':.35},
 'closed_smile':{'ParamEyeLOpen':0.,'ParamEyeROpen':0.,'ParamEyeLSmile':1.,'ParamEyeRSmile':1.,'ParamMouthForm':1.,'ParamMouthOpenY':.38,'ParamMouthWidth':.5},
 'wink_left':{'ParamEyeLOpen':0.,'ParamEyeLSmile':.9,'ParamEyeROpen':.9,'ParamEyeRSmile':.35,'ParamMouthForm':.9,'ParamMouthOpenY':.3,'ParamMouthWidth':.3},
 'wink_right':{'ParamEyeROpen':0.,'ParamEyeRSmile':.9,'ParamEyeLOpen':.9,'ParamEyeLSmile':.35,'ParamMouthForm':.9,'ParamMouthOpenY':.3,'ParamMouthWidth':.3},
 'worried':{'ParamEyeLOpen':.75,'ParamEyeROpen':.75,'ParamBrowLY':.45,'ParamBrowRY':.45,'ParamBrowLAngle':-.8,'ParamBrowRAngle':.8,'ParamBrowLForm':.4,'ParamBrowRForm':.4,'ParamMouthForm':-.9,'ParamMouthOpenY':.16,'ParamMouthWidth':-.3},
 'serious':{'ParamEyeLOpen':.95,'ParamEyeROpen':.95,'ParamBrowLAngle':.55,'ParamBrowRAngle':-.55,'ParamBrowLY':-.25,'ParamBrowRY':-.25,'ParamMouthForm':-.65,'ParamMouthWidth':-.2},
 'happy':{'ParamEyeLOpen':.58,'ParamEyeROpen':.58,'ParamEyeLSmile':1.,'ParamEyeRSmile':1.,'ParamMouthForm':1.,'ParamMouthOpenY':.64,'ParamMouthWidth':.65,'ParamBrowLY':.2,'ParamBrowRY':.2},
 'shy':{'ParamEyeLOpen':.65,'ParamEyeROpen':.65,'ParamEyeLSmile':.3,'ParamEyeRSmile':.3,'ParamBrowLForm':.5,'ParamBrowRForm':.5,'ParamBrowLY':.25,'ParamBrowRY':.25,'ParamMouthForm':.5,'ParamMouthOpenY':.12,'ParamMouthWidth':-.15},
 'surprised':{'ParamBrowLY':1.,'ParamBrowRY':1.,'ParamBrowLForm':-.4,'ParamBrowRForm':-.4,'ParamMouthOpenY':.95,'ParamMouthForm':-.1,'ParamMouthWidth':-.8},
 'curious':{'ParamEyeLOpen':.75,'ParamEyeROpen':1.,'ParamBrowLY':.9,'ParamBrowRY':-.2,'ParamBrowLAngle':-.4,'ParamBrowRAngle':.15,'ParamMouthForm':-.25,'ParamMouthOpenY':.22,'ParamMouthWidth':-.4},
 'sleepy':{'ParamEyeLOpen':.27,'ParamEyeROpen':.27,'ParamBrowLY':-.35,'ParamBrowRY':-.35,'ParamMouthForm':-.15,'ParamMouthOpenY':.12,'ParamMouthWidth':-.25},
 'downcast':{'ParamEyeLOpen':.48,'ParamEyeROpen':.48,'ParamBrowLAngle':-.9,'ParamBrowRAngle':.9,'ParamBrowLY':.1,'ParamBrowRY':.1,'ParamMouthForm':-1.,'ParamMouthWidth':-.4},
 'annoyed':{'ParamEyeLOpen':.55,'ParamEyeROpen':.55,'ParamBrowLY':-.5,'ParamBrowRY':-.5,'ParamBrowLAngle':.8,'ParamBrowRAngle':-.8,'ParamMouthForm':-.9,'ParamMouthWidth':.1},
 'laugh':{'ParamEyeLOpen':.13,'ParamEyeROpen':.13,'ParamEyeLSmile':1.,'ParamEyeRSmile':1.,'ParamBrowLY':.5,'ParamBrowRY':.5,'ParamMouthForm':1.,'ParamMouthOpenY':.95,'ParamMouthWidth':.9},
 'angry':{'ParamEyeLOpen':.8,'ParamEyeROpen':.8,'ParamBrowLY':-.85,'ParamBrowRY':-.85,'ParamBrowLAngle':1.,'ParamBrowRAngle':-1.,'ParamBrowLForm':-.5,'ParamBrowRForm':-.5,'ParamMouthForm':-1.,'ParamMouthOpenY':.42,'ParamMouthWidth':.6},
 'pout':{'ParamEyeLOpen':.72,'ParamEyeROpen':.72,'ParamBrowLY':-.4,'ParamBrowRY':-.4,'ParamBrowLAngle':.5,'ParamBrowRAngle':-.5,'ParamMouthForm':-1.,'ParamMouthOpenY':.02,'ParamMouthWidth':-.85},
 'bashful':{'ParamEyeLOpen':.5,'ParamEyeROpen':.5,'ParamEyeLSmile':.25,'ParamEyeRSmile':.25,'ParamBrowLAngle':-.45,'ParamBrowRAngle':.45,'ParamBrowLY':.3,'ParamBrowRY':.3,'ParamMouthForm':.65,'ParamMouthOpenY':.1,'ParamMouthWidth':-.3},
 'expectant':{'ParamEyeLOpen':1.,'ParamEyeROpen':1.,'ParamEyeLSmile':.15,'ParamEyeRSmile':.15,'ParamBrowLY':.65,'ParamBrowRY':.65,'ParamMouthForm':.85,'ParamMouthOpenY':.4,'ParamMouthWidth':.1},
 'thinking':{'ParamEyeLOpen':.8,'ParamEyeROpen':.8,'ParamBrowLY':.55,'ParamBrowRY':-.2,'ParamBrowLAngle':-.2,'ParamBrowRAngle':-.2,'ParamMouthForm':-.4,'ParamMouthWidth':-.55},
 'skeptical':{'ParamEyeLOpen':.55,'ParamEyeROpen':.85,'ParamBrowLY':.8,'ParamBrowRY':-.5,'ParamBrowLAngle':-.55,'ParamBrowRAngle':-.45,'ParamMouthForm':-.8,'ParamMouthWidth':-.35},
 'embarrassed':{'ParamEyeLOpen':.72,'ParamEyeROpen':.72,'ParamBrowLAngle':-.6,'ParamBrowRAngle':.6,'ParamBrowLY':.5,'ParamBrowRY':.5,'ParamMouthForm':.15,'ParamMouthOpenY':.38,'ParamMouthWidth':.15},
 'yawning':{'ParamEyeLOpen':.13,'ParamEyeROpen':.13,'ParamBrowLY':-.3,'ParamBrowRY':-.3,'ParamMouthForm':-.15,'ParamMouthOpenY':1.,'ParamMouthWidth':-.75},
 'resting':{'ParamEyeLOpen':0.,'ParamEyeROpen':0.,'ParamEyeLSmile':.12,'ParamEyeRSmile':.12,'ParamBrowLY':-.1,'ParamBrowRY':-.1,'ParamMouthForm':.2}
}
FACE_VALUES={name:{**FACE_BASE,**values} for name,values in FACE_VALUES.items()}
FACE_BLUSH={'shy':.42,'bashful':.62,'embarrassed':.48,'happy':.12,'laugh':.16,'pout':.12}
FACE_GAZE={'bashful':(.18,-.35),'thinking':(-.55,.38),'skeptical':(.4,0.),'downcast':(0.,-.32),'shy':(.15,-.16),'pout':(.35,-.08)}
