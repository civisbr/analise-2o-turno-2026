import pathlib
import sys

import polars as pl

from .load import ALL, load_sections
from .munzona import crosscheck, load_munzona
from .prereg import exige_prereg

CHECKS = {
    'válidos (votação) != nominais (detalhe)': pl.col('valid') != pl.col('nominais'),
    'brancos (votação) != brancos (detalhe)': pl.col('branco') != pl.col('brancos_d'),
    'nulos (votação) != nulos (detalhe)': pl.col('nulo') != pl.col('nulos_d'),
    'comparecimento != nominais + brancos + nulos': pl.col('comp') != pl.col('nominais') + pl.col('brancos_d') + pl.col('nulos_d'),
    'comparecimento + abstenções > aptos': pl.col('comp') + pl.col('abst') > pl.col('apt'),
}


def reconcile(g):
    """Fecha votação x detalhe seção a seção. Retorna {verificação: nº de seções divergentes}."""
    return {k: g.filter(f.fill_null(True)).height for k, f in CHECKS.items()}   # nulo conta como divergência


TOT_COLS = ['apt', 'comp', 'abstencao', 'valid', 'lula', 'flavio', 'terceira_via', 'branco', 'nulo']


def totais(g):
    c = g.with_columns(terceira_via=pl.col('valid') - pl.col('lula') - pl.col('flavio'), abstencao=pl.col('abst'))
    soma = lambda chave: c.group_by(chave).agg(pl.col(TOT_COLS).sum()).sort(chave)
    return soma('NR_TURNO'), soma(['SG_UF', 'NR_TURNO'])


def fechamento(dir, year, g, exige_munzona=False):
    """Fecha votação x detalhe por seção e a soma das seções x município-zona do TSE; para se falhar."""
    bad = reconcile(g)
    print('\nFechamento votação x detalhe, seções divergentes:')
    for k, v in bad.items():
        print(f'  {k}: {v}')
    if (pathlib.Path(dir) / f'detalhe_votacao_munzona_{year}.zip').exists():
        zonas, tecnicos = crosscheck(g, load_munzona(dir, year, set(g['NR_TURNO'].to_list())))
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
    if g['apt'].null_count():
        sys.exit(f'{year}: sem detalhe_votacao_secao; fechamento não verificável')
    # Os totais do 2º turno de 2026 já respondem Q1: só depois do pré-registro congelado.
    if exige and str(year) == '2026' and '2' in set(g['NR_TURNO'].to_list()):
        exige_prereg()
    bad = fechamento(dir, year, g)
    nac, uf = totais(g)
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    arquivos = [out / f'totais_nacionais_{year}.csv', out / f'totais_uf_{year}.csv']
    nac.write_csv(arquivos[0]); uf.write_csv(arquivos[1])
    print(f'\nTotais nacionais {year} (27 UFs + exterior ZZ):')
    with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_hide_dataframe_shape=True):
        print(nac)
    return {'fechamento': bad, 'arquivos': arquivos}
