"""Synthetic USB/ADB fixtures; no physical frame access."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('frame_diagnostics', Path(__file__).resolve().parents[1] / 'scripts/diagnose-frame.py')
assert SPEC is not None and SPEC.loader is not None
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


class FrameDiagnosticsTests(unittest.TestCase):
    def test_no_enumeration_is_not_an_adb_permissions_failure(self):
        self.assertEqual(DIAG.diagnosis([], [])[0], 'not-enumerated')

    def test_stock_mass_storage_is_not_adb(self):
        devices = [{'vendor': '1f3a', 'product': '1000', 'adb': False}]
        self.assertEqual(DIAG.diagnosis(devices, [])[0], 'usb-without-adb')

    def test_fel_is_not_android(self):
        devices = [{'vendor': '1f3a', 'product': 'efe8', 'adb': False}]
        self.assertEqual(DIAG.diagnosis(devices, [])[0], 'fel')

    def test_distinct_adb_failure_states(self):
        for state, expected in [('unauthorized', 'unauthorized'), ('offline', 'offline'), ('no permissions', 'permissions'), ('device', 'adb-available')]:
            with self.subTest(state=state):
                self.assertEqual(DIAG.diagnosis([], [state])[0], expected)
        self.assertEqual(DIAG.diagnosis([], [], adb_ok=False)[0], 'adb-host-error')

    def test_target_identifiers_are_not_retained(self):
        output = 'List of devices attached\nPRIVATE_TARGET_A device product:private\nPRIVATE_TARGET_B unauthorized\nPRIVATE_TARGET_C no permissions (missing udev rules)\n'
        states = DIAG.adb_states(output)
        self.assertEqual(states, ['device', 'unauthorized', 'no permissions'])
        self.assertNotIn('PRIVATE_TARGET', repr(states))

    def test_usb_interface_recognition_without_reading_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / '1-1'
            device.mkdir()
            (device / 'idVendor').write_text('18d1')
            (device / 'idProduct').write_text('1234')
            (device / 'serial').write_text('PRIVATE_SERIAL_NOT_TO_READ')
            interface = root / '1-1:1.0'
            interface.mkdir()
            for key, value in [('bInterfaceClass', 'ff'), ('bInterfaceSubClass', '42'), ('bInterfaceProtocol', '01')]:
                (interface / key).write_text(value)
            devices = DIAG.usb_devices(root)
            self.assertEqual(devices, [{'vendor': '18d1', 'product': '1234', 'adb': True}])
            self.assertEqual(DIAG.diagnosis(devices, [])[0], 'usb-adb-interface')
            self.assertNotIn('PRIVATE_SERIAL', repr(devices))


if __name__ == '__main__':
    unittest.main()
