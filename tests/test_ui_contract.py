"""Static HTML/CSS/JS contract checks, NOT browser, visual, or UI end-to-end tests.

These checks deliberately do not claim rendered layout, screenshots, contrast,
pointer behavior or responsive acceptance. Those require an authorized browser.
"""
import ast
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Inventory(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class StaticUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        cls.inventory = Inventory(cls.html)
        cls.elements = cls.inventory.elements
        cls.ids = {attrs['id'] for _, attrs in cls.elements if 'id' in attrs}
        source = ast.parse((ROOT / 'run.py').read_text(encoding='utf-8'))
        cls.routes = {}
        for item in ast.walk(source):
            if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'files' for t in item.targets):
                cls.routes = ast.literal_eval(item.value)

    def test_unique_ids_and_all_static_js_selectors_exist(self):
        counts = Counter(attrs['id'] for _, attrs in self.elements if 'id' in attrs)
        self.assertEqual([key for key, count in counts.items() if count > 1], [])
        pattern = r'''(?:q|\$|text|emptyChart|chart)\(\s*['"]#([A-Za-z][\w-]*)['"](?!\s*\+)'''
        for name in ('app.js', 'eod-ui.js', 'market-ui.js', 'themes.js'):
            script = (ROOT / 'web' / name).read_text(encoding='utf-8')
            referenced = set(re.findall(pattern, script))
            self.assertFalse(referenced - self.ids, f'{name}: missing {referenced - self.ids}')

    def test_navigation_and_accessibility_id_targets_exist(self):
        navigation = [(attrs['data-page'], attrs.get('href')) for tag, attrs in self.elements
                      if tag == 'a' and 'data-page' in attrs]
        self.assertEqual(set(navigation), {('monitor', '#monitor'), ('analysis', '#analysis'),
                                           ('calculator', '#calculator'), ('book', '#book'), ('alerts', '#alerts'), ('method', '#method')})
        for _, attrs in self.elements:
            href = attrs.get('href', '')
            if href.startswith('#'):
                self.assertIn(href[1:], self.ids)
            for attribute in ('aria-labelledby', 'aria-describedby', 'aria-controls', 'for'):
                for target in attrs.get(attribute, '').split():
                    self.assertIn(target, self.ids)

    def test_script_and_stylesheet_assets_exist_and_are_whitelisted(self):
        references = []
        for tag, attrs in self.elements:
            if tag == 'script':
                self.assertIn('src', attrs, 'No inline scripts allowed by CSP.')
                references.append(attrs['src'])
            if tag == 'link' and attrs.get('rel') == 'stylesheet':
                references.append(attrs['href'])
        self.assertTrue(references)
        for reference in references:
            self.assertTrue(reference.startswith('/') and not reference.startswith('//'))
            self.assertIn(reference, self.routes)
            filename, _ = self.routes[reference]
            self.assertTrue((ROOT / 'web' / filename).is_file())
        scripts = [attrs['src'] for tag, attrs in self.elements if tag == 'script']
        self.assertLess(scripts.index('/calculator-core.js'), scripts.index('/app.js'))
        self.assertLess(scripts.index('/app.js'), scripts.index('/eod-ui.js'))

    def test_filter_sort_and_theme_choices_match_contract(self):
        sort_fields = {attrs['data-sort'] for _, attrs in self.elements if 'data-sort' in attrs}
        self.assertEqual(sort_fields, {'date', 'open_vnd', 'high_vnd', 'low_vnd', 'close_vnd', 'volume_shares', 'source_value_vnd'})
        self.assertEqual({a['data-range'] for _, a in self.elements if 'data-range' in a}, {'1D','5D','1W','1M','3M','6M','YTD','1Y','3Y','5Y','MAX','CUSTOM'})
        self.assertEqual({a['data-theme-choice'] for _, a in self.elements if 'data-theme-choice' in a}, set())
        root = next(attrs for tag, attrs in self.elements if tag == 'html')
        self.assertEqual(root['data-theme'], 'red')

    def test_market_displays_start_empty_and_no_reference_png_background(self):
        for identifier in ('metric-return', 'metric-volume', 'metric-relative', 'metric-volatility'):
            self.assertRegex(self.html, rf'id="{identifier}"[^>]*>—</strong>')
        for identifier in ('eod-table-body', 'ranking-body'):
            self.assertIn(f'<tbody id="{identifier}"></tbody>', self.html)
        for filename in ('style.css', 'theme-tokens.css'):
            css = (ROOT / 'web' / filename).read_text(encoding='utf-8')
            self.assertNotRegex(css, r'(?is)url\([^)]*\.png(?:[?#][^)]*)?\)')
        self.assertNotIn('theme_1_reference.png', self.html)

    def test_literal_api_calls_are_relative_and_no_streaming_client(self):
        calls = []
        for filename in ('app.js', 'eod-ui.js', 'market-ui.js'):
            script = (ROOT / 'web' / filename).read_text(encoding='utf-8')
            calls += re.findall(r'''(?:request|fetch)\(\s*([`'"])(.*?)\1''', script, re.S)
            self.assertNotRegex(script, r'new\s+(?:WebSocket|EventSource|XMLHttpRequest)\s*\(')
        self.assertTrue(calls)
        for _, url in calls:
            self.assertTrue(url.startswith('/api/') and not url.startswith('//'), url)


if __name__ == '__main__':
    unittest.main()
