import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import recover


class RecoveryTests(unittest.TestCase):
    def test_device_guard_rejects_other_hardware_and_shared_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            pci = Path(tmp) / 'devices/0000:02:00.0'
            driver = Path(tmp) / 'drivers/iosm'
            pci.mkdir(parents=True)
            driver.mkdir(parents=True)
            (pci / 'vendor').write_text('0x8086\n')
            (pci / 'device').write_text('0x7360\n')
            (pci / 'reset').touch()
            (pci / 'driver').symlink_to(driver)
            (driver / pci.name).symlink_to(pci)
            with patch.object(recover, 'PCI', pci), patch.object(recover, 'DRIVER', driver):
                self.assertTrue(recover.guarded_device())
                (pci / 'device').write_text('0x1234')
                self.assertFalse(recover.guarded_device())
                (pci / 'device').write_text('0x7360')
                (driver / '0000:03:00.0').symlink_to(pci)
                self.assertFalse(recover.guarded_device())

    def test_healthy_modem_is_not_reset(self):
        with patch.object(recover, 'run') as run, patch.object(recover, 'guarded_device', return_value=True), \
                patch.object(recover, 'wait_detected', return_value=True):
            recover.main()
            self.assertEqual(run.call_count, 1)

    def test_query_error_is_not_treated_as_missing_modem(self):
        with patch.object(recover, 'run', side_effect=['', 'invalid json']) as run, \
                patch.object(recover, 'guarded_device', return_value=True):
            with self.assertRaises(ValueError):
                recover.main()
            self.assertFalse(any('stop' in c.args for c in run.call_args_list))

    def test_failed_reset_restores_driver_and_service(self):
        with patch.object(recover, 'run') as run, patch.object(recover, 'guarded_device', return_value=True), \
                patch.object(recover, 'wait_detected', return_value=False), patch.object(recover, 'PCI') as pci:
            pci.joinpath.return_value.write_text.side_effect = OSError('reset failed')
            with self.assertRaises(OSError):
                recover.main()
            self.assertEqual(run.call_args_list[-2].args, ('/usr/bin/modprobe', 'iosm'))
            self.assertEqual(run.call_args_list[-1].args, ('/usr/bin/systemctl', 'start', 'ModemManager.service'))

    def test_only_one_reset_when_recovery_fails(self):
        with patch.object(recover, 'run'), patch.object(recover, 'guarded_device', return_value=True), \
                patch.object(recover, 'wait_detected', return_value=False), patch.object(recover, 'PCI') as pci:
            with self.assertRaisesRegex(RuntimeError, 'still unavailable'):
                recover.main()
            pci.joinpath.return_value.write_text.assert_called_once_with('1\n')


if __name__ == '__main__':
    unittest.main()
