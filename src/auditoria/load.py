"""Leitura dos arquivos de seção do TSE (layout verificado em 26/10/2026, iguais em 2022 e 2026).

  votacao_secao/votacao_secao_<ano>_BR.zip   membro votacao_secao_<ano>_BR.csv: todas as UFs, só cargo
        Presidente (CD_CARGO 1); SG_UF é a UF real da seção. Os zips por UF só trazem cargos estaduais.
        NR_TURNO, CD_CARGO, SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO, NR_VOTAVEL, QT_VOTOS
  detalhe_votacao_secao/detalhe_votacao_secao_<ano>.zip   arquivo nacional único; membro
        detalhe_votacao_secao_<ano>_BR.csv (Presidente): QT_APTOS, QT_COMPARECIMENTO
  CSV com ';', aspas, latin1. NR_VOTAVEL: 13 = Lula, 22 = Flávio/Bolsonaro, 95 = branco, 96 = nulo.
O exterior (ZZ) fica fora de ALL; tratamento previsto na Fase 2.
"""
import pathlib
import sys
import zipfile

import numpy as np
import pandas as pd

NE = ['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE']
ALL = sorted(NE + ['AC', 'AM', 'AP', 'DF', 'ES', 'GO', 'MG', 'MS', 'MT', 'PA', 'PR', 'RJ', 'RO', 'RR', 'RS',
                   'SC', 'SP', 'TO'])

KEY = ['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']
LULA, FLAVIO = 13, 22
NONVALID = (95, 96)
VOTOS_COLS = ['lula', 'flavio', 'valid', 'branco', 'nulo']
DETALHE_COLS = ['apt', 'comp', 'abst', 'nominais', 'brancos_d', 'nulos_d']


def resolve_ufs(s):
    s = (s or 'NE').upper()
    if s == 'NE':
        return NE
    if s == 'ALL':
        return ALL
    ufs = [u.strip() for u in s.split(',') if u.strip()]
    bad = [u for u in ufs if u not in ALL]
    if bad:
        sys.exit(f'UF inválida em --ufs: {bad}')
    return ufs


def need(df, cols, name):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        sys.exit(f'{name}: colunas ausentes {miss}. Colunas presentes: {list(df.columns)}')


def read_member(zip_path, member, usecols, ufs, reduce, chunksize=1_000_000):
    """Lê o CSV nacional (>1 GB) em blocos, filtra Presidente das UFs pedidas e reduz cada bloco
    com `reduce` antes de acumular, para não segurar milhões de linhas de texto em memória."""
    parts = []
    with zipfile.ZipFile(zip_path) as z:
        if member not in z.namelist():
            sys.exit(f'{zip_path}: membro {member} ausente. Membros: {z.namelist()}')
        with z.open(member) as f:
            header = pd.read_csv(f, sep=';', encoding='latin1', dtype=str, nrows=0)
        need(header, usecols, f'{zip_path}:{member}')
        with z.open(member) as f:
            for ch in pd.read_csv(f, sep=';', encoding='latin1', dtype=str, usecols=usecols, chunksize=chunksize):
                ch = ch[(ch.CD_CARGO == '1') & ch.SG_UF.isin(ufs)]
                if len(ch):
                    parts.append(reduce(ch))
    return parts


def _votos(ch):
    v = ch.assign(q=ch.QT_VOTOS.astype(int), n=ch.NR_VOTAVEL.astype(int))
    v['lula'] = np.where(v.n == LULA, v.q, 0)
    v['flavio'] = np.where(v.n == FLAVIO, v.q, 0)
    v['valid'] = np.where(v.n.isin(NONVALID), 0, v.q)
    v['branco'] = np.where(v.n == 95, v.q, 0)
    v['nulo'] = np.where(v.n == 96, v.q, 0)
    return v.groupby(KEY + ['NR_TURNO'], as_index=False)[VOTOS_COLS].sum()


def _detalhe(ch):
    t = ch.assign(apt=ch.QT_APTOS.astype(int), comp=ch.QT_COMPARECIMENTO.astype(int),
                  abst=ch.QT_ABSTENCOES.astype(int),
                  nominais=ch.QT_VOTOS_NOMINAIS.astype(int), brancos_d=ch.QT_VOTOS_BRANCOS.astype(int),
                  nulos_d=ch.QT_VOTOS_NULOS.astype(int))
    return t.groupby(KEY + ['NR_TURNO'], as_index=False)[DETALHE_COLS].sum()


def _soma(parts, cols):
    return pd.concat(parts).groupby(KEY + ['NR_TURNO'], as_index=False)[cols].sum() if parts else None


def load_sections(d, year, ufs, chunksize=1_000_000):
    """Uma linha por seção e turno (formato longo), com votação e, se houver, detalhe."""
    d = pathlib.Path(d)
    vs = d / f'votacao_secao_{year}_BR.zip'
    ds = d / f'detalhe_votacao_secao_{year}.zip'
    if not vs.exists():
        sys.exit(f'{vs} ausente; rode o download')
    g = _soma(read_member(vs, f'votacao_secao_{year}_BR.csv',
                          KEY + ['NR_TURNO', 'CD_CARGO', 'NR_VOTAVEL', 'QT_VOTOS'], ufs, _votos, chunksize),
              VOTOS_COLS)
    if g is None:
        sys.exit(f'nenhum dado de presidente carregado para {year} nas UFs pedidas')
    if ds.exists():
        t = _soma(read_member(ds, f'detalhe_votacao_secao_{year}_BR.csv',
                              KEY + ['NR_TURNO', 'CD_CARGO', 'QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'QT_VOTOS_NOMINAIS',
                                     'QT_VOTOS_BRANCOS', 'QT_VOTOS_NULOS'], ufs, _detalhe, chunksize),
                  DETALHE_COLS)
        sem = int((~g.set_index(KEY + ['NR_TURNO']).index.isin(t.set_index(KEY + ['NR_TURNO']).index)).sum())
        if sem:
            sys.exit(f'{year}: {sem:,} seção(ões) de votação sem linha no detalhe; comparecimento seria subcontado')
        # seções não instaladas só existem no detalhe (sem votos): entram com votos zero para fechar os totais
        g = g.merge(t, on=KEY + ['NR_TURNO'], how='outer')
        g[VOTOS_COLS] = g[VOTOS_COLS].fillna(0).astype(int)
    else:
        print(f'[aviso] {year}: detalhe_votacao_secao ausente – análise de comparecimento desligada')
        for c in DETALHE_COLS:
            g[c] = np.nan
    return g


def load_year(d, year, ufs, chunksize=1_000_000):
    """Retorna DataFrame por seção com as colunas de load_sections sufixadas por turno (1, 2)."""
    df = load_sections(d, year, ufs, chunksize)
    print(f'{year}: turnos presentes nos arquivos: {sorted(df.NR_TURNO.unique())}')
    if not {'1', '2'} <= set(df.NR_TURNO.unique()):
        sys.exit(f'{year}: faltam turnos (precisa de 1 e 2). Se o 2º turno ainda não foi publicado, aguarde.')
    w = {}
    for turno in ('1', '2'):
        x = df[df.NR_TURNO == turno].drop(columns='NR_TURNO').set_index(KEY)
        w[turno] = x.add_suffix(turno)
    # inner join descarta seções que existem só em um turno; quantificar isso é tarefa da Fase 2
    wide = w['1'].join(w['2'], how='inner').reset_index()
    print(f'{year}: {len(wide):,} seções presentes nos dois turnos')
    return wide
