"""Launch to first protocol greeting with state ready; no query startup cost."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
sys.dont_write_bytecode = True
from measure import BASE, ENV, ROOT

corpus, mode = sys.argv[1:3]
if mode != 'raw':
    raise SystemExit('daemon measurements use the unmodified baseline only')
source = BASE / f'{corpus}-catalog'
copy = BASE / f'{corpus}-daemon-{mode}'
binary = ROOT / ('target/release/ferretd' if mode == 'raw' else 'target/i13-build/release/ferretd')
env = dict(ENV)
env.pop('FERRET_NO_DAEMON', None)
if mode != 'raw':
    env['FERRET_I13_SECTION'] = str(BASE / f'{corpus}-names.bin')
for repeat in range(8):
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(source, copy, ignore=shutil.ignore_patterns('index'))
    metadata = copy.stat()
    endpoint = Path(ENV['XDG_RUNTIME_DIR']) / 'ferret' / f'{metadata.st_dev:x}-{metadata.st_ino:x}.sock'
    if shutil.disk_usage(BASE).free < 4 * 1024**3:
        raise SystemExit('below 4 GiB free')
    start = time.perf_counter_ns()
    with (BASE / 'daemon-stderr').open('wb') as error:
        process = subprocess.Popen([str(binary), '--index', str(copy), '--idle-ms', '10000'],
                                   env=env, stdout=subprocess.DEVNULL, stderr=error)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError((BASE / 'daemon-stderr').read_text())
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(2)
                        client.connect(str(endpoint))
                        hello = client.makefile('rb').readline()
                        data = json.loads(hello)
                        if data.get('state') == 'ready':
                            elapsed = (time.perf_counter_ns() - start) / 1e6
                            print(json.dumps(dict(corpus=corpus, mode=mode,
                                                  repeat=repeat, ready_ms=elapsed)), flush=True)
                            break
                        if data.get('state') == 'error':
                            raise RuntimeError(data)
                except (FileNotFoundError, ConnectionRefusedError):
                    pass
                time.sleep(0.001)
            else:
                raise TimeoutError('daemon not ready within 60 seconds')
        finally:
            process.terminate()
            process.wait(timeout=10)
