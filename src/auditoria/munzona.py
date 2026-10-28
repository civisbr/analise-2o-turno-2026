"""Conferência independente: o TSE agrega por município-zona (detalhe_votacao_munzona) e a soma das
seções tem de fechar com essa agregação.

Regra exata, verificada em 2022 e 2026: válidos(munzona) = nominais(seções) − nulos técnicos, e
QT_TOTAL_VOTOS_NULOS = QT_VOTOS_NULOS + QT_VOTOS_NULOS_TECNICOS. Em 2026 (1º turno) os nulos técnicos
somam 5.246 votos (candidato nº 28), que os arquivos de seção contam como válidos."""
import pathlib

import polars as pl

from .load import ALL, read_member

ZONA = ['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_TURNO']
COLS = ['QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'QT_TOTAL_VOTOS_VALIDOS', 'QT_VOTOS_BRANCOS',
        'QT_VOTOS_NULOS', 'QT_VOTOS_NULOS_TECNICOS', 'QT_TOTAL_VOTOS_NULOS']


def _norm_mun(c):
    # o município vem com zeros à esquerda neste arquivo ('01007') e sem nas seções ('1007')
    return pl.col(c).cast(pl.Int64).cast(pl.Utf8)


def _reducer(turnos):
    def _reduce(ch):
        # turno que não está nas seções nem é agregado: o 2º turno de 2026 não entra antes do pré-registro
        ch = ch.filter(pl.col('NR_TURNO').is_in(list(turnos)))
        c = ch.with_columns([pl.col(k).cast(pl.Int64) for k in COLS]).with_columns(
            CD_MUNICIPIO=_norm_mun('CD_MUNICIPIO'), NR_ZONA=_norm_mun('NR_ZONA'))
        return c.group_by(ZONA).agg(pl.col(COLS).sum())
    return _reduce


def load_munzona(d, year, turnos):
    z = pathlib.Path(d) / f'detalhe_votacao_munzona_{year}.zip'
    parts = read_member(z, f'detalhe_votacao_munzona_{year}_BR.csv', ZONA + ['CD_CARGO'] + COLS, ALL + ['ZZ'],
                        _reducer(set(turnos)))
    return pl.concat(parts).group_by(ZONA).agg(pl.col(COLS).sum()).sort(ZONA)


def crosscheck(g, mz):
    """Compara a soma das seções (formato longo de load_sections) com o município-zona."""
    s = (g.with_columns(CD_MUNICIPIO=_norm_mun('CD_MUNICIPIO'), NR_ZONA=_norm_mun('NR_ZONA'))
          .group_by(ZONA).agg(pl.col(['apt', 'comp', 'abst', 'nominais', 'brancos_d', 'nulos_d']).sum()))
    j = mz.join(s, on=ZONA, how='full', coalesce=True)
    sem_par = j.filter(pl.any_horizontal(pl.all().is_null())).height
    j = j.drop_nulls()   # contagem de sem par já feita acima; zonas sem par param o pipeline
    n = lambda cond: j.filter(cond).height
    ruins = {
        'zonas sem par (só numa das fontes)': sem_par,
        'aptos': n(pl.col('QT_APTOS') != pl.col('apt')),
        'comparecimento': n(pl.col('QT_COMPARECIMENTO') != pl.col('comp')),
        'abstenções': n(pl.col('QT_ABSTENCOES') != pl.col('abst')),
        'brancos': n(pl.col('QT_VOTOS_BRANCOS') != pl.col('brancos_d')),
        'nulos (sem técnicos)': n(pl.col('QT_VOTOS_NULOS') != pl.col('nulos_d')),
        'válidos != nominais − nulos técnicos': n(pl.col('QT_TOTAL_VOTOS_VALIDOS') != pl.col('nominais') - pl.col('QT_VOTOS_NULOS_TECNICOS')),
        'total de nulos != nulos + técnicos': n(pl.col('QT_TOTAL_VOTOS_NULOS') != pl.col('QT_VOTOS_NULOS') + pl.col('QT_VOTOS_NULOS_TECNICOS')),
    }
    tec = j.group_by('NR_TURNO').agg(pl.col('QT_VOTOS_NULOS_TECNICOS').sum()).sort('NR_TURNO')
    tecnicos = {str(t): int(v) for t, v in tec.iter_rows()}
    return ruins, tecnicos
