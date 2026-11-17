"""Separate load and into_resident measurements, one warmup and seven runs."""
import json
import sys
sys.dont_write_bytecode = True
from measure import BASE, ENV, ROOT, run

corpus, mode = sys.argv[1:3]
env = dict(ENV)
if mode != 'raw':
    env['FERRET_I13_SECTION'] = str(BASE / f'{corpus}-names.bin')
for repeat in range(8):
    with (BASE / 'open-phases.json').open('wb') as output:
        measured = run([ROOT / 'target/i13-build/release/examples/i13-open',
                        BASE / f'{corpus}-catalog'], env, output)
    phases = json.loads((BASE / 'open-phases.json').read_text())
    print(json.dumps(dict(corpus=corpus, mode=mode, repeat=repeat,
                          **phases, **measured)), flush=True)
