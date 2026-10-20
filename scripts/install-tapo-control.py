#!/usr/bin/env python3
"""Install only the reviewed, hash-pinned Tapo component; run root-owned copy."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request

VERSION = '7.2.8'
COMMIT = '057d7a8d0b47cbde283b77c19ca27bf4274b7594'
ARCHIVE_SHA256 = '15f65f7fe26f82d6321fc1c73d5ab3b35c90601839554638245afe5f11957519'
ARCHIVE = Path('/home/ishank/.local/share/home-hub/review/tapo-7.2.8/source.tar.gz')
CONFIG = Path('/srv/homeassistant/config')
STATE = Path('/var/lib/home-hub/tapo-install')
PREFIX = 'HomeAssistant-Tapo-Control-' + COMMIT + '/custom_components/tapo_control/'


def component_files(data):
    """Reject malformed archives before touching HA. Ignore all noncomponent code."""
    if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Pinned source archive hash mismatch')
    result = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for item in archive:
            if not item.name.startswith(PREFIX):
                continue
            name = item.name[len(PREFIX):]
            if not name:
                continue
            parts = PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or '\\' in name:
                raise ValueError('Unsafe component path')
            if item.isdir():
                continue
            if not item.isfile() or name in result or item.size > 4_000_000:
                raise ValueError('Unsupported component member')
            total += item.size
            if total > 20_000_000 or len(result) >= 500:
                raise ValueError('Component exceeds bounded size')
            source = archive.extractfile(item)
            if source is None:
                raise ValueError('Missing component member')
            result[name] = source.read()
    manifest = json.loads(result['manifest.json'])
    if manifest.get('domain') != 'tapo_control' or manifest.get('version') != VERSION:
        raise ValueError('Unexpected component manifest')
    if manifest.get('requirements') != ['pytapo==3.4.26', 'python-kasa[speedups]>=0.10.2']:
        raise ValueError('Unexpected dependency declarations')
    return result


# Keep component/pytapo callbacks from writing session URLs or camera payloads to
# HA logs, including exception traceback rendering. All component modules share
# this exact logger; upstream defaults are otherwise unchanged.
PRIVATE_LOG_FILTER = """
class _HomeHubPrivateLog(logging.Filter):
    def filter(self, record):
        if record.levelno < logging.WARNING:
            return False
        record.msg = "Tapo camera integration warning/error; detailed log suppressed for privacy."
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True
LOGGER.addFilter(_HomeHubPrivateLog())
"""


def privacy_patch(files):
    files = dict(files)
    needle = b'LOGGER = logging.getLogger("custom_components." + DOMAIN)'
    original = files['const.py']
    if original.count(needle) != 1:
        raise ValueError('Pinned component logger anchor changed')
    files['const.py'] = original.replace(needle, needle + PRIVATE_LOG_FILTER.encode())
    # HA itself logs setup exceptions, outside this logger filter. Replace the
    # twelve pinned setup raises with constant messages and no exception chain.
    text = files['__init__.py'].decode()
    lines = text.splitlines(keepends=True)
    patched = 0
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        expr = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if not isinstance(expr, ast.Name) or expr.id not in ('ConfigEntryAuthFailed', 'ConfigEntryNotReady'):
            continue
        if node.end_lineno != node.lineno:
            raise ValueError('Pinned setup exception shape changed')
        indent = lines[node.lineno-1][:node.col_offset]
        lines[node.lineno-1] = indent + 'raise ' + expr.id + '("Tapo setup failed; check local device settings") from None\n'
        patched += 1
    if patched != 12:
        raise ValueError('Pinned setup exception count changed')
    files['__init__.py'] = ''.join(lines).encode()
    return files


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def safe_directory(path):
    for ancestor in reversed((path, *path.parents)):
        if not ancestor.exists():
            ancestor.mkdir(mode=0o700)
        info = ancestor.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('Install directories must be root-owned and not writable by others')


def healthy():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8123/', timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run the installed root-owned script with sudo; no credentials are accepted by this script.')
    info = Path(__file__).resolve().stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit('Install this script root-owned before running it.')
    # Capture and validate the existing boundary; never change compose/network policy.
    observed = json.loads(run(['docker', 'inspect', 'homeassistant']))[0]
    host = observed['HostConfig']
    ports = host.get('PortBindings') or {}
    binds = ports.get('8123/tcp') or []
    if (host.get('Privileged') or host.get('NetworkMode') in ('host', 'none')
            or set(ports) != {'8123/tcp'} or len(binds) != 1
            or binds[0] != {'HostIp': '127.0.0.1', 'HostPort': '8123'}
            or 'ALL' not in (host.get('CapDrop') or [])
            or not any(str(x).startswith('no-new-privileges') for x in host.get('SecurityOpt') or [])):
        raise SystemExit('Home Assistant boundary differs from the reviewed private-bridge policy.')
    if not any(x.get('Destination') == '/config' and x.get('Source') == str(CONFIG) for x in observed['Mounts']):
        raise SystemExit('Unexpected HA config mount.')
    if not observed['State']['Running'] or not healthy():
        raise SystemExit('Home Assistant must be healthy before installation.')
    files = privacy_patch(component_files(ARCHIVE.read_bytes()))
    safe_directory(CONFIG)
    safe_directory(STATE)
    # Serialize separate invocations; never overwrite another install or component.
    import fcntl
    with (STATE / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        destination = CONFIG / 'custom_components' / 'tapo_control'
        if destination.exists() or destination.is_symlink():
            raise SystemExit('Tapo component already exists; leave it unchanged and review before replacing.')
        safe_directory(destination.parent)
        batch = Path(tempfile.mkdtemp(prefix='7.2.8-', dir=STATE))
        os.chmod(batch, 0o700)
        (batch / 'source.tar.gz').write_bytes(ARCHIVE.read_bytes())
        # Verify the privately retained rollback input as well.
        if hashlib.sha256((batch / 'source.tar.gz').read_bytes()).hexdigest() != ARCHIVE_SHA256:
            raise SystemExit('Source changed during preparation; HA was not modified.')
        before = {k: host.get(k) for k in ['NetworkMode', 'PortBindings', 'Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit', 'Privileged', 'CapDrop', 'SecurityOpt', 'RestartPolicy']}
        (batch / 'boundary-before.json').write_text(json.dumps(before, indent=2))
        staged = batch / 'tapo_control'
        staged.mkdir(mode=0o755)
        for name, data in files.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            path.write_bytes(data)
            path.chmod(0o644)
        manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        (batch / 'installed-files.json').write_text(json.dumps(manifest, sort_keys=True, indent=2))
        # Same filesystem staging avoids partial visibility. Copy privately to config,
        # then one rename publishes the complete component before the single restart.
        temporary = Path(tempfile.mkdtemp(prefix='.tapo-stage-', dir=destination.parent))
        try:
            for child in staged.iterdir():
                if child.is_dir():
                    shutil.copytree(child, temporary / child.name)
                else:
                    shutil.copy2(child, temporary / child.name)
            temporary.chmod(0o755)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        try:
            print('Pinned component installed. Restarting Home Assistant; existing integrations will briefly pause.', flush=True)
            run(['systemctl', 'restart', 'home-assistant.service'])
            for _ in range(90):
                if healthy():
                    after = json.loads(run(['docker', 'inspect', 'homeassistant']))[0]['HostConfig']
                    if before != {key: after.get(key) for key in before}:
                        raise RuntimeError('HA boundary changed unexpectedly')
                    print('Home Assistant HTTP is ready. Add Tapo: Cameras Control in Devices & services.')
                    print('This is installation only; device authentication and live-stream acceptance remain pending.')
                    print('Private install record:', batch)
                    return
                time.sleep(2)
            raise RuntimeError('HA did not become healthy within three minutes')
        except Exception:
            # Preserve failed files and HA state for diagnosis, rather than deleting them.
            shutil.move(str(destination), str(batch / 'rolled-back-component'))
            run(['systemctl', 'restart', 'home-assistant.service'])
            raise SystemExit('Component was rolled back and HA restart requested. Inspect private local HA logs before retrying.')


if __name__ == '__main__':
    main()
