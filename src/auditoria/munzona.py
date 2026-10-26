"""Conferência independente: o TSE agrega por município-zona (detalhe_votacao_munzona) e a soma das
seções tem de fechar com essa agregação.

Regra exata, verificada em 2022 e 2026: válidos(munzona) = nominais(seções) − nulos técnicos, e
QT_TOTAL_VOTOS_NULOS = QT_VOTOS_NULOS + QT_VOTOS_NULOS_TECNICOS. Em 2026 (1º turno) os nulos técnicos
somam 5.246 votos (candidato nº 28), que os arquivos de seção contam como válidos."""
import pathlib

import pandas as pd

from .load import ALL, read_member

ZONA = ['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_TURNO']
COLS = ['QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'QT_TOTAL_VOTOS_VALIDOS', 'QT_VOTOS_BRANCOS',
        'QT_VOTOS_NULOS', 'QT_VOTOS_NULOS_TECNICOS', 'QT_TOTAL_VOTOS_NULOS']


def _norm_mun(s):
    # o município vem com zeros à esquerda neste arquivo ('01007') e sem nas seções ('1007')
    return s.astype(int).astype(str)


def _reducer(turnos):
    def _reduce(ch):
        # turno que não está nas seções nem é agregado: o 2º turno de 2026 não entra antes do pré-registro
        ch = ch[ch.NR_TURNO.isin(turnos)]
        c = ch.assign(**{k: ch[k].astype(int) for k in COLS})
        c['CD_MUNICIPIO'] = _norm_mun(c.CD_MUNICIPIO); c['NR_ZONA'] = _norm_mun(c.NR_ZONA)
        return c.groupby(ZONA, as_index=False)[COLS].sum()
    return _reduce


def load_munzona(d, year, turnos):
    z = pathlib.Path(d) / f'detalhe_votacao_munzona_{year}.zip'
    parts = read_member(z, f'detalhe_votacao_munzona_{year}_BR.csv', ZONA + ['CD_CARGO'] + COLS, ALL + ['ZZ'],
                        _reducer(set(turnos)))
    return pd.concat(parts).groupby(ZONA)[COLS].sum()


def crosscheck(g, mz):
    """Compara a soma das seções (formato longo de load_sections) com o município-zona."""
    s = g.assign(CD_MUNICIPIO=_norm_mun(g.CD_MUNICIPIO), NR_ZONA=_norm_mun(g.NR_ZONA))
    s = s.groupby(ZONA)[['apt', 'comp', 'abst', 'nominais', 'brancos_d', 'nulos_d']].sum()
    j = mz.join(s, how='outer')
    sem_par = int(j.isna().any(axis=1).sum())
    j = j.dropna()   # contagem de sem par já feita acima; zonas sem par param o pipeline
    ruins = {
        'zonas sem par (só numa das fontes)': sem_par,
        'aptos': int((j.QT_APTOS != j.apt).sum()),
        'comparecimento': int((j.QT_COMPARECIMENTO != j.comp).sum()),
        'abstenções': int((j.QT_ABSTENCOES != j.abst).sum()),
        'brancos': int((j.QT_VOTOS_BRANCOS != j.brancos_d).sum()),
        'nulos (sem técnicos)': int((j.QT_VOTOS_NULOS != j.nulos_d).sum()),
        'válidos != nominais − nulos técnicos': int((j.QT_TOTAL_VOTOS_VALIDOS != j.nominais - j.QT_VOTOS_NULOS_TECNICOS).sum()),
        'total de nulos != nulos + técnicos': int((j.QT_TOTAL_VOTOS_NULOS != j.QT_VOTOS_NULOS + j.QT_VOTOS_NULOS_TECNICOS).sum()),
    }
    tecnicos = {str(t): int(v) for t, v in j.groupby('NR_TURNO').QT_VOTOS_NULOS_TECNICOS.sum().items()}
    return ruins, tecnicos
