import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import main


class AuthenticationSecurityTests(unittest.TestCase):
    def test_unset_session_secret_changes_between_processes(self):
        env = dict(os.environ)
        env.pop('SESSION_SECRET', None)
        code = 'from app.core.config import SESSION_SECRET; print(SESSION_SECRET)'
        values = [subprocess.check_output([sys.executable, '-c', code], env=env, text=True).strip() for _ in range(2)]
        self.assertNotEqual(values[0], values[1])
        self.assertTrue(all(len(value) >= 48 for value in values))

    def test_missing_password_is_rejected(self):
        client = TestClient(main.app)
        with patch.object(main.config, 'AUTH_REQUIRED', True), patch.object(main.config, 'TEMP_PW', ''):
            self.assertEqual(client.post('/login', data={'username': main.config.TEMP_ID, 'password': 'qa'}).status_code, 401)
            self.assertEqual(client.get('/api/sync/status').status_code, 401)

    def test_configured_login_preserves_session(self):
        client = TestClient(main.app)
        with patch.object(main.config, 'AUTH_REQUIRED', True), patch.object(main.config, 'TEMP_PW', 'test-only-password'):
            response = client.post('/login', data={'username': main.config.TEMP_ID, 'password': 'test-only-password'}, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(client.get('/').status_code, 200)
