import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from photo_album.cli import scan, render, finalize, verify_export, period_bounds, read, write, sha

class WorkflowTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.batch = self.root / 'batch'
        Image.new('RGB', (1600, 1000), '#416f60').save(self.source / '20270103_family.jpg')
        self.original = sha(self.source / '20270103_family.jpg')

    def scan(self, **overrides):
        args = dict(inputs=[str(self.source)], batch=str(self.batch), period='2027-Q1', timezone='UTC', profile='nixplay', label=None, reuse=None, width=None, height=None, max_bytes=None, file_max_bytes=None)
        args.update(overrides)
        scan(SimpleNamespace(**args))

    def ready(self, category='A'):
        self.scan()
        plans = read(self.batch / 'plan.json')
        plans[0].update(category=category, title='Park </script><script>bad()</script>', reason='Clear subject', ratings=dict(clarity=4, exposure=4, framing=4, expression=4, artifacts=4))
        write(self.batch / 'plan.json', plans)
        render(SimpleNamespace(batch=str(self.batch)))

    def choices(self, chosen='yes', digest=None):
        record = read(self.batch / 'rendered.json')[0]
        path = self.root / 'choices.csv'
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['source_id', 'chosen', 'reviewed_sha256'])
            writer.writeheader()
            writer.writerow(dict(source_id=record['id'], chosen=chosen, reviewed_sha256=digest or record['output_sha256']))
        return path

    def test_periods(self):
        self.assertEqual(tuple(map(str, period_bounds('2028-02'))), ('2028-02-01', '2028-03-01'))
        self.assertEqual(tuple(map(str, period_bounds('2027-Q4'))), ('2027-10-01', '2028-01-01'))
        self.assertEqual(tuple(map(str, period_bounds('2027-01-31:2027-02-01'))), ('2027-01-31', '2027-02-02'))
        with self.assertRaises(ValueError):
            period_bounds('2027-03-02:2027-02-01')

    def test_intake_reports_duplicates_unknown_and_errors(self):
        (self.source / '20270103_copy.jpg').write_bytes((self.source / '20270103_family.jpg').read_bytes())
        Image.new('RGB', (10, 10)).save(self.source / 'undated.jpg')
        (self.source / 'broken.jpg').write_text('bad')
        self.scan()
        report = read(self.batch / 'intake-report.json')
        self.assertEqual(report['photos'], 1)
        self.assertEqual(len(report['exact_duplicates']), 1)
        self.assertEqual(len(report['outside_period_or_unknown_date']), 1)
        self.assertEqual(len(report['errors']), 1)

    def test_takeout_timezone_boundary(self):
        source = self.source / '20270103_family.jpg'
        write(Path(str(source) + '.json'), {'photoTakenTime': {'timestamp': '1798759800'}})
        self.scan(period='2027-01', timezone='Asia/Kolkata')
        self.assertEqual(len(read(self.batch / 'inventory.json')), 1)

    def test_complete_export_and_tamper_detection(self):
        self.ready()
        target = self.root / 'final'
        finalize(SimpleNamespace(batch=str(self.batch), choices=str(self.choices()), output=str(target)))
        verify_export(target)
        self.assertEqual(sha(self.source / '20270103_family.jpg'), self.original)
        output = next((target / 'photos').iterdir())
        output.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            verify_export(target)

    def test_stale_review_rejected(self):
        self.ready()
        with self.assertRaisesRegex(ValueError, 'Stale'):
            finalize(SimpleNamespace(batch=str(self.batch), choices=str(self.choices(digest='wrong')), output=str(self.root / 'final')))

    def test_unresolved_category_rejected(self):
        self.ready('B')
        with self.assertRaisesRegex(ValueError, 'Only reviewed'):
            finalize(SimpleNamespace(batch=str(self.batch), choices=str(self.choices()), output=str(self.root / 'final')))

    def test_portrait_a_blocked_c_allowed(self):
        Image.new('RGB', (1000, 1600), 'white').save(self.source / '20270103_family.jpg')
        self.scan()
        plan = read(self.batch / 'plan.json')
        plan[0].update(category='A', reason='Portrait', ratings=dict(clarity=4, exposure=4, framing=4, expression=4, artifacts=4))
        write(self.batch / 'plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'fill'):
            render(SimpleNamespace(batch=str(self.batch)))
        plan[0]['category'] = 'C'
        write(self.batch / 'plan.json', plan)
        render(SimpleNamespace(batch=str(self.batch)))
        self.assertLess(read(self.batch / 'rendered.json')[0]['frame_coverage'], 0.995)

    def test_crop_protects_subject(self):
        self.scan()
        plan = read(self.batch / 'plan.json')
        plan[0].update(category='C', crop=[0, 0, 1000, 600], protected=[100, 100, 1500, 800])
        write(self.batch / 'plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'protected'):
            render(SimpleNamespace(batch=str(self.batch)))

    def test_budget_blocks_before_export(self):
        self.ready()
        config = read(self.batch / 'batch.json')
        config['max_bytes'] = 1
        write(self.batch / 'batch.json', config)
        target = self.root / 'final'
        with self.assertRaisesRegex(ValueError, 'budget'):
            finalize(SimpleNamespace(batch=str(self.batch), choices=str(self.choices()), output=str(target)))
        self.assertFalse(target.exists())

    def test_safe_html_and_no_source_paths(self):
        self.ready()
        page = (self.batch / 'review.html').read_text()
        self.assertNotIn('</script><script>bad()', page)
        self.assertNotIn(str(self.source), page)
        self.assertIn('\\u003c/script', page)

    def test_original_mutation_blocks_render(self):
        self.scan()
        (self.source / '20270103_family.jpg').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Original changed'):
            render(SimpleNamespace(batch=str(self.batch)))

    def test_reuse_is_only_hint(self):
        self.ready()
        old = self.batch
        self.batch = self.root / 'next'
        self.scan(reuse=str(old))
        plan = read(self.batch / 'plan.json')[0]
        self.assertEqual(plan['prior_category'], 'A')
        self.assertEqual(plan['category'], 'B')

    def test_sources_cannot_contain_batch(self):
        self.batch = self.source / 'batch'
        with self.assertRaisesRegex(ValueError, 'separate'):
            self.scan()
if __name__ == '__main__':
    unittest.main()
