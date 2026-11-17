"""Copy tracked source files from each checkout, excluding build artifacts."""
import pathlib
import shutil
import subprocess

out = pathlib.Path('/tmp/i13/tree')
if shutil.disk_usage('/tmp').free < 4 * 1024**3:
    raise SystemExit('below 4 GiB free')
worktrees = subprocess.check_output(['git', 'worktree', 'list', '--porcelain'], text=True)
count = 0
for row in worktrees.splitlines():
    if not row.startswith('worktree '):
        continue
    source = pathlib.Path(row[9:])
    label = 'main' if source.name == 'super-ferret' else source.name
    files = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z'])
    for raw in files.split(b'\0'):
        if not raw:
            continue
        relative = pathlib.Path(raw.decode())
        original = source / relative
        if not original.is_file() or original.is_symlink():
            continue
        dest = out / label / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, dest)
        count += 1
print(f'copied_files={count}')
