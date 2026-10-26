import datetime
import hashlib
import json
import pathlib
import platform
import subprocess
import sys

import numpy as np
import pandas as pd

from .robust import BOOT_SEED, CLOSING_SEED

SEEDS = {'balanco': BOOT_SEED, 'analyze': CLOSING_SEED}


ROOT = pathlib.Path(__file__).resolve().parents[2]


def _git(*args):
    r = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sanitiza_argv(argv):
    """Caminho absoluto vira relativo à raiz do projeto, ou <externo>: o JSON é versionado."""
    out = []
    for a in argv:
        pre, sep, val = a.partition('=') if a.startswith('--') else ('', '', a)
        if val.startswith('/'):
            p = pathlib.Path(val).resolve()
            val = str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else '<externo>'
        out.append(pre + sep + val)
    return out


def confere_insumos(raw_dir):
    """Recalcula o SHA-256 dos zips presentes e compara com o MANIFEST.json; devolve os hashes lidos."""
    raw = pathlib.Path(raw_dir); manifest = raw / 'MANIFEST.json'
    if not manifest.exists():
        return None
    reg = json.loads(manifest.read_text()); lidos = {}
    for nome, rec in reg.items():
        f = raw / nome
        if not f.exists():
            continue
        h = _sha(f)
        if h != rec['sha256']:
            sys.exit(f'{nome}: SHA-256 difere do MANIFEST.json (arquivo alterado ou corrompido)')
        lidos[nome] = {'sha256': h, 'bytes': rec['bytes'], 'url': rec['url'], 'last_modified': rec.get('last_modified')}
    return lidos


def write_run(cmd, year, argv, out_dir, insumos, fechamento=None, arquivos=None):
    """Registra como a saída foi gerada. 'tree_clean' falso significa que o commit não reproduz a saída."""
    out = pathlib.Path(out_dir)
    saidas = [pathlib.Path(a) for a in arquivos] if arquivos else sorted(out.glob('*.csv'))
    info = {
        'comando': cmd,
        'ano': str(year),
        'argv': sanitiza_argv(argv),
        'gerado_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'commit': _git('rev-parse', 'HEAD'),
        'tree_clean': _git('status', '--porcelain', '--', ':/', ':(exclude,top)data/derived') == '',
        'prereg_tag': _git('rev-parse', '-q', '--verify', 'refs/tags/prereg-v1^{commit}'),
        'versoes': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__},
        'semente': SEEDS.get(cmd),
        'insumos': insumos,
        'fechamento_secoes_divergentes': fechamento,
        'saidas': {p.name: _sha(p) for p in saidas},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / f'run_{cmd}_{year}.json').write_text(json.dumps(info, indent=2, ensure_ascii=False) + '\n')
    return info
