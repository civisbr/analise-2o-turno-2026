import datetime
import hashlib
import json
import pathlib
import platform
import subprocess

import numpy as np
import pandas as pd

BOOT_SEED = 11   # semente fixa do bootstrap em balance.py


def _git(*args):
    r = subprocess.run(['git', *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def write_run(cmd, year, argv, raw_dir, out_dir):
    """Registra como a saída foi gerada. 'tree_clean' falso significa que o commit não reproduz a saída."""
    raw, out = pathlib.Path(raw_dir), pathlib.Path(out_dir)
    manifest = raw / 'MANIFEST.json'
    info = {
        'comando': cmd,
        'ano': str(year),
        'argv': list(argv),
        'gerado_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'commit': _git('rev-parse', 'HEAD'),
        'tree_clean': _git('status', '--porcelain', '--', '.', ':(exclude)data') == '',
        'prereg_tag': _git('rev-parse', '-q', '--verify', 'refs/tags/prereg-v1^{commit}'),
        'versoes': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__},
        'semente_bootstrap': BOOT_SEED,
        'insumos': json.loads(manifest.read_text()) if manifest.exists() else None,
        'saidas': {p.name: _sha(p) for p in sorted(out.glob('*.csv'))},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / f'run_{cmd}_{year}.json').write_text(json.dumps(info, indent=2, ensure_ascii=False) + '\n')
    return info
