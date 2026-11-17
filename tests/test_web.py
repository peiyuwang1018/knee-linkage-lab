"""Check static deployment boundaries and the shared solver entry point."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from build_site import build, ROOT
from kneelab.api import dispatch, dispatch_json


class BrowserBuildTests(unittest.TestCase):
    def test_public_artifact_contains_same_sources_and_relative_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = build(tmp)
            bundle = json.loads((site / 'kneelab-sources.json').read_text())
            for name, content in bundle.items():
                self.assertEqual(content, (ROOT / 'kneelab' / name).read_text())
            self.assertIn('api.py', bundle)
            self.assertIn('chains.json', bundle)
            self.assertFalse((site / 'server.py').exists())
            self.assertFalse((site / '.git').exists())
            for html in site.glob('*.html'):
                content = html.read_text()
                self.assertNotRegex(content, r'(?:href|src)="/(?!/)')
                for target in re.findall(r'(?:href|src)="\./([^"#?]+)', content):
                    self.assertTrue((site / target).is_file(), (html.name, target))
            for name in ('index.html', 'chain.html'):
                content = (site / name).read_text()
                self.assertIn('data-solver="browser"', content)
                self.assertIn('runtime.js', content)
                self.assertNotIn('data-solver="browser"', (ROOT / 'static' / name).read_text())

    def test_json_boundary_preserves_defaults_and_returns_real_csv(self):
        self.assertEqual(json.loads(dispatch_json('/api/defaults', 'null')), dispatch('/api/defaults'))
        csv = json.loads(dispatch_json('/api/cycle.csv', '{"config": {}}'))
        self.assertIsInstance(csv, str)
        self.assertGreater(len(csv.splitlines()), 240)
        with self.assertRaises(ValueError):
            dispatch('/api/cycle', [])
        with self.assertRaises(ValueError):
            dispatch('/api/not-a-solver', {})
