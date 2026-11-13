"""Geometry, foot load, and linear axial-compliance statics.

SI units internally; public configuration uses mm and deg for CAD convenience.
Positive rod force = tension. Local x points from input axis O to knee K.
This is an analytical screening model, not a multibody dynamics integrator.
"""
from __future__ import annotations
import math
from dataclasses import asdict, dataclass, fields, replace
from .statistics import sampled_force_extrema, ZERO_FORCE_N

G = 9.81
TAU = 2 * math.pi


@dataclass
class Config:
    n: int = 2
    spacing_deg: float = 90.0
    center_mm: float = 300.0
    input_radius_mm: float = 60.0
    output_radius_mm: float = 60.0
    rod_mm: float = 300.0
    shank_mm: float = 340.0
    clocking_deg: float = 120.0
    q_start_deg: float = -120.0
    q_end_deg: float = -15.0
    half_cycle_s: float = 2.0
    dead_center_tol_deg: float = 5.0
    mass_kg: float = 80.0
    share: float = 0.5
    load_mode: str = "constant"
    load_factor: float = 1.0
    stiffness_n_mm: float = 10000.0
    k2_ratio: float = 1.0
    k3_ratio: float = 1.0
    branch: str = "open"
    samples: int = 241

    @classmethod
    def from_dict(cls, data=None):
        data = data or {}
        allowed = {f.name for f in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError("Unknown parameters: " + ", ".join(sorted(unknown)))
        c = cls(**data)
        if isinstance(c.n, bool) or not isinstance(c.n,int) or c.n not in (1, 2, 3):
            raise ValueError("n must be 1, 2 or 3.")
        if not isinstance(c.samples, int) or not 21 <= c.samples <= 1001:
            raise ValueError("samples must be an integer between 21 and 1001.")
        for f in fields(cls):
            v = getattr(c, f.name)
            if f.name not in ("branch", "load_mode") and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
                raise ValueError(f"{f.name} must be finite and numeric.")
        ranges = {
            "center_mm": (50, 1000), "shank_mm": (50, 1000),
            "input_radius_mm": (2, 200), "output_radius_mm": (2, 200),
            "rod_mm": (10, 1500), "spacing_deg": (1, 179),
            "clocking_deg": (-360, 360), "q_start_deg": (-175, 175),
            "q_end_deg": (-175, 175), "half_cycle_s": (0.1, 30),
            "mass_kg": (0.1, 1000), "share": (0.01, 1),
            "load_factor": (0.01, 5), "stiffness_n_mm": (1, 1e7),
            "k2_ratio": (0.01, 100), "k3_ratio": (0.01, 100),
            "dead_center_tol_deg": (0.1, 30),
        }
        for name, (lo, hi) in ranges.items():
            if not lo <= getattr(c, name) <= hi:
                raise ValueError(f"{name} must be in [{lo}, {hi}].")
        if c.branch not in ("open", "crossed") or c.load_mode not in ("constant", "trajectory"):
            raise ValueError("Invalid branch or load mode.")
        if c.n > 1:
            # User-confirmed compatible parallelogram family. Never solve
            # incompatible extra rigid bars by silently averaging errors.
            c.output_radius_mm = c.input_radius_mm
            c.rod_mm = c.center_mm
            c.branch = "open"
        if c.n == 3:
            if not 60 <= c.spacing_deg <= 120:
                raise ValueError("Three-rod phase spacing must be in [60, 120] degrees.")
        return c

    def to_dict(self):
        return asdict(self)


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def rotate(v, a):
    c, s = math.cos(a), math.sin(a)
    return [c*v[0] - s*v[1], s*v[0] + c*v[1]]


def unwrap(a, reference):
    return reference + (a-reference+math.pi) % TAU - math.pi


def geometry(c, beta, previous=None):
    """Prescribe output angle beta and solve the input circle intersection.

    n>1 has theta=beta exactly. Single-bar open/crossed assembly branches
    are selected initially and then tracked continuously.
    """
    d, ri, ro, length = [v/1000 for v in
                        (c.center_mm, c.input_radius_mm, c.output_radius_mm, c.rod_mm)]
    phases = [math.radians(i*c.spacing_deg) for i in range(c.n)]
    parallel = abs(ri-ro) < 1e-12 and abs(length-d) < 1e-12
    if parallel and c.branch == "open":
        theta = beta
    else:
        b0 = [d + ro*math.cos(beta), ro*math.sin(beta)]
        distance = math.hypot(*b0)
        if distance < 1e-12:
            return None, "undetermined_input"
        cosine = (distance*distance + ri*ri-length*length)/(2*distance*ri)
        if abs(cosine) > 1+1e-10:
            return None, "no_closure"
        a = math.atan2(b0[1], b0[0])
        delta = math.acos(max(-1, min(1, cosine)))
        candidates = [a+delta, a-delta]
        reference = beta if previous is None else previous
        candidates = [unwrap(v, reference) for v in candidates]
        candidates.sort(key=lambda v: abs(v-reference))
        theta = candidates[-1] if previous is None and c.branch == "crossed" else candidates[0]
    a_points, b_points, u, arm_in, arm_out, residual = [], [], [], [], [], []
    for phase in phases:
        ra = [ri*math.cos(theta+phase), ri*math.sin(theta+phase)]
        rb = [ro*math.cos(beta+phase), ro*math.sin(beta+phase)]
        b = [d+rb[0], rb[1]]
        v = [b[j]-ra[j] for j in (0, 1)]
        actual = math.hypot(*v)
        if actual < 1e-12:
            return None, "zero_length"
        direction = [x/actual for x in v]
        a_points.append(ra); b_points.append(b); u.append(direction)
        arm_in.append(cross(ra, direction))
        arm_out.append(cross(rb, [-direction[0], -direction[1]]))
        residual.append(actual-length)
    if max(abs(v) for v in residual) > 1e-8:
        return None, "incompatible_closure"
    # Lost transmission authority or infinite input speed: do not emit an
    # apparently valid zero-load solution at a singular configuration.
    if max(abs(v) for v in arm_out) < 1e-7:
        return None, "output_dead_center"
    if max(abs(v) for v in arm_in) < 1e-7:
        return None, "input_dead_center"
    j = max(range(c.n), key=lambda i: abs(arm_in[i]))
    speed_ratio = -arm_out[j]/arm_in[j]
    clearance = min(math.degrees(math.asin(min(1, abs(a)/radius)))
                    for arms, radius in ((arm_in, ri), (arm_out, ro)) for a in arms)
    g = dict(theta=theta, beta=beta, A=a_points, B=b_points, u=u,
                arm_in=arm_in, arm_out=arm_out, closure_m=max(abs(x) for x in residual),
                speed_ratio=speed_ratio, clearance_deg=clearance)
    if c.n == 1 and clearance < c.dead_center_tol_deg - 1e-8:
        return g, "dead_center_margin"
    return g, None


def guard_events(c, lo, hi):
    """Output-angle boundaries for closure and both crank/coupler margins.

    Input: |OB| follows the cosine rule for triangle O-A-B.
    Output: at a margin, A=K+Rot(beta)[ro+L*cos(delta), L*sin(delta)].
    Enumerate both assembly branches; harmless extra events split intervals.
    Angles are radians, including any full revolutions in [lo, hi].
    """
    d, ri, ro, length = [v/1000 for v in
                        (c.center_mm, c.input_radius_mm, c.output_radius_mm, c.rod_mm)]
    roots = [0.0, math.pi]
    for eps in (0.0, math.radians(c.dead_center_tol_deg)):
        for sign in (-1, 1):
            cosine = (ri*ri+length*length+sign*2*ri*length*math.cos(eps)-d*d-ro*ro)/(2*d*ro)
            if abs(cosine) <= 1+1e-12:
                a = math.acos(max(-1, min(1, cosine)))
                roots.extend((a, -a))
        for delta in (eps, -eps, math.pi+eps, math.pi-eps):
            wx, wy = ro+length*math.cos(delta), length*math.sin(delta)
            radius = math.hypot(wx, wy)
            if radius < 1e-12:
                continue
            cosine = (ri*ri-d*d-radius*radius)/(2*d*radius)
            if abs(cosine) <= 1+1e-12:
                a = math.acos(max(-1, min(1, cosine)))
                phase = math.atan2(wy, wx)
                roots.extend((a-phase, -a-phase))
    events = [lo, hi]
    for root in roots:
        for k in range(math.ceil((lo-root)/TAU), math.floor((hi-root)/TAU)+1):
            events.append(root+k*TAU)
    ordered = sorted(events)
    unique = []
    for event in ordered:
        if not unique or event-unique[-1] > 1e-10:
            unique.append(event)
    return unique


def motion_range(c):
    """First connected admissible interval in the requested travel direction.

    Keep the requested config unchanged. Rebuild the smooth motion on the
    preview interval; a shortened preview is never a successful task/scan.
    """
    start, end = c.q_start_deg, c.q_end_deg
    result = dict(requested_start_deg=start, requested_end_deg=end,
                  start_deg=start, end_deg=end, limited=False,
                  available=True, theta_start=None)
    if c.n != 1:
        return result
    offset = math.radians(c.clocking_deg)
    a, b = math.radians(start)+offset, math.radians(end)+offset
    if abs(a-b) < 1e-12:
        g, error = geometry(c, a)
        result.update(available=not bool(error), theta_start=g['theta'] if g else None)
        return result
    direction = 1 if b > a else -1
    events = guard_events(c, min(a,b), max(a,b))
    if direction < 0:
        events.reverse()
    chosen_start = chosen_end = seed = previous = None
    initial, initial_error = geometry(c, a)
    if not initial_error:
        # If the requested start is already on a safe boundary, stop there;
        # never teleport across the excluded zone to another assembly range.
        chosen_start = chosen_end = a
        seed = previous = initial['theta']
    for left, right in zip(events, events[1:]):
        middle = (left+right)/2
        g, error = geometry(c, middle, previous)
        if error:
            if chosen_start is not None:
                break
            continue
        edge, edge_error = geometry(c, left, g['theta'])
        if chosen_start is not None and edge_error:
            break  # Never bridge a forbidden gap or change assembly mode.
        if chosen_start is None:
            chosen_start = left if not edge_error else left+direction*min(1e-7, abs(right-left)/100)
            first, first_error = geometry(c, chosen_start, g['theta'])
            if first_error:
                chosen_start = None
                continue
            seed = first['theta']
        edge, edge_error = geometry(c, right, g['theta'])
        chosen_end = right if not edge_error else right-direction*min(1e-7, abs(right-left)/100)
        previous = g['theta']
    if chosen_start is None:
        result['available'] = False
        result['end_deg'] = start
        return result
    result.update(start_deg=math.degrees(chosen_start-offset),
                  end_deg=math.degrees(chosen_end-offset), theta_start=seed)
    result['limited'] = abs(result['start_deg']-start)>1e-7 or abs(result['end_deg']-end)>1e-7
    return result


def rod_end_forces(a, b, tension):
    """External forces ON the ideal massless rod, world [x,z].

    u points A->B; tension pulls A toward -u and B toward +u.
    The forces on the discs are the opposite action/reaction pair.
    """
    length = math.dist(a, b)
    at_b = [tension*(b[j]-a[j])/length for j in (0,1)]
    return dict(A=[-v for v in at_b], B=at_b)


def pose(c, q, qdot=0.0, qddot=0.0):
    """Foot=(0,0), hip x=0. Lumped COM follows hip vertically.

    The thigh pitch is dependent, not fixed. Thus the foot really stays
    fixed while both knee and hip height change.
    """
    d, s = c.center_mm/1000, c.shank_mm/1000
    h = math.sqrt(d*d+s*s+2*d*s*math.cos(q))
    hp = -d*s*math.sin(q)/h
    hpp = -d*s*math.cos(q)/h - (d*s*math.sin(q))**2/h**3
    pitch = -math.pi/2 - math.atan2(s*math.sin(q), d+s*math.cos(q))
    hip = [0.0, h]
    knee = [d*math.cos(pitch), h+d*math.sin(pitch)]
    acceleration = hpp*qdot*qdot + hp*qddot
    return dict(hip=hip, knee=knee, foot=[0.0, 0.0], height_m=h,
                thigh_pitch=pitch, acceleration=acceleration)


def stiffness_forces(arms, stiffnesses, output_torque):
    """Minimum strain energy solution under sum(b_i*N_i)=tau.

    Equivalent to holding the input and allowing a SMALL output twist:
    N_i=k_i*b_i*tau / sum(k_j*b_j^2). No preload or clearance.
    """
    stiffness = sum(k*b*b for k, b in zip(stiffnesses, arms))
    if stiffness <= 1e-12:
        raise ValueError("No torsional stiffness at this pose.")
    twist = output_torque/stiffness
    return [k*b*twist for k, b in zip(stiffnesses, arms)], twist, stiffness


def quintic(u):
    """Position, first derivative, second derivative on a unit interval."""
    return (10*u**3-15*u**4+6*u**5,
            30*u*u-60*u**3+30*u**4,
            60*u-180*u*u+120*u**3)


def cycle(c):
    if not isinstance(c, Config):
        c = Config.from_dict(c)
    else:
        c = Config.from_dict(c.to_dict())
    motion = motion_range(c)
    rows, previous, last_ok = [], motion['theta_start'], False
    start, end = math.radians(motion['start_deg']), math.radians(motion['end_deg'])
    T = c.half_cycle_s
    stiffnesses = [c.stiffness_n_mm*1000*x for x in (1, c.k2_ratio, c.k3_ratio)][:c.n]
    for index in range(c.samples):
        t = 2*T*index/(c.samples-1)
        outbound = t <= T
        u = t/T if outbound else (t-T)/T
        a, b = (start, end) if outbound else (end, start)
        f, fp, fpp = quintic(u)
        q, qdot, qddot = a+(b-a)*f, (b-a)*fp/T, (b-a)*fpp/(T*T)
        p = pose(c, q, qdot, qddot)
        factor = c.load_factor if c.load_mode == "constant" else 1+p["acceleration"]/G
        fz = c.mass_kg*c.share*G*factor
        tau_out = p["knee"][0]*fz  # -cross(foot-knee, ground_force)
        beta = q + math.radians(c.clocking_deg)
        geom, error = geometry(c, beta, previous)
        reasons = []
        if not motion['available']: reasons.append("no_safe_motion")
        if error: reasons.append(error)
        if fz <= 0: reasons.append("contact_lost")
        row = dict(t=t, q_deg=math.degrees(q), qdot=qdot, qddot=qddot,
                   hip_height_m=p["height_m"], com_accel=p["acceleration"],
                   load_factor=factor, fz=fz, tau_out=tau_out,
                   hip=p["hip"], knee=p["knee"], foot=p["foot"],
                   valid=False, reasons=reasons, forces=None, tau_in=None,
                   motor_speed=None, motor_power=None, theta_deg=None,
                   A=None, B=None, closure_m=None, reaction_knee=None,
                   reaction_input=None, twist_deg=None, gain=None,
                   moment_residual=None, power_residual=None, torsional_stiffness=None,
                   clearance_deg=None, rod_end_forces=None)
        if geom:
            # Detect discontinuous branch selection after a gap rather than
            # joining two assembly modes in an apparently valid trajectory.
            if previous is not None and last_ok and abs(geom["theta"]-previous) > math.pi/2:
                reasons.append("branch_jump")
            previous = geom["theta"]
            def world(v):
                r = rotate(v, p["thigh_pitch"])
                return [r[j]+p["hip"][j] for j in (0, 1)]
            row.update(A=[world(v) for v in geom["A"]], B=[world(v) for v in geom["B"]],
                       theta_deg=math.degrees(geom["theta"]), closure_m=geom["closure_m"],
                       clearance_deg=geom['clearance_deg'])
            if not reasons:
                forces, twist, kt = stiffness_forces(geom["arm_out"], stiffnesses, tau_out)
                tau_in = -sum(a*n for a, n in zip(geom["arm_in"], forces))
                motor_speed = geom["speed_ratio"]*qdot
                rods_input_local = [sum(n*v[j] for n,v in zip(forces,geom["u"])) for j in (0,1)]
                rods_input_world = rotate(rods_input_local, p["thigh_pitch"])
                row.update(valid=True, forces=forces, tau_in=tau_in, motor_speed=motor_speed,
                    rod_end_forces=[rod_end_forces(a,b,n) for a,b,n in zip(row['A'],row['B'],forces)],
                    motor_power=tau_in*motor_speed, gain=geom["speed_ratio"],
                    reaction_input=[-v for v in rods_input_world],
                    reaction_knee=[rods_input_world[0], rods_input_world[1]-fz],
                    twist_deg=math.degrees(twist), torsional_stiffness=kt,
                    moment_residual=sum(b*n for b,n in zip(geom["arm_out"],forces))-tau_out,
                    power_residual=tau_in*motor_speed-tau_out*qdot)
        last_ok = not bool(error)
        rows.append(row)
    # An open single parallelogram loses transmission at beta=k*pi even
    # when the discrete time grid misses the exact singular instant.
    if c.n == 1 and c.branch == "open" and abs(c.input_radius_mm-c.output_radius_mm)<1e-9 and abs(c.rod_mm-c.center_mm)<1e-9:
        for left,right in zip(rows,rows[1:]):
            lo,hi=sorted([left["q_deg"]+c.clocking_deg,right["q_deg"]+c.clocking_deg])
            if hi-lo>1e-10 and math.ceil((lo+1e-9)/180)<=math.floor((hi-1e-9)/180):
                for r in (left,right):
                    if "dead_center_between_samples" not in r["reasons"]:r["reasons"].append("dead_center_between_samples")
                    r["valid"]=False
                    for key in ("forces","tau_in","motor_speed","motor_power","reaction_knee","reaction_input","twist_deg","gain","moment_residual","power_residual","torsional_stiffness","rod_end_forces"):
                        r[key]=None
    good = [r for r in rows if r["valid"]]
    errors = sorted({e for r in rows for e in r["reasons"]})
    warnings = []
    if motion['limited']:
        errors.append('motion_limited')
        warnings.append(f"Single-rod guard: requested {c.q_start_deg:g} to {c.q_end_deg:g} deg; preview {motion['start_deg']:.3f} to {motion['end_deg']:.3f} deg. The original motion is not feasible at this margin.")
    if min(start,end) <= 0 <= max(start,end):
        warnings.append("Knee crosses straight alignment: whole-leg singularity; clearance and control not verified.")
    if c.n > 1:
        warnings.append("Rod loads use equal/assigned axial stiffness, zero preload and zero clearance. Rigid statics alone is indeterminate.")
    if c.load_mode == "trajectory":
        warnings.append("COM is lumped at the hip; link masses and rotational inertia are omitted.")
    else:
        warnings.append("Constant load is an envelope; cycle speed does not change this prescribed ground force.")
    if good and max(abs(r["twist_deg"]) for r in good) > 1:
        warnings.append("Elastic twist exceeds 1 degree: small-deformation load sharing needs a nonlinear check.")
    if len(good) != len(rows):
        warnings.append("Incomplete cycle: do not rank this as a feasible design. Invalid curve segments are omitted.")
    def peak(key, vector=False):
        if not good: return None
        return max(math.hypot(*r[key]) if vector else abs(r[key]) for r in good)
    rod_stats = []
    for i in range(c.n):
        values = [r["forces"][i] for r in good]
        rod_stats.append(dict(rod=i+1, tension_n=max([0]+values),
                             compression_n=max([0]+[-v for v in values]),
                             extrema=sampled_force_extrema(rows, i),
                             rms_n=math.sqrt(sum(v*v for v in values)/len(values)) if values else None))
    summary = dict(complete=len(good)==len(rows) and not motion['limited'],
        preview_complete=len(good)==len(rows), valid_samples=len(good), samples=len(rows),
        peak_rod_n=max([max(r["tension_n"],r["compression_n"]) for r in rod_stats]) if good else None,
        peak_input_nm=peak("tau_in"), peak_output_nm=peak("tau_out"),
        peak_input_rad_s=peak("motor_speed"), peak_input_power_w=peak("motor_power"),
        peak_knee_reaction_n=peak("reaction_knee",True), peak_input_reaction_n=peak("reaction_input",True),
        peak_twist_deg=peak("twist_deg"),
        min_fz_n=min(r["fz"] for r in rows), max_fz_n=max(r["fz"] for r in rows),
        min_load_factor=min(r["load_factor"] for r in rows), max_load_factor=max(r["load_factor"] for r in rows),
        min_hip_m=min(r["hip_height_m"] for r in rows), max_hip_m=max(r["hip_height_m"] for r in rows),
        max_closure_m=max((r["closure_m"] for r in rows if r["closure_m"] is not None),default=None),
        max_moment_residual_nm=peak("moment_residual"), max_power_residual_w=peak("power_residual"),
        rods=rod_stats, extrema_zero_tol_n=ZERO_FORCE_N)
    return dict(version="0.4.0", config=c.to_dict(), motion=motion, summary=summary, errors=errors,
                warnings=warnings, rows=rows)
