import unittest,json,html,tempfile
from pathlib import Path
from ingest_reports import convert
from build_daily import Days,load_speediance_strap,load_whoop

class WearableReportTests(unittest.TestCase):
 def test_wearable_plot_survives_ingestion(self):
  spec={'title':'Overnight HRV','x':['10-19'],'axes':[{'label':'ms'}],'series':[{'label':'Speediance app','data':[32]}]}
  raw='<body><h1>Report</h1><section id="wearable-comparison"><h2>Comparison</h2><figure data-wearable-spec="'+html.escape(json.dumps(spec),quote=True)+'"><img src="data:image/svg+xml;base64,AA" alt="comparison"></figure></section></body>'
  report=convert(raw,'morning','2026-10-19')
  markup=report['blocks'][0]['html']
  self.assertIn('wearable-observation',markup);self.assertIn('data-spec=',markup);self.assertNotIn('data:image',markup)
  from htmldom import parse
  slot=parse(markup).find('div')
  self.assertEqual(json.loads(slot.attrs['data-spec']),spec)
 def test_device_cache_yields_only_valid_dated_recovery(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'speediance_strap').mkdir();(root/'speediance_strap/normalized.json').write_text(json.dumps({'records':{'2026-10-19':{'spd_recovery':35.3},'2026-10-18':{'spd_recovery':None}}}))
   days=Days();load_speediance_strap(root,days)
   self.assertEqual(days.d['2026-10-19']['spd_recovery'],35.3)
   self.assertNotIn('2026-10-18',days.d)
 def test_published_sleep_series_is_asleep(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'whoop_v2_latest.json').write_text(json.dumps({'sleep':{'records':[{'end':'2026-10-19T12:00:00Z','score':{'stage_summary':{'total_in_bed_time_milli':36000000,'total_light_sleep_time_milli':18000000,'total_rem_sleep_time_milli':7200000,'total_slow_wave_sleep_time_milli':3600000}}}]}}))
   days=Days();load_whoop(root,days);self.assertEqual(days.d['2026-10-19']['w_sleep_h'],8)
if __name__=='__main__':unittest.main()
