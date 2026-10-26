import pathlib
import sys

from .load import ALL, load_sections

CHECKS = {
    'válidos (votação) != nominais (detalhe)': lambda g: g.valid != g.nominais,
    'brancos (votação) != brancos (detalhe)': lambda g: g.branco != g.brancos_d,
    'nulos (votação) != nulos (detalhe)': lambda g: g.nulo != g.nulos_d,
    'comparecimento != nominais + brancos + nulos': lambda g: g.comp != g.nominais + g.brancos_d + g.nulos_d,
    'comparecimento + abstenções > aptos': lambda g: g.comp + g.abst > g.apt,
}


def reconcile(g):
    """Fecha votação x detalhe seção a seção. Retorna {verificação: nº de seções divergentes}."""
    return {k: int(f(g).sum()) for k, f in CHECKS.items()}


def totais(g):
    c = g.assign(terceira_via=g.valid - g.lula - g.flavio, abstencao=g.abst)
    cols = ['apt', 'comp', 'abstencao', 'valid', 'lula', 'flavio', 'terceira_via', 'branco', 'nulo']
    return (c.groupby('NR_TURNO')[cols].sum(), c.groupby(['SG_UF', 'NR_TURNO'])[cols].sum())


def verify(dir, out, year):
    g = load_sections(dir, year, ALL + ['ZZ'])
    if g.apt.isna().any():
        sys.exit(f'{year}: sem detalhe_votacao_secao; fechamento não verificável')
    bad = reconcile(g)
    nac, uf = totais(g)
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    nac.to_csv(out / f'totais_nacionais_{year}.csv'); uf.to_csv(out / f'totais_uf_{year}.csv')
    print(f'\nTotais nacionais {year} (27 UFs + exterior ZZ):')
    print(nac.to_string())
    print('\nFechamento votação x detalhe, seções divergentes:')
    for k, v in bad.items():
        print(f'  {k}: {v}')
    if any(bad.values()):
        sys.exit(f'{year}: fechamento falhou; pipeline parado')
