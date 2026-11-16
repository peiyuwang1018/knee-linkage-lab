"""Planar circular pitch-path routing with fixed outside-inward idlers.

Main sprockets turn clockwise along the ordered path, idlers counterclockwise.
All lengths are mm. This is a mean pitch-path model, not discrete tooth contact.
"""
import math

TAU=2*math.pi

def sub(a,b):return (a[0]-b[0],a[1]-b[1])
def dot(a,b):return a[0]*b[0]+a[1]*b[1]
def cross(a,b):return a[0]*b[1]-a[1]*b[0]
def distance(p,a,b):
    v=sub(b,a);n=dot(v,v)
    t=max(0,min(1,dot(sub(p,a),v)/n)) if n else 0
    return math.hypot(p[0]-a[0]-t*v[0],p[1]-a[1]-t*v[1])

def tangent(a,b):
    delta=sub(b['center'],a['center']);d=math.hypot(*delta)
    # Signed radius: material lies right of travel for main wheels, left for idlers.
    ra=a['r']*a['side'];rb=b['r']*b['side'];k=(ra-rb)/d
    if abs(k)>=1:raise ValueError('No common tangent')
    vx,vy=delta[0]/d,delta[1]/d;h=math.sqrt(1-k*k)
    n=(k*vx-h*vy,k*vy+h*vx);u=(n[1],-n[0])
    p=[a['center'][i]+ra*n[i] for i in (0,1)];q=[b['center'][i]+rb*n[i] for i in (0,1)]
    return dict(start=p,end=q,unit=u,length=math.hypot(*sub(q,p)))

def route(circles,clearance=0,plate_height=0,validate=True):
    edges=[tangent(a,circles[(i+1)%len(circles)]) for i,a in enumerate(circles)]
    arcs=[];total=sum(e['length'] for e in edges)
    for i,c in enumerate(circles):
        a=sub(edges[i-1]['end'],c['center']);b=sub(edges[i]['start'],c['center'])
        start=math.atan2(a[1],a[0]);end=math.atan2(b[1],b[0]);direction=-c['side']
        sweep=(direction*(end-start))%TAU
        if min(sweep,TAU-sweep)<1e-8:sweep=0
        if c['side']<0 and sweep>math.pi+1e-7:raise ValueError('Idler branch reversed')
        arcs.append(dict(center=c['center'],radius=c['r'],start=start,sweep=sweep,direction=direction,name=c['name']))
        total+=c['r']*sweep
    if validate:
        for i,c in enumerate(circles):
            for other in circles[i+1:]:
                if math.hypot(*sub(c['center'],other['center'])) < c['outer']+other['outer']+clearance-1e-7:
                    raise ValueError('Wheel envelopes overlap')
        for i,e in enumerate(edges):
            for j,c in enumerate(circles):
                if j in (i,(i+1)%len(circles)):continue
                if distance(c['center'],e['start'],e['end']) < c['outer']+plate_height/2+clearance-1e-7:
                    raise ValueError('Chain span / wheel interference')
            for j,f in enumerate(edges[:i]):
                v=sub(e['end'],e['start']);w=sub(f['end'],f['start']);den=cross(v,w)
                if abs(den)>1e-8:
                    offset=sub(f['start'],e['start']);t=cross(offset,w)/den;u=cross(offset,v)/den
                    if 1e-8<t<1-1e-8 and 1e-8<u<1-1e-8:raise ValueError('Chain spans cross')
                if not ({i,(i+1)%len(circles)} & {j,(j+1)%len(circles)}):
                    gap=min(distance(p,e['start'],e['end']) for p in [f['start'],f['end']])
                    gap=min(gap,*(distance(p,f['start'],f['end']) for p in [e['start'],e['end']]))
                    if gap<plate_height+clearance-1e-7:raise ValueError('Chain spans too close')
    for i,e in enumerate(edges):
        e['span']='A' if circles[i]['name'] in ('Input','I-A') else 'B'
    return dict(circles=circles,edges=edges,arcs=arcs,length_mm=total,
                wrap1_deg=math.degrees(arcs[0]['sweep']),
                wrap2_deg=math.degrees(next(a for a in arcs if a['name']=='Output')['sweep']))

def build(center,r1,r2,ri,outer1,outer2,outer_i,mode,x,depth,clearance,plate_height):
    a=math.asin((r2-r1)/center)
    # x is a coordinate along the input-output centerline; travel is normal to it.
    y0=(r1+ri+math.sin(a)*x)/math.cos(a)
    y=y0-depth
    circles=[dict(name='Input',center=[0,0],r=r1,outer=outer1,side=1)]
    if mode=='dual':circles.append(dict(name='I-A',center=[x,y],r=ri,outer=outer_i,side=-1))
    circles.append(dict(name='Output',center=[center,0],r=r2,outer=outer2,side=1))
    if mode in ('single','dual'):circles.append(dict(name='I-B',center=[x,-y],r=ri,outer=outer_i,side=-1))
    if mode=='dual' and y<=0:raise ValueError('Mirrored idlers crossed centerline')
    out=route(circles,clearance,plate_height)
    out.update(depth_mm=depth,x_mm=x,initial_y_mm=y0,mode=mode)
    return out

def prepare(c,g,item):
    p=item['pitch_mm'];ri=p*c.idler_teeth/TAU
    tip_i=p/math.sin(math.pi/c.idler_teeth)+1.25*p-item['roller_mm']
    args=(c.center_mm,g['r1_mm'],g['r2_mm'],ri,g['tip1_mm']/2,g['tip2_mm']/2,tip_i/2,c.idler_mode)
    def at(x,h):
        r=build(*args,x,h,c.idler_clearance_mm,item['plate_height_mm'])
        if min(r['wrap1_deg'],r['wrap2_deg'])<c.min_wrap_deg-1e-7:raise ValueError('Insufficient drive-wheel wrap')
        return r
    if c.idler_mode=='none':return dict(options=[],at=at,max_length=g['route_mm'])
    fractions=[.2+.05*i for i in range(13)] if c.idler_position=='auto' else [c.idler_x_fraction]
    options=[]
    for f in fractions:
        x=f*c.center_mm
        try:r0=at(x,0)
        except ValueError:continue
        lo=0;last=r0
        for j in range(1,25):
            h=c.idler_travel_mm*j/24
            try:r=at(x,h)
            except ValueError:
                hi=h
                for _ in range(14):
                    mid=(lo+hi)/2
                    try:r=at(x,mid);lo=mid;last=r
                    except ValueError:hi=mid
                break
            lo=h;last=r
        options.append(dict(x=x,depth=lo,max_length=last['length_mm'],base=r0))
    return dict(options=options,at=at,max_length=max((o['max_length'] for o in options),default=g['route_mm']))

def fit(prepared,target):
    best=None
    for o in prepared['options']:
        if not o['base']['length_mm']-1e-6<=target<=o['max_length']+1e-6:continue
        lo=0;hi=o['depth'];r=o['base']
        for _ in range(32):
            h=(lo+hi)/2;r=prepared['at'](o['x'],h)
            if r['length_mm']<target:lo=h
            else:hi=h
        r=prepared['at'](o['x'],(lo+hi)/2)
        r['length_error_mm']=r['length_mm']-target
        center=next(c['center'][0] for c in r['circles'] if c['name']=='Output')
        score=lambda item:(item['depth_mm'],abs(item['x_mm']-center/2))
        if best is None or score(r)<score(best):best=r
    return best

def plain(c,g):
    # Valid mean route even when packaging limits fail, for an honest base preview.
    circles=[dict(name='Input',center=[0,0],r=g['r1_mm'],outer=g['tip1_mm']/2,side=1),
             dict(name='Output',center=[c.center_mm,0],r=g['r2_mm'],outer=g['tip2_mm']/2,side=1)]
    r=route(circles,validate=False);r.update(mode='none',depth_mm=0,x_mm=None,initial_y_mm=None)
    return r
