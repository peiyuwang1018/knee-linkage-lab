"""Independent physical checks, not screenshots of implementation values."""
import json
import math
import unittest
from kneelab.model import Config,cycle,geometry,pose,stiffness_forces,cross,rod_end_forces
from kneelab.scan import scan
from kneelab.export import cycle_csv


class MechanicsTests(unittest.TestCase):
    def test_static_force_newtons(self):
        r=cycle(Config())
        self.assertAlmostEqual(r['rows'][0]['fz'],80*9.81/2)
        self.assertTrue(r['summary']['complete'])

    def test_foot_really_fixed(self):
        c=Config()
        for q in [-2.3,-1.5,-.1,0,.1,1.5,2.3]:
            p=pose(c,q);angle=p['thigh_pitch']+q
            foot=[p['knee'][0]+.34*math.cos(angle),p['knee'][1]+.34*math.sin(angle)]
            self.assertAlmostEqual(foot[0],0,places=12)
            self.assertAlmostEqual(foot[1],0,places=12)

    def test_height_acceleration_finite_difference(self):
        c=Config();q,qd,qdd=-1.3,.7,.2;dt=1e-4
        z=lambda t:pose(c,q+qd*t+.5*qdd*t*t)['height_m']
        numerical=(z(dt)-2*z(0)+z(-dt))/(dt*dt)
        self.assertAlmostEqual(pose(c,q,qd,qdd)['acceleration'],numerical,places=6)

    def test_equal_two_rods_analytical(self):
        b=[.06*math.sin(math.pi/6),.06*math.cos(math.pi/6)]
        forces,twist,k=stiffness_forces(b,[1e7,1e7],120)
        self.assertAlmostEqual(forces[0],1000,places=9)
        self.assertAlmostEqual(forces[1],1000*math.sqrt(3),places=9)
        self.assertAlmostEqual(k,36000)

    def test_three_rods_analytical(self):
        for angle in (0,.3,1.5,3.0):
            b=[.06*math.sin(angle+i*math.pi/3) for i in range(3)]
            forces,_,kt=stiffness_forces(b,[1e7]*3,120)
            for i in range(3):self.assertAlmostEqual(forces[i],(2*120/(3*.06))*math.sin(angle+i*math.pi/3))
            self.assertAlmostEqual(kt,54000)

    def test_general_fourbar_virtual_work_and_velocity(self):
        c=Config.from_dict(dict(n=1,input_radius_mm=50,output_radius_mm=60,rod_mm=310))
        beta=1.1;g,e=geometry(c,beta);self.assertIsNone(e)
        gm,_=geometry(c,beta-1e-6,g['theta']);gp,_=geometry(c,beta+1e-6,g['theta'])
        numerical=(gp['theta']-gm['theta'])/2e-6
        self.assertAlmostEqual(numerical,g['speed_ratio'],places=6)
        forces,_,_=stiffness_forces(g['arm_out'],[1e7],100)
        drive=-g['arm_in'][0]*forces[0]
        self.assertAlmostEqual(drive*numerical,100,places=5)

    def test_multi_rods_geometry_enforced(self):
        c=Config.from_dict(dict(n=3,rod_mm=420,output_radius_mm=30,spacing_deg=120))
        self.assertEqual(c.rod_mm,c.center_mm)
        self.assertEqual(c.output_radius_mm,c.input_radius_mm)
        self.assertEqual(c.spacing_deg,120)
        with self.assertRaises(ValueError):Config.from_dict(dict(n=3,spacing_deg=59))

    def test_parallel_ratio_and_closure(self):
        for n in (2,3):
            c=Config.from_dict(dict(n=n))
            for beta in (0,math.pi/2,math.pi,1.23):
                g,e=geometry(c,beta);self.assertIsNone(e)
                self.assertAlmostEqual(g['theta'],beta)
                self.assertAlmostEqual(g['speed_ratio'],1)
                self.assertLess(g['closure_m'],1e-12)

    def test_total_force_equilibrium(self):
        r=cycle(Config())
        for row in r['rows']:
            ir,kr=row['reaction_input'],row['reaction_knee']
            self.assertAlmostEqual(ir[0]+kr[0],0,places=8)
            self.assertAlmostEqual(ir[1]+kr[1]+row['fz'],0,places=8)

    def test_output_moment_independent(self):
        r=cycle(Config())
        for row in r['rows'][::20]:
            moment=cross([row['foot'][i]-row['knee'][i] for i in (0,1)],[0,row['fz']])
            for a,b,n in zip(row['A'],row['B'],row['forces']):
                length=math.dist(a,b)
                force=[n*(a[i]-b[i])/length for i in (0,1)]
                moment+=cross([b[i]-row['knee'][i] for i in (0,1)],force)
            self.assertAlmostEqual(moment,0,places=8)

    def test_stiffness_scale(self):
        a=cycle(Config());b=cycle(Config(stiffness_n_mm=20000))
        self.assertAlmostEqual(a['summary']['peak_rod_n'],b['summary']['peak_rod_n'])
        self.assertAlmostEqual(a['summary']['peak_twist_deg'],2*b['summary']['peak_twist_deg'])

    def test_load_scale(self):
        a=cycle(Config());b=cycle(Config(load_factor=1.5))
        self.assertAlmostEqual(b['summary']['peak_rod_n'],1.5*a['summary']['peak_rod_n'])
        self.assertAlmostEqual(b['summary']['peak_input_nm'],1.5*a['summary']['peak_input_nm'])

    def test_contact_loss_not_clamped(self):
        r=cycle(Config(load_mode='trajectory',half_cycle_s=.15))
        self.assertFalse(r['summary']['complete']);self.assertIn('contact_lost',r['errors'])
        self.assertLess(r['summary']['min_fz_n'],0)
        self.assertTrue(all(row['forces'] is None for row in r['rows'] if row['fz']<=0))

    def test_slow_limit(self):
        r=cycle(Config(load_mode='trajectory',half_cycle_s=30))
        self.assertLess(abs(r['summary']['max_load_factor']-1),.001)

    def test_singular_single_bar(self):
        r=cycle(Config(n=1))
        self.assertFalse(r['summary']['complete']);self.assertIn('motion_limited',r['errors'])
        self.assertTrue(r['summary']['preview_complete'])
        self.assertAlmostEqual(r['motion']['start_deg'],-115)
        self.assertTrue(all(row['clearance_deg']>=5-1e-7 for row in r['rows']))

    def test_singularity_between_samples(self):
        r=cycle(Config(n=1,q_start_deg=-130.3,q_end_deg=-12.7,clocking_deg=120,samples=22))
        self.assertFalse(r['summary']['complete'])
        self.assertIn('motion_limited',r['errors'])
        self.assertAlmostEqual(r['motion']['end_deg'],-125)
        self.assertTrue(all(row['q_deg']<=-125+1e-7 for row in r['rows']))

    def test_reverse_knee_torque_sign(self):
        r=cycle(Config(q_start_deg=-100,q_end_deg=100,samples=241))
        self.assertTrue(r['summary']['complete'])
        self.assertGreater(r['rows'][0]['tau_out'],0)
        self.assertLess(r['rows'][120]['tau_out'],0)
        self.assertTrue(any('singularity' in w for w in r['warnings']))

    def test_invalid_geometry(self):
        r=cycle(Config(n=1,rod_mm=10,input_radius_mm=2,output_radius_mm=2))
        self.assertFalse(r['summary']['complete']);self.assertIn('no_closure',r['errors'])
        self.assertIsNone(r['summary']['peak_rod_n'])

    def test_numeric_validation(self):
        for data in (dict(mass_kg=-1),dict(half_cycle_s=0),dict(n=2.0),dict(k2_ratio=0),dict(q_start_deg=float('nan'))):
            with self.assertRaises(ValueError):Config.from_dict(data)

    def test_scanner_dedup_and_known_ranking(self):
        r=scan(Config(),dict(n=[2,3],input_radius_mm=[40,80],spacing_deg=[60,90]),dict(max_rod_n=0))
        self.assertEqual(r['evaluated'],8)
        self.assertTrue(r['feasible']>0)
        self.assertEqual(r['candidates'][0]['config']['input_radius_mm'],80)
        for row in r['candidates']:self.assertTrue(row['complete'])

    def test_scanner_rejects_dead_point(self):
        r=scan(Config(),dict(n=[1],input_radius_mm=[60]),dict(max_rod_n=0))
        self.assertEqual(r['feasible'],0)

    def test_json_finite_and_csv_invalid_rows(self):
        r=cycle(Config(n=1));json.dumps(r,allow_nan=False)
        self.assertIn('False',cycle_csv(r));self.assertEqual(len(cycle_csv(r).splitlines()),242)

    def test_sample_convergence(self):
        a=cycle(Config(samples=241));b=cycle(Config(samples=961))
        self.assertLess(abs(a['summary']['peak_rod_n']/b['summary']['peak_rod_n']-1),.002)

    def test_margin_limits_both_directions_and_smooth_endpoints(self):
        for start,end,expected in [(-120,-15,(-110,-15)),(-15,-130,(-15,-110)),(-130,-15,(-130,-130))]:
            r=cycle(Config(n=1,q_start_deg=start,q_end_deg=end,dead_center_tol_deg=10))
            self.assertAlmostEqual(r['motion']['start_deg'],expected[0])
            self.assertAlmostEqual(r['motion']['end_deg'],expected[1])
            self.assertEqual(r['rows'][0]['qdot'],0)
            self.assertAlmostEqual(r['rows'][120]['qdot'],0)
            for row in r['rows']:
                if row['valid']:self.assertGreaterEqual(row['clearance_deg'],10-1e-7)

    def test_general_fourbar_margin_at_both_cranks(self):
        for branch in ('open','crossed'):
            r=cycle(Config(n=1,input_radius_mm=50,output_radius_mm=60,rod_mm=310,
                           q_start_deg=-150,q_end_deg=50,branch=branch,samples=1001,dead_center_tol_deg=7))
            self.assertTrue(r['motion']['available'])
            self.assertTrue(r['summary']['preview_complete'])
            for row in r['rows']:
                # Independently calculate sin(angle) from world pin coordinates.
                a,b=row['A'][0],row['B'][0];rod=[b[j]-a[j] for j in (0,1)]
                for axis,pin in ((row['hip'],a),(row['knee'],b)):
                    arm=[pin[j]-axis[j] for j in (0,1)]
                    sine=abs(cross(arm,rod))/(math.hypot(*arm)*math.hypot(*rod))
                    self.assertGreaterEqual(sine,math.sin(math.radians(7))-1e-8)

    def test_no_safe_interval_blocks_force_results(self):
        r=cycle(Config(n=1,q_start_deg=-122,q_end_deg=-118))
        self.assertFalse(r['motion']['available'])
        self.assertFalse(r['summary']['complete'])
        self.assertTrue(all(row['forces'] is None for row in r['rows']))
        self.assertTrue(all(row['q_deg']==r['rows'][0]['q_deg'] for row in r['rows']))

    def test_three_rod_120_degree_uniform_stiffness(self):
        for alpha in (60,90,120):
            c=Config.from_dict(dict(n=3,spacing_deg=alpha))
            stiffnesses=[]
            for beta in (0,.3,1.2,2.9):
                g,e=geometry(c,beta);self.assertIsNone(e)
                f,_,kt=stiffness_forces(g['arm_out'],[1e7]*3,100)
                self.assertAlmostEqual(sum(n*b for n,b in zip(f,g['arm_out'])),100)
                stiffnesses.append(kt)
            if alpha in (60,120):
                for kt in stiffnesses:self.assertAlmostEqual(kt,54000)
            else:self.assertGreater(max(stiffnesses)-min(stiffnesses),1000)

    def test_rod_vectors_tension_compression_and_action_reaction(self):
        for force in (500,-500,0):
            a,b=[.1,.2],[.4,.6];v=rod_end_forces(a,b,force)
            self.assertAlmostEqual(v['B'][0],force*.6)
            self.assertAlmostEqual(v['B'][1],force*.8)
            self.assertAlmostEqual(cross([b[j]-a[j] for j in (0,1)],v['B']),0)
            for j in (0,1):self.assertEqual(v['A'][j],-v['B'][j])
        for row in cycle(Config(n=3,spacing_deg=120))['rows'][::20]:
            for j in (0,1):
                self.assertAlmostEqual(sum(v['A'][j] for v in row['rod_end_forces']),row['reaction_input'][j])
                self.assertAlmostEqual(sum(v['B'][j] for v in row['rod_end_forces'])-(row['fz'] if j else 0),row['reaction_knee'][j])

    def test_scan_keeps_three_rod_spacing_and_rejects_trimmed_range(self):
        r=scan(Config(),dict(n=[3],spacing_deg=[60,90,120]),dict(max_rod_n=0,max_twist_deg=0))
        self.assertEqual(r['evaluated'],3)
        self.assertEqual({c['config']['spacing_deg'] for c in r['candidates']},{60,90,120})
        r=scan(Config(n=1),dict(n=[1]),dict(max_rod_n=0))
        self.assertEqual(r['feasible'],0)
        self.assertIn('motion_limited',r['rejected'])
        r=scan(Config(),dict(n=[2,3],spacing_deg=[30,120]),dict(max_rod_n=0,max_twist_deg=0))
        self.assertEqual(r['evaluated'],4)
        self.assertEqual(r['rejected']['three_rod_phase_spacing'],1)


if __name__=='__main__':unittest.main()
