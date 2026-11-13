import unittest
from kneelab.statistics import sampled_force_extrema
from kneelab.model import cycle, Config


def sample(value, t, valid=True):
    return dict(forces=[value] if value is not None else None,
                t=t, q_deg=10*t, valid=valid)


class StatisticsTests(unittest.TestCase):
    def test_signed_extrema_and_first_occurrence(self):
        rows=[sample(v,i/10) for i,v in enumerate([0,12,2,-3,-45,12,-.5])]
        stats=sampled_force_extrema(rows,0)
        self.assertEqual([stats[k]['force_n'] for k in
                          ('min_positive','max_positive','min_negative','max_negative')],
                         [2,12,-45,-.5])
        self.assertEqual(stats['max_positive']['frame'],1)
        self.assertEqual(stats['min_negative']['t_s'],.4)
        self.assertEqual(stats['min_negative']['q_deg'],4)

    def test_missing_sign_invalid_and_zero_noise(self):
        rows=[sample(1e-8,0),sample(-1e-8,.1),sample(999,.2,False),
              sample(None,.3),sample(float('nan'),.4),sample(5,.5)]
        stats=sampled_force_extrema(rows,0)
        self.assertEqual(stats['min_positive']['force_n'],5)
        self.assertIsNone(stats['min_negative'])
        self.assertIsNone(stats['max_negative'])
        self.assertTrue(all(v is None for v in sampled_force_extrema([],0).values()))

    def test_cycle_statistics_point_back_to_valid_samples(self):
        for c in (Config(),Config(n=3,spacing_deg=120),Config(n=1),
                  Config(n=1,q_start_deg=-122,q_end_deg=-118)):
            result=cycle(c)
            for i,stats in enumerate(result['summary']['rods']):
                for event in stats['extrema'].values():
                    if event is None:continue
                    row=result['rows'][event['frame']]
                    self.assertTrue(row['valid'])
                    self.assertEqual(event['force_n'],row['forces'][i])
                    self.assertEqual(event['t_s'],row['t'])
                positives=[r['forces'][i] for r in result['rows'] if r['valid'] and r['forces'][i]>1e-6]
                negatives=[r['forces'][i] for r in result['rows'] if r['valid'] and r['forces'][i]<-1e-6]
                if positives:self.assertEqual(stats['extrema']['max_positive']['force_n'],max(positives))
                if negatives:self.assertEqual(stats['extrema']['min_negative']['force_n'],min(negatives))


if __name__=='__main__':unittest.main()
