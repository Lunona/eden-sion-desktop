const CATALOG={calm:['neutral','resting'],joy:['happy','laugh','closed_smile'],warm:['soft_smile','closed_smile'],care:['worried','serious'],curious:['curious','skeptical'],thoughtful:['thinking'],shy:['shy','bashful','embarrassed'],surprise:['surprised','expectant'],sad:['downcast'],sleepy:['sleepy','yawning'],playful:['wink_left','wink_right','pout']};
function visualPlan(r){
 const defaults={smile:'warm',thoughtful:'thoughtful',concerned:'care',sleepy:'sleepy'};
 const fallback=typeof r.expression==='string'&&Object.hasOwn(defaults,r.expression)?defaults[r.expression]:'calm';
 const v=r.visual&&typeof r.visual==='object'?r.visual:{};
 const emotion=typeof v.emotion==='string'&&Object.hasOwn(CATALOG,v.emotion)?v.emotion:fallback;
 return {emotion,face:CATALOG[emotion].includes(v.face)?v.face:CATALOG[emotion][0],intensity:Number.isFinite(v.intensity)?Math.max(.1,Math.min(.85,v.intensity)):.45,action:Number.isInteger(v.action)&&[0,1,2,3,8,11,12,17,18].includes(v.action)?v.action:r.motion==='wave'?18:0,side:['left','right'].includes(v.side)?v.side:'auto'};
}
const INSTRUCTION='另加visual对象，表示诗音对这次对话的回应，不把用户情绪当成她被冒犯：emotion选calm/joy/warm/care/curious/thoughtful/shy/surprise/sad/sleepy/playful，intensity为0.1至0.85，face选该情绪相应的已有表情（微笑soft_smile、开心happy、开怀laugh、担忧worried、思考thinking、疑惑curious、害羞shy/bashful、惊讶surprised、期待expectant、低落downcast、困倦sleepy、左/右眨眼wink_left/wink_right），action通常0，打招呼18，牵手回应11，袖口回应12，脚边回应17，side选left/right。谨慎使用较强动作；转述、例句、程序报错不等于对你的攻击。';
module.exports={visualPlan,INSTRUCTION,CATALOG};
