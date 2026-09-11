import unittest
from unittest.mock import patch
import modem

class ModemControls(unittest.TestCase):
    def test_diagnostics_clipboard_has_bounded_foreground_ownership(self):
        status = dict(ok=True, present=True, profiles=[])
        with patch.object(modem, 'snapshot', return_value=status), patch.object(modem, 'run') as run:
            self.assertIn('pasted', modem.action('copy'))
            self.assertEqual(run.call_args.args[0], ['wl-copy', '--foreground', '--paste-once'])
            self.assertEqual(run.call_args.kwargs['timeout'], 60)

    def test_wrong_sim_profiles_are_excluded(self):
        sim = {'OperatorIdentifier': '23450', 'SimIdentifier': 'sim-a'}
        self.assertTrue(modem.compatible({'sim-operator-id': '23450'}, sim))
        self.assertFalse(modem.compatible({'sim-operator-id': '23415'}, sim))
        self.assertFalse(modem.compatible({'sim-id': 'sim-b'}, sim))
        self.assertTrue(modem.compatible({}, sim))

    def test_profile_argument_cannot_select_unlisted_connection(self):
        status = dict(ok=True, present=True, radio=True, profiles=[{'uuid': 'allowed'}])
        with patch.object(modem, 'snapshot', return_value=status), patch.object(modem, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'compatible'):
                modem.action('connect', 'wifi-or-injected-profile')
            run.assert_not_called()

    def test_power_off_disables_nm_before_low_power(self):
        status = dict(ok=True, present=True, state=3, modem='/modem/0')
        with patch.object(modem, 'snapshot', return_value=status), patch.object(modem, 'run') as run:
            modem.action('power-off')
            commands = [c.args[0] for c in run.call_args_list]
            self.assertEqual(commands[0], ['nmcli', 'radio', 'wwan', 'off'])
            self.assertIn('--set-power-state-low', commands[-1])

    def test_hardware_block_prevents_power_on(self):
        with patch.object(modem, 'snapshot', return_value={'ok': True, 'hardwareEnabled': False}), patch.object(modem, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'hardware'):
                modem.action('power-on')
            run.assert_not_called()

    def test_power_on_retries_autoconnect_only_after_registration(self):
        initial = dict(ok=True, present=True, hardwareEnabled=True, power=2, modem='/modem/0',
                       profile='cell', profiles=[{'uuid': 'cell', 'autoconnect': True}])
        searching = dict(radio=False, radioEnabled=True, connected=False, registration=0, device='wwan0at1')
        registered = dict(radio=True, radioEnabled=True, connected=False, registration=5, device='wwan0at1')
        pending = dict(radio=False, radioEnabled=False, connected=False, registration=0)
        with patch.object(modem, 'snapshot', side_effect=[initial, pending, searching, registered]), \
             patch.object(modem, 'run') as run, patch.object(modem.time, 'sleep') as sleep:
            self.assertIn('connected', modem.action('power-on'))
            self.assertEqual(sleep.call_count, 2)
            self.assertIn('cell', run.call_args.args[0])
            self.assertIn('wwan0at1', run.call_args.args[0])

    def test_connectivity_test_requires_cellular_and_binds_interface(self):
        with patch.object(modem, 'snapshot', return_value={'ok': True, 'present': True, 'profiles': [], 'connected': False}):
            with self.assertRaisesRegex(RuntimeError, 'Connect cellular'):
                modem.action('test')
        status = dict(ok=True, present=True, profiles=[], connected=True, interface='wwan0')
        with patch.object(modem, 'snapshot', return_value=status), patch.object(modem, 'run', return_value='301 0.08') as run:
            self.assertIn('passed', modem.action('test'))
            command = run.call_args.args[0]
            self.assertEqual(command[command.index('--interface') + 1], 'wwan0')

if __name__ == '__main__':
    unittest.main()
