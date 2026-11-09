"""Fixed 60Hz Cubism particle chains, including relative-angle tip outputs.

The existing two-vertex groups retain the previous arithmetic. Hair chains use
the SDK's parent-segment angle for vertex 2, rather than a duplicate head drive.
Reference: Live2D/CubismWebFramework src/physics/cubismphysics.ts.
"""
import json,math
import numpy as np
from physics_pose_preview import Physics as LegacyPhysics
from runtime_preview import angle
from rig_limits import clamp_value

class Physics:
 inputs=LegacyPhysics.inputs
 def __init__(self,core,settings=None):
  self.c=core;self.settings=settings if settings is not None else json.loads((core.runtime/'Sion_H20R12.physics3.json').read_text('utf-8'))['PhysicsSettings'];self.state=[];self.ranges={};self.raw_ranges={}
  for setting in self.settings:
   root,gravity=self.inputs(setting,core.defaults);n=len(setting['Vertices']);positions=np.zeros((n,2));positions[0]=root
   for i in range(1,n):positions[i]=positions[i-1]+gravity*setting['Vertices'][i]['Radius']
   self.state.append({'positions':positions,'velocities':np.zeros((n,2)),'gravities':np.tile(gravity,(n,1))})
 def step(self,values):
  result={};context=dict(values)
  for setting,st in zip(self.settings,self.state):
   root,gravity=self.inputs(setting,context);p=st['positions'];p[0]=root
   for i in range(1,len(p)):
    vertex=setting['Vertices'][i];delay=vertex['Delay']*.5;direction=p[i]-p[i-1];rad=angle(st['gravities'][i],gravity)/5
    # Preserve the SDK's in-place rotation arithmetic.
    x=math.cos(rad)*direction[0]-direction[1]*math.sin(rad);y=math.sin(rad)*x+direction[1]*math.cos(rad)
    old=p[i].copy();position=p[i-1]+np.array([x,y])+st['velocities'][i]*delay+gravity*vertex['Acceleration']*delay*delay
    d=position-p[i-1];d/=max(np.linalg.norm(d),1e-12);position=p[i-1]+d*vertex['Radius']
    if abs(position[0])<.001*setting['Normalization']['Position']['Maximum']:position[0]=0
    p[i]=position;st['velocities'][i]=(position-old)/delay*vertex['Mobility'] if delay else np.zeros(2);st['gravities'][i]=gravity
   for output in setting['Output']:
    i=output['VertexIndex'];parent=p[i-1]-p[i-2] if i>=2 else np.array([0.,1.]);assert output['Type']=='Angle'
    value=angle(parent,p[i]-p[i-1])*output['Scale']*(-1 if output['Reflect'] else 1);ident=output['Destination']['Id'];raw=self.raw_ranges.setdefault(ident,[0.,0.]);raw[0]=min(raw[0],value);raw[1]=max(raw[1],value);param=self.c.params[ident];value=clamp_value(value,float(param.getMinimumValue()),float(param.getMaximumValue()));weight=output['Weight']/100
    result[ident]=context.get(ident,float(param.getDefaultValue()))*(1-weight)+value*weight;context[ident]=result[ident];extent=self.ranges.setdefault(ident,[0.,0.]);extent[0]=min(extent[0],result[ident]);extent[1]=max(extent[1],result[ident])
  return result
