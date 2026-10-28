"""Equivalência com a implementação em pandas: tests/golden/resultados_sintetico_pandas.json é o resultados.json que o
código em pandas gerou para os dados sintéticos (boot=50, sim=3). Qualquer mudança de biblioteca de dados tem de
reproduzi-lo, a menos de erro de arredondamento."""
import json
import math
import pathlib

from auditoria import analise as an
from synth import UFS

GOLDEN = pathlib.Path(__file__).parent / 'golden' / 'resultados_sintetico_pandas.json'


def _difs(a, b, caminho=''):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return [f'{caminho}: chaves {sorted(set(a) ^ set(b))[:3]}']
        return [d for k in sorted(a) for d in _difs(a[k], b[k], f'{caminho}/{k}')]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f'{caminho}: tamanho {len(a)} != {len(b)}']
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _difs(x, y, f'{caminho}[{i}]')]
    if isinstance(a, float) or isinstance(b, float):
        ok = a == b or (a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12))
        return [] if ok else [f'{caminho}: {a} != {b}']
    return [] if a == b else [f'{caminho}: {a} != {b}']


def test_resultados_iguais_ao_do_codigo_em_pandas(synth_dir, tmp_path):
    an.analise(synth_dir, tmp_path, 2026, 2022, UFS, min_valid=200, boot=50, n_sim=3)
    novo = json.loads((tmp_path / 'resultados.json').read_text(encoding='utf-8'))
    esperado = json.loads(GOLDEN.read_text(encoding='utf-8'))
    assert _difs(esperado, novo) == []
