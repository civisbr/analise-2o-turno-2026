"""Leitura dos arquivos de seção do TSE (layout verificado em 26/10/2026, iguais em 2022 e 2026).

  votacao_secao/votacao_secao_<ano>_BR.zip   membro votacao_secao_<ano>_BR.csv: todas as UFs, só cargo
        Presidente (CD_CARGO 1); SG_UF é a UF real da seção. Os zips por UF só trazem cargos estaduais.
        NR_TURNO, CD_CARGO, SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO, NR_VOTAVEL, QT_VOTOS
  detalhe_votacao_secao/detalhe_votacao_secao_<ano>.zip   arquivo nacional único; membro
        detalhe_votacao_secao_<ano>_BR.csv (Presidente): QT_APTOS, QT_COMPARECIMENTO
  CSV com ';', aspas, latin1. NR_VOTAVEL: 13 = Lula, 22 = Jair Bolsonaro (2022) ou Flávio Bolsonaro (2026), 95 = branco, 96 = nulo.
  detalhe_votacao_munzona/detalhe_votacao_munzona_<ano>.zip: agregação do TSE por município-zona (munzona.py).
O exterior (ZZ) fica fora de ALL; verify e build o somam à parte.
"""
import io
import pathlib
import sys
import zipfile

import polars as pl

NE = ['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE']
ALL = sorted(NE + ['AC', 'AM', 'AP', 'DF', 'ES', 'GO', 'MG', 'MS', 'MT', 'PA', 'PR', 'RJ', 'RO', 'RR', 'RS',
                   'SC', 'SP', 'TO'])

KEY = ['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']
LULA, FLAVIO = 13, 22
NONVALID = (95, 96)
MIN_SECOES_PUBLICAS = 10   # município ou grupo com menos seções não é publicado isolado (regra 7)
MAX_MEMBRO_BYTES = 5 * 1024 ** 3   # teto de tamanho descompactado (zip bomb); o maior arquivo real tem ~1 GB
MAX_LINHA = 1024 ** 2              # teto por linha: as reais têm ~150 bytes; linha sem quebra seria carregada inteira
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
    presentes = list(getattr(df, 'columns', df))
    miss = [c for c in cols if c not in presentes]
    if miss:
        sys.exit(f'{name}: colunas ausentes {miss}. Colunas presentes: {presentes}')


def _csv(dados, usecols=None):
    """CSV do TSE (';', aspas). utf8-lossy: o arquivo é latin1, mas as colunas lidas são ASCII e os bytes altos
    das demais nunca formam ';', aspas ou quebra de linha em UTF-8, então o parse não muda."""
    return pl.read_csv(io.BytesIO(dados), separator=';', encoding='utf8-lossy', infer_schema=False, columns=usecols)


def _linhas(f, n, onde):
    """Até n linhas do membro, recusando linha maior que MAX_LINHA (arquivo sem quebras de linha)."""
    out = []
    for _ in range(n):
        linha = f.readline(MAX_LINHA + 1)
        if not linha:
            break
        if len(linha) > MAX_LINHA:
            sys.exit(f'{onde}: linha com mais de {MAX_LINHA:,} bytes; arquivo inválido')
        out.append(linha)
    return out


def _exige_preenchido(ch, cols, onde):
    """Campo vazio viraria null e sumiria da soma (o astype(int) do pandas abortava): arquivo truncado ou adulterado."""
    n = ch.select(pl.col(cols).null_count()).sum_horizontal().item()
    if n:
        sys.exit(f'{onde}: {n:,} campo(s) vazio(s) nas colunas lidas; arquivo truncado ou adulterado')


def read_member(zip_path, member, usecols, ufs, reduce, chunksize=1_000_000):
    """Lê o CSV nacional (>1 GB) em blocos de linhas, filtra Presidente das UFs pedidas e reduz cada bloco
    com `reduce` antes de acumular, para não segurar milhões de linhas de texto em memória."""
    parts = []
    with zipfile.ZipFile(zip_path) as z:
        if member not in z.namelist():
            sys.exit(f'{zip_path}: membro {member} ausente. Membros: {z.namelist()}')
        if z.getinfo(member).file_size > MAX_MEMBRO_BYTES:
            sys.exit(f'{zip_path}: membro {member} descompactado passa de {MAX_MEMBRO_BYTES:,} bytes')
        onde = f'{zip_path}:{member}'
        with z.open(member) as f:
            cab = _linhas(f, 1, onde)[0]
            need(_csv(cab).columns, usecols, onde)
            while True:
                linhas = _linhas(f, chunksize, onde)
                if not linhas:
                    break
                bloco = b''.join(linhas)
                if bloco.count(b'"') % 2:   # campo entre aspas com quebra de linha partido entre blocos
                    sys.exit(f'{onde}: aspas abertas no fim de um bloco de linhas; arquivo fora do layout esperado')
                ch = _csv(cab + bloco, usecols)
                _exige_preenchido(ch, usecols, onde)
                ch = ch.filter((pl.col('CD_CARGO') == '1') & pl.col('SG_UF').is_in(ufs))
                if ch.height:
                    parts.append(reduce(ch))
    return parts


def _votos(ch):
    q = pl.col('QT_VOTOS').cast(pl.Int64); n = pl.col('NR_VOTAVEL').cast(pl.Int64)
    v = ch.with_columns(
        lula=pl.when(n == LULA).then(q).otherwise(0), flavio=pl.when(n == FLAVIO).then(q).otherwise(0),
        valid=pl.when(n.is_in(NONVALID)).then(0).otherwise(q),
        branco=pl.when(n == 95).then(q).otherwise(0), nulo=pl.when(n == 96).then(q).otherwise(0))
    return v.group_by(KEY + ['NR_TURNO']).agg(pl.col(VOTOS_COLS).sum())


def _detalhe(ch):
    t = ch.with_columns(apt=pl.col('QT_APTOS').cast(pl.Int64), comp=pl.col('QT_COMPARECIMENTO').cast(pl.Int64),
                        abst=pl.col('QT_ABSTENCOES').cast(pl.Int64), nominais=pl.col('QT_VOTOS_NOMINAIS').cast(pl.Int64),
                        brancos_d=pl.col('QT_VOTOS_BRANCOS').cast(pl.Int64), nulos_d=pl.col('QT_VOTOS_NULOS').cast(pl.Int64))
    return t.group_by(KEY + ['NR_TURNO']).agg(pl.col(DETALHE_COLS).sum())


def _soma(parts, cols):
    if not parts:
        return None
    return pl.concat(parts).group_by(KEY + ['NR_TURNO']).agg(pl.col(cols).sum()).sort(KEY + ['NR_TURNO'])


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
    chave = KEY + ['NR_TURNO']
    if ds.exists():
        t = _soma(read_member(ds, f'detalhe_votacao_secao_{year}_BR.csv',
                              KEY + ['NR_TURNO', 'CD_CARGO', 'QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'QT_VOTOS_NOMINAIS',
                                     'QT_VOTOS_BRANCOS', 'QT_VOTOS_NULOS'], ufs, _detalhe, chunksize),
                  DETALHE_COLS)
        sem = g.join(t.select(chave), on=chave, how='anti').height
        if sem:
            sys.exit(f'{year}: {sem:,} seção(ões) de votação sem linha no detalhe; comparecimento seria subcontado')
        # seções não instaladas só existem no detalhe (sem votos): entram com votos zero para fechar os totais
        g = g.with_columns(_com_votacao=pl.lit(True)).join(t, on=chave, how='full', coalesce=True).sort(chave)
        so_detalhe = pl.col('_com_votacao').is_null()
        com_voto = g.filter(so_detalhe & ((pl.col('comp') > 0) | (pl.col('nominais') + pl.col('brancos_d') + pl.col('nulos_d') > 0))).height
        if com_voto:
            sys.exit(f'{year}: {com_voto:,} seção(ões) com votos no detalhe e sem linha na votação; '
                     'arquivos inconsistentes ou truncados')
        g = g.drop('_com_votacao').with_columns(pl.col(VOTOS_COLS).fill_null(0))
    else:
        print(f'[aviso] {year}: detalhe_votacao_secao ausente – análise de comparecimento desligada')
        g = g.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in DETALHE_COLS])
    return g


def pivota(g):
    """Formato longo (uma linha por seção e turno) para largo: colunas sufixadas por turno, só seções nos dois."""
    w = []
    for t in ('1', '2'):
        x = g.filter(pl.col('NR_TURNO') == t).drop('NR_TURNO')
        w.append(x.rename({c: c + t for c in x.columns if c not in KEY}))
    return w[0].join(w[1], on=KEY, how='inner').sort(KEY)


def load_year(d, year, ufs, chunksize=1_000_000):
    """Retorna DataFrame por seção com as colunas de load_sections sufixadas por turno (1, 2)."""
    df = load_sections(d, year, ufs, chunksize)
    # seção não instalada (sem comparecimento nem votos) fica fora das análises; só os totais a contam
    vazias = ((pl.col('comp') == 0) & (pl.col('valid') == 0)).fill_null(False)
    n_vazias = df.filter(vazias).height
    if n_vazias:
        print(f'{year}: {n_vazias:,} seção(ões) sem comparecimento e sem votos descartadas')
        df = df.filter(~vazias)
    turnos = sorted(df['NR_TURNO'].unique().to_list())
    print(f'{year}: turnos presentes nos arquivos: {turnos}')
    if not {'1', '2'} <= set(turnos):
        sys.exit(f'{year}: faltam turnos (precisa de 1 e 2). Se o 2º turno ainda não foi publicado, aguarde.')
    # inner join descarta seções que existem só em um turno; quantificar isso é tarefa da Fase 2
    wide = pivota(df)
    print(f'{year}: {wide.height:,} seções presentes nos dois turnos')
    return wide
