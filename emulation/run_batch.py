"""Run a fixed manifest sequentially, auditing each result before proceeding."""
import argparse
import json
from pathlib import Path
import subprocess
import gzip
import shutil

p = argparse.ArgumentParser()
p.add_argument('manifest')
p.add_argument('output')
args = p.parse_args()
root = Path(args.output)
root.mkdir(parents=True, exist_ok=False)
manifest = json.loads(Path(args.manifest).read_text())
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
for i, row in enumerate(manifest['runs']):
    output = root / f'run-{i:03d}'
    command = ['python3', '/experiment/run_policy.py', '--output', str(output)]
    for key, value in row.items(): command.extend(['--' + key.replace('_', '-'), str(value)])
    with (root / f'run-{i:03d}.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=row['seconds'] + 60)
        if result.returncode: raise RuntimeError(f'Run {i} failed; inspect retained log')
        subprocess.run(['python3', '/experiment/analyze_policy.py', str(output)],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    for path in output.glob('*.jsonl'):
        with path.open('rb') as source, gzip.open(str(path)+'.gz', 'wb') as target:
            shutil.copyfileobj(source, target)
        path.unlink()
    (root / 'progress.json').write_text(json.dumps({'completed': i + 1, 'total': len(manifest['runs'])}))
    print(f'Completed and audited {i + 1}/{len(manifest["runs"])}', flush=True)
(root / 'COMPLETE').write_text('All manifest runs completed and audited.\n')
