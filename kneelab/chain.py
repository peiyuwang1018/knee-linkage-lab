"""Single-stage chain screening; SI forces, mm catalog geometry.

Smooth mean-radius model (R=p*z/2pi) preserves exact mean tooth ratio and
virtual power. Pitch circles and conservative tooth-tip estimates are reported
separately. Fixed reverse-bend idlers are placed by a circular pitch-path solve;
spring dynamics and discrete tooth contact remain outside this model.
"""
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
import csv
import io
import json
import math
from .model import Config, G, pose, quintic, rotate
from . import chain_route

CATALOG = json.loads(Path(__file__).with_name('chains.json').read_text())
ITEMS = {item['id']: item for item in CATALOG['items']}
TASK_KEYS = ('center_mm','shank_mm','q_start_deg','q_end_deg','half_cycle_s',
             'mass_kg','share','load_mode','load_factor')


@dataclass
class ChainConfig:
    chain_id: str = 'tsubaki35'
    input_teeth: int = 19
    output_teeth: int = 38
    links: int = 92
    center_mm: float = 300
    shank_mm: float = 340
    q_start_deg: float = -120
    q_end_deg: float = -15
    half_cycle_s: float = 2
    mass_kg: float = 70
    share: float = 0.5
    load_mode: str = 'constant'
    load_factor: float = 1
    prescribed_torque_nm: float = 100
    slack_n: float = 50
    load_margin: float = 1.25
    rating_multiplier: float = 1
    allowable_override_n: float = None
    efficiency: float = 0.95
    motor_rated_nm: float = 55
    motor_speed_rpm: float = 120
    input_max_mm: float = 100
    output_max_mm: float = 180
    width_max_mm: float = 20
    ratio_min: float = 1
    ratio_max: float = 2
    min_wrap_deg: float = 120
    takeup_mm: float = 8  # legacy v0.8 field; not used for idler routing
    idler_mode: str = 'dual'
    idler_teeth: int = 15
    idler_travel_mm: float = 100
    idler_clearance_mm: float = 2
    idler_position: str = 'auto'
    idler_x_fraction: float = 0.5
    links_min: int = 60
    links_max: int = 140
    input_teeth_min: int = 17
    input_teeth_max: int = 29
    custom_pitch_mm: float = 8
    custom_roller_mm: float = 5
    custom_plate_mm: float = 7.1
    custom_width_mm: float = 9.2
    custom_inner_width_mm: float = 3.16
    samples: int = 241

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data=None):
        if isinstance(data,cls): data=data.to_dict()
        if data is None: data={}
        if not isinstance(data,dict): raise ValueError('Chain config must be an object.')
        allowed={f.name for f in fields(cls)}
        unknown=set(data)-allowed
        if unknown: raise ValueError('Unknown chain parameters: '+', '.join(sorted(unknown)))
        c=cls(**{**data,'ratio_min':1})  # fixed lower bound; migrate v0.8 files
        for f in fields(cls):
            v=getattr(c,f.name)
            if f.name in ('chain_id','load_mode','idler_mode','idler_position'): continue
            if f.name=='allowable_override_n' and v is None: continue
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
                raise ValueError(f'{f.name} must be finite and numeric.')
        if c.chain_id not in ITEMS and c.chain_id!='custom': raise ValueError('Unknown chain type.')
        if c.idler_mode not in ('none','single','dual'): raise ValueError('Unknown idler layout.')
        if c.idler_position not in ('auto','fixed'): raise ValueError('Unknown idler placement mode.')
        if c.load_mode not in ('constant','trajectory','torque'): raise ValueError('Unknown load model.')
        limits={
            'input_teeth':(11,120),'output_teeth':(11,240),'links':(12,600),
            'center_mm':(50,1000),'shank_mm':(50,1000),'q_start_deg':(-175,175),
            'q_end_deg':(-175,175),'half_cycle_s':(.1,30),'mass_kg':(.1,1000),
            'share':(.01,1),'load_factor':(.01,5),'prescribed_torque_nm':(-5000,5000),
            'slack_n':(0,10000),'load_margin':(1,10),'rating_multiplier':(.01,1),
            'efficiency':(.1,1),'motor_rated_nm':(.1,5000),'motor_speed_rpm':(.1,10000),
            'input_max_mm':(10,500),'output_max_mm':(10,1000),'width_max_mm':(1,200),
            'ratio_min':(1,2),'ratio_max':(1,2),'min_wrap_deg':(90,180),
            'idler_teeth':(11,40),'idler_travel_mm':(0,300),'idler_clearance_mm':(0,30),'idler_x_fraction':(.15,.85),
            'takeup_mm':(0,100),'links_min':(12,600),'links_max':(12,600),
            'input_teeth_min':(11,80),'input_teeth_max':(11,80),
            'custom_pitch_mm':(3,25.4),'custom_roller_mm':(.5,20),
            'custom_plate_mm':(1,30),'custom_width_mm':(1,100),'custom_inner_width_mm':(.5,30),'samples':(21,501)}
        for k,(lo,hi) in limits.items():
            if not lo<=getattr(c,k)<=hi: raise ValueError(f'{k} must be in [{lo}, {hi}].')
        for k in ('input_teeth','output_teeth','links','links_min','links_max','input_teeth_min','input_teeth_max','idler_teeth','samples'):
            if not isinstance(getattr(c,k),int): raise ValueError(f'{k} must be an integer.')
        if not c.input_teeth<=c.output_teeth<=math.floor(c.input_teeth*c.ratio_max+1e-9):
            raise ValueError(f'Output teeth must be between {c.input_teeth} and {math.floor(c.input_teeth*c.ratio_max+1e-9)} for ratio 1–{c.ratio_max:g}.')
        if c.custom_inner_width_mm>=c.custom_width_mm: raise ValueError('Inner plate spacing must be below total chain width.')
        if c.links%2: raise ValueError('Use an even number of pitches; offset links are outside this model.')
        if c.samples%2!=1: raise ValueError('Use an odd sample count to include the turnaround frame.')
        for a,b in [('links_min','links_max'),('input_teeth_min','input_teeth_max'),('ratio_min','ratio_max')]:
            if getattr(c,a)>getattr(c,b): raise ValueError(f'{a} cannot exceed {b}.')
        if c.allowable_override_n is not None and not 0<c.allowable_override_n<=1e6:
            raise ValueError('Allowable-load override must be positive or empty.')
        if c.custom_roller_mm>=c.custom_pitch_mm: raise ValueError('Custom roller diameter must be below pitch.')
        return c


def chain_item(c):
    if c.chain_id=='custom':
        item=dict(id='custom',name='Custom chain',type='User-defined',pitch_mm=c.custom_pitch_mm,
                  roller_mm=c.custom_roller_mm,plate_height_mm=c.custom_plate_mm,
                  width_mm=c.custom_width_mm,inner_width_mm=c.custom_inner_width_mm,allowable_n=None,breaking_n=None,source=None,
                  note='User-defined geometry; obtain allowable load from the manufacturer.')
    else: item=dict(ITEMS[c.chain_id])
    item['rating_source']='user override' if c.allowable_override_n is not None else 'catalog'
    item['effective_allowable_n']=(c.allowable_override_n if c.allowable_override_n is not None else item['allowable_n'])
    if item['effective_allowable_n'] is not None:
        item['effective_allowable_n']*=c.rating_multiplier
    return item


def route_length(center, r1, r2):
    delta=r2-r1
    if center<=abs(delta): raise ValueError('Centers too close for external tangents.')
    return 2*math.sqrt(center*center-delta*delta)+math.pi*(r1+r2)+2*delta*math.asin(delta/center)


def geometry(c, item=None, routing=True):
    item=item or chain_item(c)
    p=item['pitch_mm']; z1=c.input_teeth; z2=c.output_teeth; C=c.center_mm
    r1=p*z1/(2*math.pi); r2=p*z2/(2*math.pi)
    pc1=p/math.sin(math.pi/z1); pc2=p/math.sin(math.pi/z2)
    # Handbook upper tooth-tip estimate. Actual finished sprocket drawing governs.
    tip1=pc1+1.25*p-item['roller_mm']; tip2=pc2+1.25*p-item['roller_mm']
    if C<=abs(r2-r1): raise ValueError('Centers too close for this sprocket pair.')
    angle=math.asin((r2-r1)/C)
    length=route_length(C,r1,r2)
    free_length=c.links*p
    # Invert smooth pitch-path length. None means even touching pitch circles
    # cannot accommodate this short chain; it is not stretched into place.
    low=max(r1+r2,abs(r2-r1)+1e-7); high=max(2000,free_length)
    fitted=None
    if free_length>=route_length(low,r1,r2):
        for _ in range(60):
            mid=(low+high)/2
            if route_length(mid,r1,r2)<free_length: low=mid
            else: high=mid
        fitted=(low+high)/2
    extra=free_length-length
    required=length/p
    next_even=2*math.ceil((required-1e-9)/2)
    g=dict(r1_mm=r1,r2_mm=r2,pitch1_mm=pc1,pitch2_mm=pc2,
        tip1_mm=tip1,tip2_mm=tip2,envelope1_mm=pc1+item['plate_height_mm'],
        envelope2_mm=pc2+item['plate_height_mm'],ratio=z2/z1,
        wrap1_deg=180-2*math.degrees(angle),wrap2_deg=180+2*math.degrees(angle),
        tangent_angle_rad=angle,route_mm=length,required_links=required,
        installed_mm=free_length,extra_path_mm=extra,free_center_mm=fitted,
        suggested_links=next_even,
        chordal_percent=100*(1-math.cos(math.pi/z1)),
        length_ok=-1e-7<=extra<=c.takeup_mm+1e-7,
        centers_clear=C>(tip1+tip2)/2)
    return route_geometry(c,g,item) if routing else g


def route_geometry(c,g,item,prepared=None):
    g=dict(g); base=chain_route.plain(c,g)
    prep=prepared or chain_route.prepare(c,g,item)
    target=c.links*item['pitch_mm']
    fitted=chain_route.fit(prep,target) if c.idler_mode!='none' else (base if abs(target-base['length_mm'])<=.1 else None)
    lo=max(c.links_min,2*math.ceil((g['required_links']-1e-9)/2))
    lo+=lo%2
    hi=min(c.links_max,2*math.floor((prep['max_length']+.000001)/item['pitch_mm']/2))
    g.update(route=fitted or base,route_solved=fitted is not None,length_ok=fitted is not None,
             route_preview_only=fitted is None, max_route_mm=prep['max_length'],
             feasible_links_min=lo if lo<=hi else None,feasible_links_max=hi if lo<=hi else None,
             suggested_links=lo if lo<=hi else g['suggested_links'],idler_mode=c.idler_mode,
             length_error_mm=fitted.get('length_error_mm',target-base['length_mm']) if fitted else None)
    if fitted:g.update(wrap1_deg=fitted['wrap1_deg'],wrap2_deg=fitted['wrap2_deg'])
    return g


def task_rows(c):
    # Reuse the existing leg/COM definition without inheriting rod singularities.
    task=Config(center_mm=c.center_mm,shank_mm=c.shank_mm)
    start,end=map(math.radians,(c.q_start_deg,c.q_end_deg)); T=c.half_cycle_s
    rows=[]
    for j in range(c.samples):
        t=2*T*j/(c.samples-1); back=t>T
        a,b=(end,start) if back else (start,end)
        f,fd,fdd=quintic((t-T)/T if back else t/T)
        q=a+(b-a)*f; qd=(b-a)*fd/T; qdd=(b-a)*fdd/T**2
        pos=pose(task,q,qd,qdd)
        factor=c.load_factor if c.load_mode!='trajectory' else 1+pos['acceleration']/G
        fz=c.mass_kg*c.share*G*factor
        tau=c.prescribed_torque_nm if c.load_mode=='torque' else pos['knee'][0]*fz
        rows.append(dict(t=t,q_deg=math.degrees(q),qdot=qd,qddot=qdd,
                         tau_knee_nm=tau,fz=None if c.load_mode=='torque' else fz,
                         valid=c.load_mode=='torque' or fz>0,**pos))
    return rows


def forces(torque, g, slack):
    delta=torque/(g['r2_mm']/1000)
    a=slack+max(delta,0); b=slack+max(-delta,0)
    path=g.get('route')
    idlers=[]
    if path:
        vec={}
        for i,c in enumerate(path['circles']):
            prev=path['edges'][i-1];nxt=path['edges'][i]
            tp=a if prev['span']=='A' else b;tn=a if nxt['span']=='A' else b
            v=[tn*nxt['unit'][k]-tp*prev['unit'][k] for k in (0,1)]
            vec[c['name']]=v
            if c['side']<0:idlers.append(dict(name=c['name'],force_local=v,support_n=math.hypot(*v)))
        fi=vec['Input'];fo=vec['Output']
    else:
        theta=g['tangent_angle_rad'];fi=[(a+b)*math.cos(theta),(a-b)*math.sin(theta)];fo=[-x for x in fi]
    return dict(tension_a_n=a,tension_b_n=b,delta_n=delta,
                chain_input_local=fi,chain_output_local=fo,idler_forces=idlers,
                chain_resultant_n=math.hypot(*fo),input_chain_resultant_n=math.hypot(*fi),
                idler_max_n=max((x['support_n'] for x in idlers),default=0))


def evaluate(c, rows=None, include_rows=True, solved_geometry=None):
    c=ChainConfig.from_dict(c); item=chain_item(c); g=solved_geometry if solved_geometry is not None else geometry(c,item)
    rows=rows if rows is not None else task_rows(c)
    result=[]; limit=item['effective_allowable_n']; eta=c.efficiency
    for task in rows:
        row=dict(task);row['contact_valid']=row['valid'];row['valid']=row['valid'] and g['route_solved']
        if not row['valid']:
            row.update(tension_a_n=None,tension_b_n=None,module_torque_nm=None,module_speed_rpm=None,
                       chain_resultant_n=None,input_chain_resultant_n=None,idler_max_n=None,idler_forces=[],knee_support_n=None,load_ok=False,motor_ok=False)
            result.append(row);continue
        f=forces(row['tau_knee_nm'],g,c.slack_n)
        power=row['tau_knee_nm']*row['qdot']
        # Lump losses at module interface; ideal chain reactions remain separate.
        loss=eta if power < -1e-10 else 1/eta
        module_tau=row['tau_knee_nm']/g['ratio']*loss
        speed=row['qdot']*g['ratio']*60/(2*math.pi)
        cf=rotate(f['chain_output_local'],row['thigh_pitch'])
        support=None if row['fz'] is None else [-cf[0],-cf[1]-row['fz']]
        row.update(f,module_torque_nm=module_tau,module_speed_rpm=speed,
                   module_power_w=module_tau*speed*2*math.pi/60,
                   knee_support_n=math.hypot(*support) if support else None,
                   chain_output_world=cf,knee_support_world=support,
                   load_ok=None if limit is None else max(f['tension_a_n'],f['tension_b_n'])*c.load_margin<=limit,
                   motor_ok=abs(module_tau)<=c.motor_rated_nm+1e-9 and abs(speed)<=c.motor_speed_rpm+1e-9)
        result.append(row)
    valid=[r for r in result if r['valid']]
    peak=lambda key:max((abs(r[key]) for r in valid if r.get(key) is not None),default=None)
    peak_chain=max((max(r['tension_a_n'],r['tension_b_n']) for r in valid),default=None)
    checks=[]
    def check(name,passed,value):
        checks.append(dict(name=name,state='unknown' if passed is None else 'pass' if passed else 'fail',detail=value))
    check('Input tip diameter',g['tip1_mm']<=c.input_max_mm,f"{g['tip1_mm']:.1f} / {c.input_max_mm:g} mm · upper estimate")
    check('Output tip diameter',g['tip2_mm']<=c.output_max_mm,f"{g['tip2_mm']:.1f} / {c.output_max_mm:g} mm · upper estimate")
    check('Chain width',item['width_mm']<=c.width_max_mm,f"{item['width_mm']:.2f} / {c.width_max_mm:g} mm · chain only")
    check('Reduction ratio',c.ratio_min<=g['ratio']<=c.ratio_max,f"{g['ratio']:.3f} · limits {c.ratio_min:g}–{c.ratio_max:g}")
    check('Sprocket separation',g['centers_clear'],'Tooth-tip envelopes must not overlap')
    check('Small-wheel wrap',min(g['wrap1_deg'],g['wrap2_deg'])>=c.min_wrap_deg,f"{min(g['wrap1_deg'],g['wrap2_deg']):.1f}° / minimum {c.min_wrap_deg:g}°")
    check('Even link-count range',c.links_min<=c.links<=c.links_max,f'{c.links} pitches · requested {c.links_min}–{c.links_max}')
    check('Idler routing / chain length',g['route_solved'],f"{c.idler_mode}: {c.links} pitches · travel {g['route']['depth_mm']:.2f} mm" if g['route_solved'] else 'No fitting route within travel / wrap / clearance limits; base path preview only')
    check('Ground contact',all(r['contact_valid'] for r in result),'Prescribed torque case' if c.load_mode=='torque' else f"{sum(r['contact_valid'] for r in result)}/{len(result)} supporting samples")
    check('Chain load',None if limit is None or peak_chain is None else peak_chain*c.load_margin<=limit,
          'Allowable load missing; breaking load is not used' if limit is None else f'{(peak_chain or 0)*c.load_margin:.0f} / {limit:.0f} N · includes screening factor')
    check('Module rated torque',peak('module_torque_nm') is not None and peak('module_torque_nm')<=c.motor_rated_nm,
          f"{(peak('module_torque_nm') or 0):.1f} / {c.motor_rated_nm:g} N·m")
    check('Module speed',peak('module_speed_rpm') is not None and peak('module_speed_rpm')<=c.motor_speed_rpm,
          f"{(peak('module_speed_rpm') or 0):.1f} / {c.motor_speed_rpm:g} rpm")
    state='fail' if any(x['state']=='fail' for x in checks) else 'unrated' if any(x['state']=='unknown' for x in checks) else 'screen_pass'
    summary=dict(state=state,peak_tension_n=peak_chain,design_tension_n=peak_chain*c.load_margin if peak_chain is not None else None,
                 peak_module_nm=peak('module_torque_nm'),peak_module_rpm=peak('module_speed_rpm'),
                 peak_knee_nm=peak('tau_knee_nm'),peak_chain_resultant_n=peak('chain_resultant_n'),
                 peak_knee_support_n=peak('knee_support_n'),peak_input_support_n=peak('input_chain_resultant_n'),peak_idler_n=peak('idler_max_n'),complete=len(valid)==len(result),
                 load_margin_available=limit/(peak_chain*c.load_margin) if limit is not None and peak_chain and peak_chain>0 else None)
    warnings=['Mean pitch-path geometry with fixed idlers. Slack tension is prescribed; spring response, wear take-up and tooth engagement are not solved.',
              'Auto placement searches x/C = 0.20–0.80 at 0.05 spacing, then solves inward travel; it selects the smallest feasible travel.',
              'Idler reverse bending and sprocket compatibility require manufacturer review; planar checks exclude hubs, shafts and housing.',
              'Chain width excludes hubs, bearings and housing. Tooth-tip dimensions are estimates; check supplier CAD.',
              'Screening is not a fatigue-life, thermal, bearing-capacity or collision verification.']
    if c.input_teeth<19: warnings.append('Input has fewer than 19 teeth; check chordal effects and manufacturer selection factors.')
    if min(c.q_start_deg,c.q_end_deg)<=0<=max(c.q_start_deg,c.q_end_deg): warnings.append('Leg crosses straight alignment; whole-leg control and clearance are not verified.')
    if c.load_mode=='trajectory': warnings.append('Acceleration comes only from a hip-lumped COM; link inertia and impact are omitted.')
    if c.load_mode=='torque': warnings.append('Prescribed knee torque does not define foot force; total knee support is not reported.')
    return dict(version='0.9.0',config=c.to_dict(),chain=item,geometry=g,summary=summary,
                checks=checks,warnings=warnings,rows=result if include_rows else [])


def scan(data=None, chain_ids=None):
    c=ChainConfig.from_dict(data)
    if chain_ids is None: chain_ids=list(ITEMS)
    if not isinstance(chain_ids,list) or not chain_ids or len(chain_ids)>5 or any(x not in ITEMS and x!='custom' for x in chain_ids):
        raise ValueError('Choose one to five known chain types.')
    chain_ids=list(dict.fromkeys(chain_ids)); tasks=task_rows(c)
    candidates=[]; rejected={}; pairs=0
    def reject(reason): rejected[reason]=rejected.get(reason,0)+1
    for ident in chain_ids:
        # A manual rating belongs to one selected chain, never to every chain.
        base=replace(c,chain_id=ident,allowable_override_n=c.allowable_override_n if ident==c.chain_id else None)
        item=chain_item(base)
        for z1 in range(c.input_teeth_min,c.input_teeth_max+1):
            for z2 in range(max(11,math.ceil(z1*c.ratio_min-1e-9)),min(240,math.floor(z1*c.ratio_max+1e-9))+1):
                pairs+=1; trial=replace(base,input_teeth=z1,output_teeth=z2)
                try: g=geometry(trial,item,routing=False)
                except ValueError: reject('Geometry');continue
                if g['tip1_mm']>c.input_max_mm: reject('Input diameter');continue
                if g['tip2_mm']>c.output_max_mm: reject('Output diameter');continue
                if item['width_mm']>c.width_max_mm: reject('Chain width');continue
                if not g['centers_clear']: reject('Separation');continue
                if min(g['wrap1_deg'],g['wrap2_deg'])<c.min_wrap_deg: reject('Wrap');continue
                prep=chain_route.prepare(trial,g,item)
                lo=max(c.links_min,math.ceil(g['required_links']-1e-9)); lo+=lo%2
                hi=min(c.links_max,math.floor((prep['max_length']+1e-6)/item['pitch_mm']))
                if lo>hi: reject('Link range / idler reach');continue
                for n in range(lo,hi+1,2):
                    if len(candidates)>=12000: raise ValueError('Scan too broad; narrow tooth, ratio or link ranges.')
                    setting=replace(trial,links=n)
                    geom=route_geometry(setting,g,item,prep)
                    if not geom['route_solved']:reject('Idler placement');continue
                    geom['installed_mm']=n*item['pitch_mm'];geom['extra_path_mm']=geom['installed_mm']-g['route_mm']
                    evaluated=evaluate(setting,tasks,include_rows=False,solved_geometry=geom)
                    candidates.append(dict(chain_id=ident,name=item['name'],input_teeth=z1,output_teeth=z2,
                        links=n,ratio=geom['ratio'],input_tip_mm=geom['tip1_mm'],output_tip_mm=geom['tip2_mm'],
                        width_mm=item['width_mm'],extra_path_mm=geom['extra_path_mm'],
                        idler_mode=c.idler_mode,idler_x_mm=geom['route']['x_mm'],idler_travel_mm=geom['route']['depth_mm'],
                        **evaluated['summary'],pareto=False,
                        failures=[ch['name'] for ch in evaluated['checks'] if ch['state']!='pass'],
                        config=setting.to_dict()))
    # Pareto only among fully rated screen passes. Same task / same center.
    feasible=[x for x in candidates if x['state']=='screen_pass']
    front=[]
    def objectives(x): return (x['output_tip_mm'],x['width_mm'],x['peak_module_nm'])
    def dominates(a,b):
        aa,bb=objectives(a),objectives(b)
        return all(x<=y+1e-9 for x,y in zip(aa,bb)) and any(x<y-1e-9 for x,y in zip(aa,bb))
    for row in feasible:
        if not any(dominates(other,row) for other in front):
            front=[other for other in front if not dominates(row,other)];front.append(row)
    for row in front: row['pareto']=True
    rank={'screen_pass':0,'unrated':1,'fail':2}
    candidates.sort(key=lambda x:(rank[x['state']],not x['pareto'],x['output_tip_mm'],x['width_mm'],x['extra_path_mm']))
    return dict(config=c.to_dict(),chain_ids=chain_ids,pairs=pairs,rejected=rejected,
                count=len(candidates),passing=len(feasible),unrated=sum(x['state']=='unrated' for x in candidates),
                pareto=len(front),objectives=['Output tip diameter','Chain width','Peak module torque'],
                candidates=candidates)


def cycle_csv(result):
    out=io.StringIO(); writer=csv.writer(out)
    # Snapshot of assumptions makes exported forces interpretable later.
    writer.writerow(['# model','Mean pitch path with fixed idlers; prescribed slack tension; no idler dynamics'])
    writer.writerow(['# config',json.dumps(result['config'],sort_keys=True)])
    writer.writerow(['# source',result['chain'].get('source') or 'User-defined'])
    writer.writerow(['# route',json.dumps(result['geometry']['route'],sort_keys=True)])
    keys=['t','q_deg','qdot','qddot','fz','tau_knee_nm','module_torque_nm','module_speed_rpm',
          'tension_a_n','tension_b_n','chain_resultant_n','input_chain_resultant_n','idler_max_n','knee_support_n','valid','load_ok','motor_ok']
    writer.writerow(keys)
    for row in result['rows']: writer.writerow([row.get(k) for k in keys])
    return out.getvalue()
