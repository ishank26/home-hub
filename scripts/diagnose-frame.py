#!/usr/bin/env python3
"""Read-only Linux USB/ADB diagnosis; never connects, installs, flashes or reads serials.

The ADB client may start its host daemon. Printed output deliberately omits USB
serials, ADB target identifiers, network addresses and credentials.
"""
import argparse
import subprocess
import time
from pathlib import Path


def usb_devices(root=Path('/sys/bus/usb/devices')):
    devices = []
    if not root.is_dir():
        return devices
    for entry in sorted(root.iterdir()):
        try:
            vendor = (entry / 'idVendor').read_text().strip().lower()
            product = (entry / 'idProduct').read_text().strip().lower()
        except OSError:
            continue
        adb_interface = False
        for interface in root.glob(entry.name + ':*'):
            try:
                fields = tuple((interface / name).read_text().strip().lower()
                               for name in ('bInterfaceClass', 'bInterfaceSubClass', 'bInterfaceProtocol'))
            except OSError:
                continue
            adb_interface = adb_interface or fields == ('ff', '42', '01')
        if vendor in ('1f3a', '2207') or adb_interface:
            devices.append({'vendor': vendor, 'product': product, 'adb': adb_interface})
    return devices


def adb_states(output):
    states = []
    for line in output.splitlines():
        if not line.strip() or line.startswith(('List of devices', '*')):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        state = 'no permissions' if 'no permissions' in line else fields[1]
        if state in ('device', 'offline', 'unauthorized', 'no permissions', 'recovery', 'sideload'):
            states.append(state)
    return states


def diagnosis(devices, states, adb_ok=True):
    if not adb_ok:
        return 'adb-host-error', 'ADB client failed or is unavailable. Check the host installation/daemon before interpreting an empty list.'
    if 'no permissions' in states:
        return 'permissions', 'A USB target is present but access is denied. Review Android udev rules and device-node permissions; do not run the dashboard as root.'
    if 'unauthorized' in states:
        return 'unauthorized', 'ADB is exposed but authorization is pending. Accept the existing on-frame debugging prompt if available; do not bypass it.'
    if 'offline' in states:
        return 'offline', 'ADB sees a target but cannot communicate. Check stable power/data connection, then retry the host daemon; no firmware write is justified.'
    if 'device' in states:
        return 'adb-available', 'An authorized ADB target is available. Confirm that it is the frame and inventory its model/firmware before any write.'
    if any(d['vendor'] == '1f3a' and d['product'] == 'efe8' for d in devices):
        return 'fel', 'Allwinner FEL is enumerated, not Android ADB. Stop and verify the board/recovery procedure; FEL alone is not a backup.'
    if any(d['adb'] for d in devices):
        return 'usb-adb-interface', 'Linux sees an ADB USB interface but the client has no usable target. Investigate host daemon/access rules before firmware changes.'
    if devices:
        return 'usb-without-adb', 'Linux sees a candidate frame but no ADB interface. A33 stock 1f3a:1000 is commonly mass-storage-only; verify the model and firmware before choosing an access route.'
    return 'not-enumerated', 'No known frame or ADB USB interface is enumerated. ADB permissions cannot explain missing USB enumeration. Verify power, a proven A-to-C data cable, and a direct USB-A port; then physically reconnect.'


def inspect():
    try:
        result = subprocess.run(['adb', 'devices', '-l'], capture_output=True, text=True, timeout=10)
        states = adb_states(result.stdout) if result.returncode == 0 else []
        adb_ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        states, adb_ok = [], False
    devices = usb_devices()
    code, message = diagnosis(devices, states, adb_ok)
    print('USB candidates:', ', '.join(d['vendor'] + ':' + d['product'] for d in devices) or 'none', flush=True)
    print('ADB states (target identifiers omitted):', ', '.join(states) or 'none', flush=True)
    print('Diagnosis:', code, flush=True)
    print(message, flush=True)
    print('No frame writes/network connections performed. Device identity, backup and approval gates still apply.', flush=True)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', type=int, default=0, metavar='SECONDS', help='repeat read-only checks while you reconnect (maximum 120 seconds)')
    args = parser.parse_args()
    if not 0 <= args.watch <= 120:
        parser.error('--watch must be 0..120 seconds')
    deadline = time.monotonic() + args.watch
    code = inspect()
    while args.watch and time.monotonic() < deadline and code != 'adb-available':
        time.sleep(min(5, max(0, deadline - time.monotonic())))
        code = inspect()
    return 0 if code == 'adb-available' else 2


if __name__ == '__main__':
    raise SystemExit(main())
