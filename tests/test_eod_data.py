"""Synthetic local fixtures only; never used as market demo data."""
import copy
import csv
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from src.eod_snapshot import COLUMNS, validate_snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.tools' / 'test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.folder = Path(self.temp.name)
        self.row = dict(zip(COLUMNS, ['TEST', '2026-11-04', '100', '110', '90', '105', '1000', '',
                                     'provider_adjusted', 'test_source', 'https://example.com/data']))
        self.manifest = {'dataset_type': 'historical_eod_snapshot', 'asof_date': '2026-11-04',
            'asof_timezone': 'Asia/Ho_Chi_Minh', 'retrieved_at_utc': '2026-11-04T20:00:00+00:00',
            'symbols_requested': ['TEST'], 'symbols_loaded': ['TEST'], 'lookback_sessions_requested': 1,
            'units': {'price': 'VND/share', 'volume': 'share', 'turnover': 'VND'},
            'refresh_policy': 'manual_one_shot', 'adjustment_policy': 'provider_adjusted',
            'upstream_sources': [{'id': 'test_source', 'source_url': 'https://example.com/data',
                                  'documentation_url': 'https://example.com/docs', 'usage_note': 'test fixture only'}],
            'coverage_by_symbol': {'TEST': {'rows': 1, 'first_available_session': '2026-11-04',
                                          'last_available_session': '2026-11-04'}}, 'row_count': 1}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows=None, manifest=None):
        rows = [self.row] if rows is None else rows
        manifest = copy.deepcopy(self.manifest if manifest is None else manifest)
        with (self.folder/'ohlcv.csv').open('w', newline='', encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=COLUMNS);writer.writeheader();writer.writerows(rows)
        manifest['file_sha256']={'ohlcv.csv':sha256((self.folder/'ohlcv.csv').read_bytes()).hexdigest()}
        (self.folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        return manifest

    def test_valid_contract(self):
        self.write();result=validate_snapshot(self.folder)
        self.assertTrue(result['passed']);self.assertEqual(result['status'],'VALID')
        self.assertEqual(result['rows'][0]['close_vnd'],'105')

    def test_partial_coverage_truthful(self):
        m=copy.deepcopy(self.manifest);m['symbols_requested'].append('OTHER');m['lookback_sessions_requested']=90
        self.write(manifest=m);result=validate_snapshot(self.folder)
        self.assertTrue(result['passed']);self.assertEqual(result['status'],'PARTIAL')

    def test_handoff_quality_flag_does_not_override_checksum(self):
        self.write();(self.folder/'PHASE1_HANDOFF.json').write_text('{"status":"VALID","quality_gate":{"passed":true}}')
        with (self.folder/'ohlcv.csv').open('a') as f:f.write('\n')
        result=validate_snapshot(self.folder);self.assertFalse(result['passed']);self.assertEqual(result['rows'],[])

    def test_rejects_nonfinite_negative_and_invalid_ohlc(self):
        for field,value in [('open_vnd','NaN'),('high_vnd','Infinity'),('low_vnd','-1'),
                            ('high_vnd','99'),('low_vnd','106'),('close_vnd','0'),
                            ('volume_shares','-1'),('volume_shares','1.5'),('turnover_vnd','NaN')]:
            with self.subTest(field=field,value=value):
                row=dict(self.row);row[field]=value;self.write([row])
                self.assertFalse(validate_snapshot(self.folder)['passed'])

    def test_rejects_duplicate_and_empty(self):
        for rows in ([],[self.row,self.row]):
            self.write(rows);self.assertFalse(validate_snapshot(self.folder)['passed'])

    def test_rejects_future_or_weekend_sessions(self):
        for value in ('2026-11-05','2026-11-01','bad-date'):
            row=dict(self.row);row['date']=value;self.write([row])
            self.assertFalse(validate_snapshot(self.folder)['passed'])

    def test_rejects_source_or_policy_drift(self):
        for field,value in [('upstream_source',''),('source_url','https://example.net/unregistered'),
                            ('price_adjustment','unadjusted'),('symbol','OTHER')]:
            row=dict(self.row);row[field]=value;self.write([row])
            self.assertFalse(validate_snapshot(self.folder)['passed'])

    def test_rejects_manifest_units_coverage_and_cutoff_drift(self):
        for field,value in [('units',{'price':'points','volume':'share'}),('row_count',999),
                            ('asof_date','2026-11-05'),('retrieved_at_utc','2026-11-04T10:00:00'),
                            ('upstream_sources',[]),('adjustment_policy','unknown')]:
            m=copy.deepcopy(self.manifest);m[field]=value;self.write(manifest=m)
            self.assertFalse(validate_snapshot(self.folder)['passed'])

    def test_no_snapshot_is_blocked_not_fake(self):
        result=validate_snapshot(self.folder)
        self.assertFalse(result['passed']);self.assertEqual(result['status'],'BLOCKED');self.assertEqual(result['rows'],[])

    def test_malformed_metadata_does_not_raise(self):
        for field,value in [('retrieved_at_utc',123),('upstream_sources',[{'id':{},'usage_note':'x'}]),
                            ('upstream_sources',[{'id':'test_source','usage_note':'x','source_url':123,'documentation_url':'https://example.com'}])]:
            with self.subTest(field=field,value=value):
                m=copy.deepcopy(self.manifest);m[field]=value;self.write(manifest=m)
                self.assertFalse(validate_snapshot(self.folder)['passed'])

    def test_explicit_blocked_manifest_has_no_rows(self):
        m=copy.deepcopy(self.manifest);m['symbols_loaded']=[];m['issues']=['source blocked']
        (self.folder/'manifest.json').write_text(json.dumps(m))
        result=validate_snapshot(self.folder)
        self.assertFalse(result['passed']);self.assertEqual(result['issues'],['source blocked'])


if __name__=='__main__':unittest.main()
