"""Serial release measurements with a small C wait4 supervisor."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
BASE = Path('/tmp/i13')
ENV = dict(os.environ, TMPDIR=str(BASE),
           XDG_STATE_HOME=str(BASE / 'xdg/state'),
           XDG_DATA_HOME=str(BASE / 'xdg/data'),
           XDG_CONFIG_HOME=str(BASE / 'xdg/config'),
           XDG_RUNTIME_DIR=str(BASE / 'xdg/run'), FERRET_NO_DAEMON='1')
ENV.pop('FERRET_I13_SECTION', None)
ENV.pop('FERRET_I13_POSTINGS', None)
RAW = ROOT / 'target/release/ferret'
PROTO = ROOT / 'target/i13-build/release/ferret'
QUERIES = {'literal': ['-name', 'Cargo.toml'],
           'glob': ['-name', '*checkpoint*.rs'],
           'regex': ['-regex', r'.*/read[^/]*[.]rs'],
           'absent': ['-name', 'i13-no-such-basename-8f0329']}


def run(command, env=ENV, output=None):
    if shutil.disk_usage(BASE).free < 4 * 1024**3:
        raise SystemExit('below 4 GiB free')
    with open(BASE / 'last-stderr', 'wb') as errors:
        result = subprocess.run([str(ROOT / 'target/i13-measure'),
                                 str(BASE / 'last-sample.json'),
                                 *[str(x) for x in command]], env=env,
                                stdout=output or subprocess.DEVNULL,
                                stderr=errors)
    if result.returncode:
        raise RuntimeError((command, result.returncode,
                            (BASE / 'last-stderr').read_text()))
    return json.loads((BASE / 'last-sample.json').read_text())



def emit(row):
    print(json.dumps(row), flush=True)


def queries(corpus, repeats, mode):
    catalog = BASE / f'{corpus}-catalog'
    start = BASE / ('tree' if corpus == 'real' else 'synthetic-tree')
    section = BASE / f'{corpus}-names.bin'
    if mode == 'raw':
        binary, env = RAW, ENV
    else:
        binary, env = PROTO, dict(ENV, FERRET_I13_SECTION=str(section))
        if mode == 'postings':
            env['FERRET_I13_POSTINGS'] = '1'
    for label, expression in QUERIES.items():
        command = [binary, '--index', catalog, 'find', start, *expression]
        with (BASE / f'{corpus}-{label}-{mode}.out').open('wb') as output:
            run(command, env, output)
        content = (BASE / f'{corpus}-{label}-{mode}.out').read_bytes()
        records = sorted(content.splitlines())
        digest = hashlib.sha256(b'\0'.join(records)).hexdigest()
        emit({'corpus': corpus, 'query': label, 'mode': mode,
              'rows': len(records), 'sorted_sha256': digest,
              'command': [str(x) for x in command]})
        for repeat in range(repeats):
            emit(dict(corpus=corpus, query=label, mode=mode, repeat=repeat,
                      **run(command, env)))


if __name__ == '__main__':
    if sys.argv[1] == 'query':
        queries(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    elif sys.argv[1] == 'once':
        emit(run(sys.argv[2:]))
