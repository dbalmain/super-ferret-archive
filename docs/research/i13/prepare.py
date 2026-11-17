"""Make a disposable prototype checkout inside this worktree's target dir."""
from pathlib import Path
import shutil
import subprocess

root = Path.cwd()
out = root / 'target/i13-prototype'
if out.exists():
    raise SystemExit(f'already exists: {out}')
files = subprocess.check_output(['git', 'ls-files', '-z']).split(b'\0')
for raw in files:
    if not raw:
        continue
    relative = Path(raw.decode())
    source = root / relative
    if not source.is_file():
        continue
    dest = out / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)

def edit(path, old, new):
    path = out / path
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'missing anchor: {path}: {old}')
    path.write_text(text.replace(old, new, 1))

catalog = 'crates/ferret-catalog/src/'
edit(catalog + 'read.rs', '    File {\n        file: File,',
     '    File {\n        names: OnceLock<Box<crate::ResidentNames>>,\n        file: File,')
edit(catalog + 'read.rs', 'source: Arc::new(Source::File {\n                file,',
     'source: Arc::new(Source::File {\n                names: OnceLock::new(),\n                file,')
edit(catalog + 'read.rs',
     'Ok(crate::log::Published::open(dir)?.map(crate::log::Published::into_catalog))',
     '''let catalog = crate::log::Published::open(dir)?.map(crate::log::Published::into_catalog);
        if let (Some(catalog), Some(path)) = (&catalog, std::env::var_os("FERRET_I13_SECTION")) {
            if let Source::File { names, .. } = catalog.source.as_ref() {
                let loaded = crate::ResidentNames::i13_read(Path::new(&path)).map_err(OpenError::Io)?;
                if loaded.row_count() != catalog.base_name_count() {
                    return Err(OpenError::Io(io::Error::other("wrong row count")));
                }
                let _ = names.set(Box::new(loaded));
            }
        }
        Ok(catalog)''')
edit(catalog + 'read.rs', 'Source::Resident { names, .. } => Some(names),',
     'Source::Resident { names, .. } => Some(names),\n            Source::File { names, .. } => names.get().map(Box::as_ref),')
edit(catalog + 'read/sections.rs', '            facts,\n        } =',
     '            facts,\n            names,\n        } =')
edit(catalog + 'read/sections.rs', '        let slot = &sections[section as usize];',
     '''        if section == Section::NameHeap && names.get().is_some() {
            return Ok(());
        }
        let slot = &sections[section as usize];''')
edit(catalog + 'read/sections.rs',
     '        let (start, end) = self.layout.range(section);\n        // Collected',
     '''        let (start, mut end) = self.layout.range(section);
        if section == Section::Names && names.get().is_some() {
            end = start + self.layout.columns[Column::NameOffset as usize].start;
        }
        // Collected''')
edit(catalog + 'read/sections.rs', '        format::check(section, &self.layout, facts, |s| {',
     '''        if section == Section::Names && names.get().is_some() {
            // Optimistic benchmark lower bound: skip full structural checks.
            let children = self.layout.blocked(Column::NameChild, &bytes);
            let dirs = (0..self.layout.names)
                .filter(|&row| children.get(row) < self.layout.dirs as u64).count();
            let _ = facts.dir_children.set(dirs);
        } else {
        format::check(section, &self.layout, facts, |s| {''')
edit(catalog + 'read/sections.rs', '        .map_err(OpenError::Decode)?;\n        let Ok(())',
     '        .map_err(OpenError::Decode)?;\n        }\n        let Ok(())')
edit(catalog + 'format/check.rs', '    dir_children: OnceLock<usize>,',
     '    pub(crate) dir_children: OnceLock<usize>,')
edit('crates/ferret/src/find.rs',
     '    catalog.load(&plan.catalog_sections()).map_err(failed)?;',
     '    if catalog.resident_names().is_some() && std::env::var_os("FERRET_I13_POSTINGS").is_some() {\n        catalog.load(&[ferret_catalog::Section::RetainedAt]).map_err(failed)?;\n    }\n    catalog.load(&plan.catalog_sections()).map_err(failed)?;')
# Both variants read only find's existing section set. Postings mode also
# constructs the same lazy planner used by the resident engine.
edit('crates/ferret/src/find.rs',
     '                plan.run_parallel(plan.parallel_catalog_source(*catalog), effects, workers)',
     '''                let index = (catalog.resident_names().is_some()
                    && std::env::var_os("FERRET_I13_POSTINGS").is_some())
                    .then(|| ferret_query::NameIndex::new(&catalog));
                plan.run_parallel(plan.indexed_catalog_source(*catalog, index.as_ref()), effects, workers)''')
(out / (catalog + 'resident_names/i13.rs')).parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / 'docs/research/i13/section.rs.txt', out / (catalog + 'resident_names/i13.rs'))
with (out / (catalog + 'resident_names.rs')).open('a') as file:
    file.write('\nmod i13;\n')
example = out / 'crates/ferret-bench/examples'
example.mkdir(exist_ok=True)
shutil.copy2(root / 'docs/research/i13/synthetic.rs.txt', example / 'i13-synthetic.rs')
(example / 'i13-section.rs').write_text('''
use std::path::Path;
use ferret_catalog::Catalog;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let catalog = Catalog::open(Path::new(&args[1]))?.ok_or("no catalog")?;
    catalog.load_all()?;
    let names = catalog.build_resident_names();
    names.i13_write(Path::new(&args[2]))?;
    println!("rows={} distinct={} bytes={}", names.row_count(), names.distinct_count(), names.bytes());
    Ok(())
}
''')
print(out)

original = subprocess.check_output([
    'git', 'show', 'd7105331^:crates/ferret-catalog/examples/synthetic.rs'], text=True)
original = original.replace('.unwrap_or_else(|| "unknown".to_owned())',
                            '.unwrap_or("unknown".to_owned())')
original = original.replace('let reset = std::fs::write("/proc/self/clear_refs", "5").is_ok();',
                            'let reset = false;')
original = original.replace('b"/synthetic"', 'b"/tmp/i13/synthetic-tree"')
(example / 'i13-dump.rs').write_text(original)

shutil.copy2(root / 'docs/research/i13/open.rs.txt', example / 'i13-open.rs')
