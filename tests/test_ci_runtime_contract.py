import re
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CIRuntimeContractTest(unittest.TestCase):
    def test_security_dependency_floor(self):
        text = (ROOT / 'server/requirements.txt').read_text(encoding='utf-8')
        for package, minimum in [('pillow', (13, 0, 0)), ('cryptography', (50, 0, 0))]:
            match = re.search(rf'(?m)^{package}==(\d+)\.(\d+)\.(\d+)\s*$', text)
            self.assertIsNotNone(match)
            self.assertGreaterEqual(tuple(map(int, match.groups())), minimum)

    def test_ci_and_image_use_compatible_python_and_ship_migrations_config(self):
        workflow = (ROOT / '.github/workflows/docker-publish.yml').read_text(encoding='utf-8')
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('python-version: "3.12"', workflow)
        self.assertRegex(dockerfile, r'FROM python:3\.12-slim@sha256:[0-9a-f]{64}')
        self.assertIn('COPY alembic.ini ./alembic.ini', dockerfile)
        self.assertTrue((ROOT / 'server/migrations').is_dir())

    def test_vulnerability_audit_is_not_bypassed(self):
        workflow = (ROOT / '.github/workflows/docker-publish.yml').read_text(encoding='utf-8')
        self.assertIn('run: pip-audit -r server/requirements.txt', workflow)
        self.assertNotIn('--ignore-vuln', workflow)
        self.assertNotIn('continue-on-error: true', workflow)

    def test_frontend_security_floors_match_the_lockfile(self):
        package = json.loads((ROOT / 'web/package.json').read_text(encoding='utf-8'))
        lock = json.loads((ROOT / 'web/package-lock.json').read_text(encoding='utf-8'))
        for name, floor in [('axios', (1, 20, 0)), ('vue', (3, 5, 44)), ('vite', (7, 3, 7))]:
            spec = (package.get('dependencies', {}) | package.get('devDependencies', {}))[name]
            self.assertGreaterEqual(tuple(map(int, spec.lstrip('^').split('.'))), floor)
            self.assertGreaterEqual(tuple(map(int, lock['packages']['node_modules/' + name]['version'].split('.'))), floor)
            root_spec = (lock['packages'][''].get('dependencies', {}) | lock['packages'][''].get('devDependencies', {}))[name]
            self.assertEqual(spec, root_spec)
