import pathlib
import sys

from .load import ALL, load_sections
from .munzona import crosscheck, load_munzona
from .prereg import exige_prereg

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


def fechamento(dir, year, g, exige_munzona=False):
    """Fecha votação x detalhe por seção e a soma das seções x município-zona do TSE; para se falhar."""
    bad = reconcile(g)
    print('\nFechamento votação x detalhe, seções divergentes:')
    for k, v in bad.items():
        print(f'  {k}: {v}')
    if (pathlib.Path(dir) / f'detalhe_votacao_munzona_{year}.zip').exists():
        zonas, tecnicos = crosscheck(g, load_munzona(dir, year, set(g.NR_TURNO)))
        print(f'\nSoma das seções x detalhe município-zona (nulos técnicos reclassificados por turno: {tecnicos}):')
        for k, v in zonas.items():
            print(f'  {k}: {v}')
        bad = {**bad, **{f'munzona: {k}': v for k, v in zonas.items()}, 'nulos_tecnicos': tecnicos}
        falhou = any(v for k, v in bad.items() if k != 'nulos_tecnicos')
    else:
        # com dados reais (há MANIFEST.json) a conferência independente não é opcional
        if exige_munzona or (pathlib.Path(dir) / 'MANIFEST.json').exists():
            sys.exit(f'{year}: detalhe_votacao_munzona ausente; conferência independente obrigatória')
        print('[aviso] detalhe município-zona ausente: conferência independente não feita')
        falhou = any(bad.values())
    if falhou:
        sys.exit(f'{year}: fechamento falhou; nada foi gravado')
    return bad


def verify(dir, out, year, exige=True):
    g = load_sections(dir, year, ALL + ['ZZ'])
    if g.apt.isna().any():
        sys.exit(f'{year}: sem detalhe_votacao_secao; fechamento não verificável')
    # Os totais do 2º turno de 2026 já respondem Q1: só depois do pré-registro congelado.
    if exige and str(year) == '2026' and '2' in set(g.NR_TURNO):
        exige_prereg()
    bad = fechamento(dir, year, g)
    nac, uf = totais(g)
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    arquivos = [out / f'totais_nacionais_{year}.csv', out / f'totais_uf_{year}.csv']
    nac.to_csv(arquivos[0]); uf.to_csv(arquivos[1])
    print(f'\nTotais nacionais {year} (27 UFs + exterior ZZ):')
    print(nac.to_string())
    return {'fechamento': bad, 'arquivos': arquivos}
