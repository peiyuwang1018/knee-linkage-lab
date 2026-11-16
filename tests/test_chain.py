import math
import unittest
from dataclasses import replace
from kneelab.chain import ChainConfig, chain_item, geometry, route_length, forces, evaluate, scan, cycle_csv


class ChainMechanicsTests(unittest.TestCase):
    def test_equal_wheels_length_and_inverse_center(self):
        c=ChainConfig(input_teeth=20,output_teeth=20,links=84)
        g=geometry(c,routing=False);p=chain_item(c)['pitch_mm']
        self.assertAlmostEqual(g['route_mm'],2*c.center_mm+20*p,10)
        self.assertAlmostEqual(g['free_center_mm'],(84-20)*p/2,9)
        self.assertEqual(g['wrap1_deg'],180)
        self.assertNotEqual(g['pitch1_mm']/2,g['r1_mm'])

    def test_moment_balance_and_reversal(self):
        g=geometry(ChainConfig(),routing=False); a=g['tangent_angle_rad'];r=g['r2_mm']/1000
        for tau in (-110,0,110):
            f=forces(tau,g,50)
            ta,tb=f['tension_a_n'],f['tension_b_n']
            self.assertEqual(min(ta,tb),50)
            self.assertAlmostEqual((ta-tb)*r,tau)
            # Independently sum moments about output center at two tangent contacts.
            p1=(-r*math.sin(a),r*math.cos(a));p2=(-r*math.sin(a),-r*math.cos(a))
            fa=(-ta*math.cos(a),-ta*math.sin(a));fb=(-tb*math.cos(a),tb*math.sin(a))
            self.assertAlmostEqual(p1[0]*fa[1]-p1[1]*fa[0]+p2[0]*fb[1]-p2[1]*fb[0],tau)
            self.assertAlmostEqual(f['chain_output_local'][0],fa[0]+fb[0])
            self.assertAlmostEqual(f['chain_output_local'][1],fa[1]+fb[1])
        self.assertAlmostEqual(forces(110,g,50)['chain_resultant_n'],forces(-110,g,50)['chain_resultant_n'])

    def test_power_and_loss_direction(self):
        c=ChainConfig(efficiency=.9)
        for r in evaluate(c)['rows']:
            pout=r['tau_knee_nm']*r['qdot'];pin=r['module_power_w']
            self.assertGreaterEqual(pin-pout,-1e-8)
            if abs(pout)>1e-8:
                self.assertAlmostEqual(pin,pout/.9 if pout>0 else pout*.9,8)
        ideal=evaluate(replace(c,efficiency=1))
        for r in ideal['rows']:
            self.assertAlmostEqual(r['module_torque_nm']*2,r['tau_knee_nm'])
            self.assertAlmostEqual(r['module_speed_rpm']*math.pi/30,2*r['qdot'])

    def test_support_free_body_balance(self):
        for r in evaluate({})['rows']:
            self.assertAlmostEqual(r['knee_support_world'][0]+r['chain_output_world'][0],0)
            self.assertAlmostEqual(r['knee_support_world'][1]+r['chain_output_world'][1]+r['fz'],0)

    def test_torque_case_does_not_invent_foot_force(self):
        r=evaluate({'load_mode':'torque','prescribed_torque_nm':-100})
        self.assertTrue(all(x['fz'] is None and x['knee_support_n'] is None for x in r['rows']))
        self.assertTrue(all(x['tension_b_n']>x['tension_a_n'] for x in r['rows']))
        self.assertIsNone(r['summary']['peak_knee_support_n'])

    def test_rating_is_not_breaking_strength(self):
        c=ChainConfig(chain_id='iwis05b',load_mode='torque',prescribed_torque_nm=10)
        c=replace(c,links=geometry(c)['suggested_links'])
        r=evaluate(c)
        self.assertIsNone(r['chain']['effective_allowable_n'])
        self.assertGreater(r['chain']['breaking_n'],0)
        self.assertEqual(r['summary']['state'],'unrated')
        self.assertEqual(evaluate(replace(c,allowable_override_n=3000))['summary']['state'],'screen_pass')

    def test_bad_length_and_contact_fail(self):
        r=evaluate({'links':60})
        self.assertLess(r['geometry']['extra_path_mm'],0)
        self.assertEqual(r['summary']['state'],'fail')
        r=evaluate({'load_mode':'trajectory','half_cycle_s':.1})
        self.assertFalse(r['summary']['complete'])
        self.assertTrue(any(not x['valid'] for x in r['rows']))
        self.assertEqual(r['summary']['state'],'fail')
        self.assertTrue(all(x['module_torque_nm'] is None for x in r['rows'] if not x['valid']))

    def test_strict_inputs(self):
        for data in ({'links':91},{'input_teeth':19.2},{'mass_kg':float('nan')},{'efficiency':True},
                     {'ratio_max':2.01},{'output_teeth':52,'ratio_max':1.55},{'links_min':100,'links_max':80},
                     {'samples':240},{'custom_pitch_mm':4,'custom_roller_mm':5}):
            with self.subTest(data=data),self.assertRaises(ValueError):ChainConfig.from_dict(data)

    def test_scan_integer_constraints_and_reload(self):
        c=ChainConfig(ratio_max=1.75,output_teeth=33,input_teeth_min=19,input_teeth_max=20,samples=21)
        s=scan(c)
        self.assertGreater(s['count'],0)
        for r in s['candidates']:
            self.assertLessEqual(r['ratio'],1.75)
            self.assertLessEqual(r['input_tip_mm'],100)
            self.assertEqual(r['links']%2,0)
            self.assertTrue(c.links_min<=r['links']<=c.links_max)
            self.assertTrue(0<=r['idler_travel_mm']<=c.idler_travel_mm)
            self.assertEqual(r['config']['center_mm'],300)
            if r['pareto']:self.assertEqual(r['state'],'screen_pass')
        for r in s['candidates'][::max(1,len(s['candidates'])//12)]:
            new=evaluate(r['config'])
            self.assertEqual(new['summary']['state'],r['state'])
            self.assertAlmostEqual(new['summary']['peak_tension_n'],r['peak_tension_n'])

    def test_override_stays_with_selected_chain(self):
        c=ChainConfig(chain_id='tsubaki35',allowable_override_n=1e5,input_teeth_min=19,input_teeth_max=19,
                      load_mode='torque',prescribed_torque_nm=10,samples=21)
        s=scan(c,['iwis05b','tsubaki35'])
        self.assertTrue(any(r['chain_id']=='iwis05b' for r in s['candidates']))
        for r in s['candidates']:
            if r['chain_id']=='iwis05b':
                self.assertIsNone(r['config']['allowable_override_n'])
                self.assertEqual(r['state'],'unrated')
                self.assertFalse(r['pareto'])

    def test_csv_records_model_and_assumptions(self):
        text=cycle_csv(evaluate({}))
        self.assertIn('prescribed slack tension',text)
        self.assertIn('ratio_max',text)
        self.assertIn('module_speed_rpm',text)
        self.assertIn('https://chains.ustsubaki.com',text)

if __name__=='__main__':unittest.main()
