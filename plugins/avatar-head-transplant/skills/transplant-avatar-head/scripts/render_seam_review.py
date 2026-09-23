"""Visualize a pending seam geometry proposal without modifying Blender."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Line3DCollection,Poly3DCollection


def render_review(input_json, output_png):
    data=json.loads(Path(input_json).read_text(encoding='utf8'))
    if data['schema']!=1 or data['stage']!='geometry':raise ValueError('Expected a geometry review export')
    axes=np.asarray(data['view_axes']);origin=np.asarray(data['view_origin'])
    unit=data['meters_per_world_unit']*1000
    project=lambda p:(np.asarray(p,float)-origin)@axes.T*unit
    body=project([p['body'] for p in data['pairs']]);head=project([p['head'] for p in data['pairs']]);target=project([p['target'] for p in data['pairs']])
    colors={data['body']:'#187cad',data['head']:'#e67e22'};green='#15914c'
    points=np.concatenate([body,head,target]);center=(points.min(axis=0)+points.max(axis=0))/2
    span=max(np.ptp(points,axis=0))*1.75
    if span<=0:raise ValueError('Degenerate seam proposal')
    fig=plt.figure(figsize=(15,10));grid=fig.add_gridspec(2,3,hspace=.2,wspace=.16)
    def closed(p):return np.vstack([p,p[0]])
    for row in range(2):
        for col in range(3):
            ax=fig.add_subplot(grid[row,col],projection='3d' if col==2 else None)
            for name,patch in data['patches'].items():
                coords=project(patch['current' if row==0 else 'proposed']);edges=np.asarray(patch['edges'],int).reshape(-1,2)
                if col<2:
                    indices=[0,2] if col==0 else [1,2]
                    if len(edges):ax.add_collection(LineCollection(coords[edges][:,:,indices],colors=colors[name],linewidths=.65,alpha=.4))
                else:
                    if len(edges):ax.add_collection3d(Line3DCollection(coords[edges],colors=colors[name],linewidths=.45,alpha=.3))
                    if row==1:ax.add_collection3d(Poly3DCollection([coords[f] for f in patch['faces']],facecolors=colors[name],edgecolors='none',alpha=.13))
            paths=[(body,colors[data['body']]),(head,colors[data['head']]),(target,green)] if row==0 else [(target,green)]
            for path,color in paths:
                p=closed(path)
                if col<2:ax.plot(p[:,indices[0]],p[:,2],color=color,lw=2);ax.scatter(path[:,indices[0]],path[:,2],c=color,s=12)
                else:ax.plot(p[:,0],p[:,1],p[:,2],color=color,lw=2)
            if row==0:
                for a,b,t in zip(body,head,target):
                    p=np.array([a,t,b])
                    if col<2:ax.plot(p[:,indices[0]],p[:,2],color='#777777',ls='--',lw=.7)
                    else:ax.plot(p[:,0],p[:,1],p[:,2],color='#777777',ls='--',lw=.7)
            # Stable pair numbers allow feedback by region without vertex IDs.
            step=max(1,len(target)//12)
            for i in range(0,len(target),step):
                p=target[i]
                if col<2:ax.annotate(str(i+1),(p[indices[0]],p[2]),xytext=(3,4),textcoords='offset points',fontsize=8,color=green)
                else:ax.text(*p,str(i+1),fontsize=7,color=green)
            if col<2:
                ax.set_xlim(center[indices[0]]-span/2,center[indices[0]]+span/2);ax.set_ylim(center[2]-span/2,center[2]+span/2)
                ax.set_aspect('equal');ax.grid(alpha=.13);ax.set_xlabel(('Right' if col==0 else 'Depth')+' (mm)');ax.set_ylabel('Up (mm)')
            else:
                ax.set_xlim(center[0]-span/2,center[0]+span/2);ax.set_ylim(center[1]-span/2,center[1]+span/2);ax.set_zlim(center[2]-span/2,center[2]+span/2)
                ax.set_box_aspect((1,1,1));ax.view_init(elev=20,azim=-65);ax.set_xlabel('Right');ax.set_ylabel('Depth');ax.set_zlabel('Up')
            ax.set_title(('Current + movement' if row==0 else 'Proposed surface')+' / '+['front','side','oblique'][col])
    fig.suptitle('Neck geometry review — '+data['review_id'],fontsize=16,y=.97)
    fig.legend(handles=[Line2D([0],[0],color='#187cad',label='Body'),Line2D([0],[0],color='#e67e22',label='Head'),Line2D([0],[0],color=green,label='Shared target boundary'),Line2D([0],[0],color='#777777',ls='--',label='Pair movement')],loc='upper center',bbox_to_anchor=(.5,.94),ncol=4,frameon=False)
    status='Explicit local targets supplied' if data['explicit_local_targets_supplied'] else 'MIDPOINT-ONLY DISCUSSION DRAFT: surrounding shaping not yet specified'
    note=' | '.join(str(n) for n in data['notes'])
    fig.text(.5,.045,f"{len(target)} pairs | Separate final meshes; no final seam weld | Approval pending\n{status}",ha='center',fontsize=10)
    if note:fig.text(.5,.014,note[:190],ha='center',fontsize=8)
    fig.subplots_adjust(top=.87,bottom=.13,left=.06,right=.97)
    path=Path(output_png);path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=150);plt.close(fig)
    return {'image':str(path),'review_id':data['review_id'],'approval_status':'pending'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('input_json');parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(render_review(args.input_json,args.output)))
