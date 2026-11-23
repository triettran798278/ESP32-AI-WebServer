import importlib
import tempfile
import unittest
from pathlib import Path

accounts = importlib.import_module('platform-bridge.accounts')


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = accounts.AccountStore(Path(self.directory.name) / 'accounts.db')

    def test_login_logout_and_password_reset_revoke_sessions(self):
        self.store.create_user('alice', 'a sufficiently long password')
        self.assertIsNone(self.store.login('alice', 'wrong password'))
        token = self.store.login('alice', 'a sufficiently long password')
        self.assertEqual(self.store.session_user(token), 'alice')
        self.store.logout(token)
        self.assertIsNone(self.store.session_user(token))
        token = self.store.login('alice', 'a sufficiently long password')
        self.store.reset_password('alice', 'another long password')
        self.assertIsNone(self.store.session_user(token))
        self.assertIsNone(self.store.login('alice', 'a sufficiently long password'))
        self.assertIsNotNone(self.store.login('alice', 'another long password'))

    def test_rejects_duplicate_accounts_and_short_passwords(self):
        with self.assertRaises(ValueError):
            self.store.create_user('alice', 'short')
        self.store.create_user('alice', 'a sufficiently long password')
        with self.assertRaises(ValueError):
            self.store.create_user('alice', 'another long password')

    def test_password_suffix_is_not_ignored_and_sessions_expire(self):
        from unittest.mock import patch
        password = 'x' * 1024
        self.store.create_user('alice', password)
        self.assertIsNone(self.store.login('alice', password + 'x'))
        with patch.object(accounts.time, 'time', return_value=1000):
            token = self.store.login('alice', password)
        with patch.object(accounts.time, 'time', return_value=1000 + accounts.SESSION_SECONDS):
            self.assertIsNone(self.store.session_user(token))

    def test_agents_are_private_and_survive_reopen(self):
        self.store.create_user('alice', 'a sufficiently long password')
        self.store.create_user('bob', 'another long password')
        self.store.put_agent('alice', {'id': 'agent-a', 'name': 'Alice agent'})
        self.assertEqual(self.store.list_agents('bob'), [])
        self.assertIsNone(self.store.get_agent('bob', 'agent-a'))
        with self.assertRaises(ValueError):
            self.store.put_agent('bob', {'id': 'agent-a', 'name': 'Stolen'})
        reopened = accounts.AccountStore(self.store.path)
        self.assertEqual(reopened.get_agent('alice', 'agent-a')['name'], 'Alice agent')
        self.assertFalse(reopened.delete_agent('bob', 'agent-a'))
        self.assertTrue(reopened.delete_agent('alice', 'agent-a'))

    def test_login_rate_limit_is_persistent_and_expires(self):
        from unittest.mock import patch
        with patch.object(accounts.time, 'time', return_value=1000):
            for _ in range(10):
                self.assertTrue(self.store.record_attempt('127.0.0.1'))
            self.assertFalse(accounts.AccountStore(self.store.path).record_attempt('127.0.0.1'))
            self.assertTrue(self.store.record_attempt('127.0.0.2'))
        with patch.object(accounts.time, 'time', return_value=1300):
            self.assertTrue(self.store.record_attempt('127.0.0.1'))

    def test_account_database_is_not_world_readable(self):
        self.assertEqual(self.store.path.stat().st_mode & 0o077, 0)

    def test_concurrent_agent_edits_do_not_overwrite_other_agents(self):
        store_module = importlib.import_module('platform-bridge.store')
        self.store.create_user('alice', 'a sufficiently long password')
        self.store.put_agent('alice', {'id': 'a', 'name': 'A'})
        self.store.put_agent('alice', {'id': 'b', 'name': 'B'})
        first = store_module.PlatformStore(self.store, 'alice')
        second = store_module.PlatformStore(self.store, 'alice')
        first.update_agent('a', {'name': 'Changed A'})
        second.update_agent('b', {'name': 'Changed B'})
        self.assertEqual(self.store.get_agent('alice', 'a')['name'], 'Changed A')
        self.assertEqual(self.store.get_agent('alice', 'b')['name'], 'Changed B')

    def test_concurrent_edits_preserve_other_fields_of_same_agent(self):
        store_module = importlib.import_module('platform-bridge.store')
        self.store.create_user('alice', 'a sufficiently long password')
        self.store.put_agent('alice', {'id': 'a', 'name': 'A', 'role': 'Assistant'})
        first = store_module.PlatformStore(self.store, 'alice')
        second = store_module.PlatformStore(self.store, 'alice')
        first.update_agent('a', {'name': 'Updated'})
        second.update_agent('a', {'role': 'Monitor'})
        agent = self.store.get_agent('alice', 'a')
        self.assertEqual((agent['name'], agent['role']), ('Updated', 'Monitor'))

    def test_password_reset_prevents_inflight_old_password_login(self):
        import threading
        from unittest.mock import patch
        self.store.create_user('alice', 'a sufficiently long password')
        started, proceed = threading.Event(), threading.Event()
        real_hash = accounts._password_hash
        def delayed_hash(password, salt):
            if threading.current_thread().name == 'old-login':
                started.set()
                self.assertTrue(proceed.wait(5))
            return real_hash(password, salt)
        result = []
        with patch.object(accounts, '_password_hash', side_effect=delayed_hash):
            thread = threading.Thread(name='old-login', target=lambda: result.append(self.store.login('alice', 'a sufficiently long password')))
            thread.start()
            self.assertTrue(started.wait(5))
            self.store.reset_password('alice', 'another long password')
            proceed.set()
            thread.join(5)
        self.assertEqual(result, [None])

    def test_bootstrap_from_env_is_noop_when_unset_or_short_password(self):
        self.assertEqual(accounts.bootstrap_from_env(self.store, {}), {'created_user': False, 'created_agent': False})
        self.assertEqual(
            accounts.bootstrap_from_env(self.store, {'CONSOLE_USERNAME': 'admin'}),
            {'created_user': False, 'created_agent': False},
        )
        short = accounts.bootstrap_from_env(self.store, {'CONSOLE_USERNAME': 'admin', 'CONSOLE_PASSWORD': 'short'})
        self.assertFalse(short['created_user'])
        self.assertFalse(short['created_agent'])
        self.assertFalse(self.store.user_exists('admin'))

    def test_bootstrap_from_env_creates_user_and_starter_agent_idempotently(self):
        env = {
            'CONSOLE_USERNAME': 'admin',
            'CONSOLE_PASSWORD': 'admin-password-123',
            'THINGSBOARD_HOST': 'https://codehelpers.tech/',
            'THINGSBOARD_API_KEY': 'tb-machine-key',
        }
        first = accounts.bootstrap_from_env(self.store, env)
        self.assertTrue(first['created_user'])
        self.assertTrue(first['created_agent'])
        self.assertIsNotNone(self.store.login('admin', 'admin-password-123'))
        agents = self.store.list_agents('admin')
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]['integrations']['thingsboard']['host'], 'https://codehelpers.tech')
        self.assertEqual(agents[0]['integrations']['thingsboard']['api_key'], 'tb-machine-key')

        second = accounts.bootstrap_from_env(
            self.store,
            {
                'CONSOLE_USERNAME': 'admin',
                'CONSOLE_PASSWORD': 'different-password-999',
                'THINGSBOARD_HOST': 'https://other.example',
                'THINGSBOARD_API_KEY': 'other-key',
            },
        )
        self.assertEqual(second, {'created_user': False, 'created_agent': False, 'username': 'admin'})
        self.assertIsNotNone(self.store.login('admin', 'admin-password-123'))
        self.assertIsNone(self.store.login('admin', 'different-password-999'))
        agents_after = self.store.list_agents('admin')
        self.assertEqual(len(agents_after), 1)
        self.assertEqual(agents_after[0]['integrations']['thingsboard']['api_key'], 'tb-machine-key')

    def test_bootstrap_from_env_seeds_agent_for_existing_empty_user_and_isolates_ids(self):
        self.store.create_user('bob', 'bob-original-password')
        seeded = accounts.bootstrap_from_env(
            self.store,
            {
                'CONSOLE_USERNAME': 'bob',
                'CONSOLE_PASSWORD': 'ignored-new-password',
                'THINGSBOARD_HOST': 'http://192.168.1.20:8080',
                'THINGSBOARD_API_KEY': 'bob-key',
            },
        )
        self.assertFalse(seeded['created_user'])
        self.assertTrue(seeded['created_agent'])
        self.assertIsNotNone(self.store.login('bob', 'bob-original-password'))
        self.assertIsNone(self.store.login('bob', 'ignored-new-password'))

        alice = accounts.bootstrap_from_env(
            self.store,
            {'CONSOLE_USERNAME': 'alice', 'CONSOLE_PASSWORD': 'alice-password-123'},
        )
        self.assertTrue(alice['created_user'])
        self.assertTrue(alice['created_agent'])
        self.assertNotEqual(seeded['agent_id'], alice['agent_id'])
        self.assertEqual(len(self.store.list_agents('bob')), 1)
        self.assertEqual(len(self.store.list_agents('alice')), 1)
