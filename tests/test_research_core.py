"""Synthetic known-answer fixtures only; not market findings or study results."""
import unittest,tempfile,json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from src.research_core import displayed_depth,label_window,replay,audit_research

class ResearchTests(unittest.TestCase):
    def test_verified_empty_bid_is_zero_depth_not_missing(self):
        c={'price_scale':1,'quantity_scale':1,'zero_pair_means_absent_level':True}
        r=displayed_depth([[0,0]]*3,[[101,10],[102,10],[0,0]],c)
        self.assertEqual(r['bid_depth'],'0');self.assertEqual(r['imbalance'],'-1');self.assertIsNone(r['spread_bps'])
        c['zero_pair_means_absent_level']=False
        with self.assertRaises(ValueError):displayed_depth([[0,0]]*3,[[101,10]]*3,c)

    def test_label_duration_and_censoring(self):
        start=datetime(2026,11,5,10,tzinfo=timezone(timedelta(hours=7)))
        rows=[{'timestamp':(start+timedelta(seconds=i)).isoformat(),'symbol':'TEST','session_id':'A','valid':True,'bid_depth':0 if 10<=i<=25 else 100} for i in range(61)]
        self.assertEqual(label_window(rows,0,0),1)
        rows[25]['bid_depth']=100;self.assertEqual(label_window(rows,0,0),0)
        rows[40]['valid']=False;self.assertIsNone(label_window(rows,0,0))

    def test_replay_receive_order_preserves_late_source_record(self):
        records=[{'topic':'quote.TEST','received_at':'2026-11-05T10:00:02+07:00','data':{'s':'TEST','t':'2026/11/05 10:00:02'}},
                 {'topic':'quote.TEST','received_at':'2026-11-05T10:00:03+07:00','data':{'s':'TEST','t':'2026/11/05 10:00:01'}}]
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'raw.jsonl';p.write_text('\n'.join(json.dumps(r) for r in records))
            out,m=replay([p]);self.assertTrue(out[1]['late']);self.assertEqual(m['events'],2)

    def test_actual_insufficient_data_never_becomes_h1_result(self):
        r=audit_research();self.assertEqual(r['h1'],'NOT_TESTED');self.assertFalse(r['prediction_available'])

    def test_logistic_training_known_sign(self):
        import numpy as np
        from src.research_models import fit,predict,metrics
        x=np.arange(-5,6,dtype=float).reshape(-1,1);y=(x[:,0]>0).astype(float)
        model=fit(x,y,.01);p=predict(model,x)
        self.assertLess(p[0],p[-1]);self.assertLess(metrics(y,p)['brier'],.25)
