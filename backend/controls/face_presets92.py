FACE_LABELS={'neutral':'默认','soft_smile':'微笑','closed_smile':'闭眼笑','wink_left':'左眨眼','wink_right':'右眨眼','worried':'担忧','serious':'严肃','happy':'开心笑','shy':'害羞','surprised':'惊讶','curious':'疑惑','sleepy':'困倦','downcast':'失落','annoyed':'轻微不满'}
FACE_BASE={'ParamEyeLOpen':1.,'ParamEyeROpen':1.,'ParamEyeLSmile':0.,'ParamEyeRSmile':0.,'ParamMouthForm':0.,'ParamMouthOpenY':0.,'ParamMouthWidth':0.}
for side in ['L','R']:
 for tail in ['X','Y','Angle','Form']:FACE_BASE['ParamBrow'+side+tail]=0.
FACE_VALUES={
 'neutral':{},
 'soft_smile':{'ParamEyeLOpen':.88,'ParamEyeROpen':.88,'ParamEyeLSmile':.45,'ParamEyeRSmile':.45,'ParamMouthForm':.8,'ParamMouthOpenY':.10,'ParamMouthWidth':.3},
 'closed_smile':{'ParamEyeLOpen':0.,'ParamEyeROpen':0.,'ParamEyeLSmile':.8,'ParamEyeRSmile':.8,'ParamMouthForm':.8,'ParamMouthOpenY':.10,'ParamMouthWidth':.3},
 'wink_left':{'ParamEyeLOpen':0.,'ParamEyeLSmile':.5,'ParamEyeRSmile':.25,'ParamMouthForm':.55,'ParamMouthOpenY':.08},
 'wink_right':{'ParamEyeROpen':0.,'ParamEyeRSmile':.5,'ParamEyeLSmile':.25,'ParamMouthForm':.55,'ParamMouthOpenY':.08},
 'worried':{'ParamEyeLOpen':.7,'ParamEyeROpen':.7,'ParamBrowLY':.35,'ParamBrowRY':.35,'ParamBrowLAngle':-.65,'ParamBrowRAngle':.65,'ParamMouthForm':-.75},
 'serious':{'ParamEyeLOpen':.9,'ParamEyeROpen':.9,'ParamBrowLAngle':.5,'ParamBrowRAngle':-.5,'ParamBrowLY':-.3,'ParamBrowRY':-.3,'ParamMouthForm':-.6},
 'happy':{'ParamEyeLOpen':.65,'ParamEyeROpen':.65,'ParamEyeLSmile':1.,'ParamEyeRSmile':1.,'ParamMouthForm':1.,'ParamMouthOpenY':.24,'ParamMouthWidth':.55},
 'shy':{'ParamEyeLOpen':.65,'ParamEyeROpen':.65,'ParamEyeLSmile':.35,'ParamEyeRSmile':.35,'ParamBrowLForm':.4,'ParamBrowRForm':.4,'ParamMouthForm':.5,'ParamMouthOpenY':.08,'ParamMouthWidth':.15},
 'surprised':{'ParamBrowLY':.9,'ParamBrowRY':.9,'ParamBrowLForm':-.3,'ParamBrowRForm':-.3,'ParamMouthOpenY':.55,'ParamMouthForm':0.,'ParamMouthWidth':-.9},
 'curious':{'ParamEyeLOpen':.8,'ParamBrowLY':.8,'ParamBrowRY':-.1,'ParamBrowLAngle':-.3,'ParamBrowRAngle':.05,'ParamMouthForm':-.2,'ParamMouthOpenY':.06,'ParamMouthWidth':-.2},
 'sleepy':{'ParamEyeLOpen':.32,'ParamEyeROpen':.32,'ParamBrowLY':-.25,'ParamBrowRY':-.25,'ParamMouthForm':-.05,'ParamMouthOpenY':.07,'ParamMouthWidth':-.2},
 'downcast':{'ParamEyeLOpen':.62,'ParamEyeROpen':.62,'ParamBrowLAngle':-.8,'ParamBrowRAngle':.8,'ParamMouthForm':-1.},
 'annoyed':{'ParamEyeLOpen':.65,'ParamEyeROpen':.65,'ParamBrowLY':-.5,'ParamBrowRY':-.5,'ParamBrowLAngle':.8,'ParamBrowRAngle':-.8,'ParamMouthForm':-.85}}
FACE_VALUES={key:{**FACE_BASE,**values} for key,values in FACE_VALUES.items()}
