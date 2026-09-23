"""Render exported Basis geometry using standard Python + numpy + matplotlib."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D


def transform(points, matrix):
    p,m=np.asarray(points,float),np.asarray(matrix,float)
    return p @ m[:3,:3].T + m[:3,3]


def section_segments(vertices, triangles):
    """Actual triangle/center-plane intersections, including interior face cuts."""
    vertices=np.asarray(vertices,float)
    epsilon=max(float(np.linalg.norm(np.ptp(vertices,axis=0)))*1e-9,1e-14)
    segments=[]
    for ids in triangles:
        tri=vertices[np.asarray(ids,int)];dist=tri[:,0]
        if np.all(dist>epsilon) or np.all(dist < -epsilon):continue
        if np.all(np.abs(dist)<=epsilon):
            segments.extend([[tri[i],tri[(i+1)%3]] for i in range(3)])
            continue
        points=[]
        for i in range(3):
            a,b=tri[i],tri[(i+1)%3];da,db=a[0],b[0]
            if abs(da)<=epsilon:points.append(a)
            if (da>epsilon and db < -epsilon) or (da < -epsilon and db>epsilon):
                points.append(a+(b-a)*(da/(da-db)))
        unique=[]
        for p in points:
            if not any(np.linalg.norm(p-q)<=epsilon for q in unique):unique.append(p)
        if len(unique)==2:segments.append(unique)
    return np.asarray(segments,float).reshape(-1,2,3)


def render_comparison(input_json, output_png):
    data=json.loads(Path(input_json).read_text(encoding='utf8'))
    if data['schema']!=1:raise ValueError('Unsupported alignment preview schema')
    axes=np.asarray(data['view_axes'],float);origin=np.asarray(data['view_origin'],float)
    unit=float(data['meters_per_world_unit'])*1000
    if unit<=0 or not np.isfinite(unit):raise ValueError('Invalid physical unit scale')
    project=lambda p:(np.asarray(p,float)-origin)@axes.T*unit
    reference=project(data['reference']['vertices'])
    donor=[project(transform(data['donor']['vertices'],data[key])) for key in ['previous_matrix','fit_matrix']]
    target=project(data['target_landmarks'])
    fitted=[project(transform(data['source_landmarks'],data[key])) for key in ['previous_matrix','fit_matrix']]
    all_points=np.concatenate([reference,*donor,target,*fitted])
    low,high=all_points.min(axis=0),all_points.max(axis=0)
    span=max(high-low)*1.12
    center=(low+high)/2
    metrics={'uniform_scale':float(np.linalg.det(np.asarray(data['fit_matrix'])[:3,:3])**(1/3)),
             'geometry_state':data['geometry_state'],'landmarks':[]}
    for i,label in enumerate(data['labels']):
        delta=fitted[1][i]-target[i]
        metrics['landmarks'].append({'label':label,'before_distance_mm':float(np.linalg.norm(fitted[0][i]-target[i])),
                                    'after_distance_mm':float(np.linalg.norm(delta)),
                                    'after_right_depth_up_mm':delta.tolist()})
    fig=plt.figure(figsize=(12,13))
    grid=fig.add_gridspec(3,2,height_ratios=[1,1,.38],hspace=.28,wspace=.18)
    colors=['#e67e22','#187cad']
    for row in range(2):
        for col in range(2):
            ax=fig.add_subplot(grid[row,col]);indices=[0,2] if col==0 else [1,2]
            for geometry,coords,color in [(data['reference'],reference,colors[0]),(data['donor'],donor[row],colors[1])]:
                if col==0:
                    edges=np.asarray(geometry['edges'],int).reshape(-1,2)
                    lines=coords[edges]
                else:lines=section_segments(coords,geometry['triangles'])
                if len(lines):ax.add_collection(LineCollection(lines[:,:,indices],colors=color,linewidths=.45 if col==0 else 1.15,alpha=.35 if col==0 else .95))
            for coords,color,marker in [(target,colors[0],'o'),(fitted[row],colors[1],'x')]:
                ax.scatter(coords[:,indices[0]],coords[:,2],s=24,c=color,marker=marker,zorder=4)
            for i in range(len(target)):
                ax.plot([target[i,indices[0]],fitted[row][i,indices[0]]],[target[i,2],fitted[row][i,2]],color='#777777',lw=.7,ls=':')
            ax.set_xlim(center[indices[0]]-span/2,center[indices[0]]+span/2)
            ax.set_ylim(center[2]-span/2,center[2]+span/2)
            ax.set_aspect('equal');ax.grid(alpha=.18)
            ax.set_xlabel(('Right' if col==0 else 'Depth')+' (mm)');ax.set_ylabel('Up (mm)')
            ax.set_title(('Before' if row==0 else 'Candidate')+' — '+('front wire projection' if col==0 else 'center-plane profile'))
    table_ax=fig.add_subplot(grid[2,:]);table_ax.axis('off')
    rows=[]
    for item in metrics['landmarks']:
        rows.append([item['label'],f"{item['before_distance_mm']:.2f}",f"{item['after_distance_mm']:.2f}",*[f'{v:+.2f}' for v in item['after_right_depth_up_mm']]])
    table=table_ax.table(cellText=rows,colLabels=['Landmark','Before error','After error','Right delta','Depth delta','Up delta'],loc='center',cellLoc='center')
    table.auto_set_font_size(False);table.set_fontsize(9);table.scale(1,1.6)
    fig.suptitle('Head alignment review — uniform fit proposal',fontsize=16,y=.975)
    fig.legend(handles=[Line2D([0],[0],color=colors[0],label='Recipient original head'),Line2D([0],[0],color=colors[1],label='Donor head')],loc='upper center',bbox_to_anchor=(.5,.951),ncol=2,frameon=False)
    fig.text(.5,.025,f"Shared axes and scale in all views | Uniform scale {metrics['uniform_scale']:.6f}\nLandmark errors in mm; geometry is Basis. Candidate is not applied to the scene.",ha='center',fontsize=10)
    fig.subplots_adjust(top=.90,bottom=.075)
    path=Path(output_png);path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=150);plt.close(fig)
    metrics_path=path.with_suffix('.metrics.json');metrics_path.write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8')
    return {'image':str(path),'metrics':str(metrics_path)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('input_json');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(render_comparison(args.input_json,args.output),ensure_ascii=False))
