import math
import unittest
from dataclasses import replace
from kneelab.chain import ChainConfig, chain_item, geometry, evaluate, forces, scan
from kneelab import chain_route

class IdlerRoutingTests(unittest.TestCase):
    def test_fixed_ratio_min_and_hard_tooth_constraint(self):
        self.assertEqual(ChainConfig.from_dict({'ratio_min':1.5}).ratio_min,1)
        for d in ({'output_teeth':52},{'output_teeth':38,'ratio_max':1.55},{'output_teeth':18}):
            with self.assertRaises(ValueError):ChainConfig.from_dict(d)
        self.assertEqual(ChainConfig.from_dict({'output_teeth':29,'ratio_max':1.55}).output_teeth,29)

    def test_single_and_mirrored_layouts_close(self):
        for mode in ('single','dual'):
            c=ChainConfig(idler_mode=mode,links=94);g=geometry(c);r=g['route']
            self.assertTrue(g['route_solved'])
            self.assertAlmostEqual(r['length_mm'],c.links*chain_item(c)['pitch_mm'],5)
            idlers=[x for x in r['circles'] if x['side']<0]
            self.assertEqual(len(idlers),1 if mode=='single' else 2)
            self.assertGreater(r['depth_mm'],0)
            self.assertLessEqual(r['depth_mm'],c.idler_travel_mm)
            if mode=='dual':
                self.assertEqual(idlers[0]['center'][0],idlers[1]['center'][0])
                self.assertAlmostEqual(idlers[0]['center'][1],-idlers[1]['center'][1])
            for i,e in enumerate(r['edges']):
                for center,pt in [(r['circles'][i]['center'],e['start']),(r['circles'][(i+1)%len(r['circles'])]['center'],e['end'])]:
                    self.assertAlmostEqual(chain_route.dot(chain_route.sub(pt,center),e['unit']),0,8)

    def test_extra_links_use_actual_idler_reach_not_old_budget(self):
        g=geometry(ChainConfig(idler_mode='single',links=96,takeup_mm=0))
        self.assertTrue(g['route_solved'])
        self.assertGreater(g['extra_path_mm'],8)
        self.assertFalse(geometry(ChainConfig(idler_mode='dual',links=100))['route_solved'])
        self.assertFalse(geometry(ChainConfig(idler_mode='single',links=60))['route_solved'])

    def test_zero_depth_matches_two_wheel_path(self):
        c=ChainConfig();g=geometry(c,routing=False);item=chain_item(c);p=chain_route.prepare(c,g,item)
        for o in p['options']:
            self.assertAlmostEqual(o['base']['length_mm'],g['route_mm'],7)
            self.assertAlmostEqual(o['base']['wrap1_deg'],g['wrap1_deg'],7)
        self.assertTrue(p['options'])

    def test_global_force_and_individual_wheel_moments(self):
        for mode in ('single','dual'):
            g=geometry(ChainConfig(idler_mode=mode,links=94))
            for torque in (-100,0,100):
                f=forces(torque,g,50);sumv=[f['chain_input_local'][i]+f['chain_output_local'][i]+sum(x['force_local'][i] for x in f['idler_forces']) for i in (0,1)]
                self.assertAlmostEqual(sumv[0],0,8);self.assertAlmostEqual(sumv[1],0,8)
                r=g['route']
                for i,c in enumerate(r['circles']):
                    prev,nxt=r['edges'][i-1],r['edges'][i]
                    tp=f['tension_a_n'] if prev['span']=='A' else f['tension_b_n']
                    tn=f['tension_a_n'] if nxt['span']=='A' else f['tension_b_n']
                    moment=chain_route.cross(chain_route.sub(prev['end'],c['center']),[-tp*x for x in prev['unit']])+chain_route.cross(chain_route.sub(nxt['start'],c['center']),[tn*x for x in nxt['unit']])
                    expected=torque*1000 if c['name']=='Output' else -torque*1000/g['ratio'] if c['name']=='Input' else 0
                    self.assertAlmostEqual(moment,expected,6)

    def test_length_derivative_agrees_with_idler_virtual_work(self):
        c=ChainConfig(idler_mode='single',links=94,idler_position='fixed',idler_x_fraction=.5)
        g=geometry(c);p=chain_route.prepare(c,geometry(c,routing=False),chain_item(c));route=g['route'];x=route['x_mm'];h=route['depth_mm'];dh=1e-3
        derivative=(p['at'](x,h+dh)['length_mm']-p['at'](x,h-dh)['length_mm'])/(2*dh)
        # Equal 100 N tension, bottom idler moving in +y; chain resists that motion.
        f=forces(0,g,100);self.assertAlmostEqual(f['idler_forces'][0]['force_local'][1],-100*derivative,5)

    def test_no_solution_has_no_fabricated_chain_forces(self):
        r=evaluate({'links':140})
        self.assertFalse(r['geometry']['route_solved'])
        self.assertEqual(r['summary']['state'],'fail')
        self.assertTrue(all(x['tension_a_n'] is None for x in r['rows']))
        contact=next(x for x in r['checks'] if x['name']=='Ground contact')
        self.assertEqual(contact['state'],'pass')

    def test_fixed_x_and_travel_constraints(self):
        c=ChainConfig(idler_position='fixed',idler_x_fraction=.5)
        g=geometry(c);self.assertTrue(g['route_solved']);self.assertAlmostEqual(g['route']['x_mm'],150)
        self.assertFalse(geometry(replace(c,idler_travel_mm=0))['route_solved'])

    def test_route_rejects_overlap_and_crossing(self):
        circles=[dict(name='Input',center=[0,0],r=20,outer=24,side=1),dict(name='Output',center=[45,0],r=20,outer=24,side=1)]
        with self.assertRaises(ValueError):chain_route.route(circles)
        c=ChainConfig(idler_mode='dual');g=geometry(c,routing=False);p=chain_route.prepare(c,g,chain_item(c))
        with self.assertRaises(ValueError):p['at'](150,100)

    def test_scan_includes_longer_chains_and_reload_reactions(self):
        c=ChainConfig(idler_mode='single',links=96,links_min=96,links_max=96,
                      input_teeth_min=19,input_teeth_max=19,samples=21,takeup_mm=0)
        results=scan(c,['tsubaki35'])['candidates']
        chosen=next(r for r in results if r['output_teeth']==38)
        self.assertEqual(chosen['links'],96)
        fresh=evaluate(chosen['config'])
        self.assertAlmostEqual(chosen['peak_idler_n'],fresh['summary']['peak_idler_n'],7)
        self.assertAlmostEqual(chosen['idler_travel_mm'],fresh['geometry']['route']['depth_mm'],7)
        self.assertGreater(chosen['extra_path_mm'],8)

    def test_catalog_distinguishes_inner_and_overall_width(self):
        for ident,expected in [('tsubaki25',3.175),('iwis05b',3.16),('tsubaki35',4.7752),('tsubaki40',7.9248)]:
            item=chain_item(ChainConfig(chain_id=ident));self.assertAlmostEqual(item['inner_width_mm'],expected)
            self.assertGreater(item['width_mm'],item['inner_width_mm'])

if __name__=='__main__':unittest.main()
