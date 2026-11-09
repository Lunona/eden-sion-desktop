function placeCompact(pet,area){
  const pad=8,gap=6;
  const height=Math.round(Math.max(210,Math.min(310,area.height*.34)));
  const width=Math.min(380,area.width-pad*2);
  const fit=Math.min(1,(area.height-height-gap-pad*2)/pet.height,(area.width-pad*2)/pet.width);
  const pw=Math.max(1,Math.round(pet.width*fit)),ph=Math.max(1,Math.round(pet.height*fit));
  const bound=(n,min,max)=>Math.round(Math.max(min,Math.min(max,n)));
  const x=bound(pet.x+(pet.width-pw)/2,area.x+pad,area.x+area.width-pad-pw);
  const y=bound(pet.y,area.y+pad,area.y+area.height-pad-ph-height-gap);
  return {pet:{x,y,width:pw,height:ph},chat:{x:bound(x+pw/2-width/2,area.x+pad,area.x+area.width-pad-width),y:y+ph+gap,width,height}};
}
module.exports={placeCompact};
