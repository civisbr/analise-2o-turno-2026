import hashlib
import pathlib
import sys

import polars as pl

from .balance import muni_table
from .load import ALL, KEY, MIN_SECOES_PUBLICAS, load_sections, pivota
from .prereg import exige_prereg
from .verify import fechamento, totais

CHECADOS = {'lula': 'lula', 'flavio': 'flavio', 'valid': 'validos', 'apt': 'aptos', 'comp': 'comparecimento'}
SOMAS_DESCARTES = ['secoes', 'aptos', 'comparecimento', 'validos', 'lula', 'flavio']


def conteudo_sha256(df):
    """Hash do conteúdo, não do arquivo: Parquet embute a versão da biblioteca nos metadados."""
    return hashlib.sha256(df.write_csv().encode()).hexdigest()


def descartes(g):
    """Seções (com votos ou comparecimento) presentes em só um dos turnos: ficam fora da tabela municipal."""
    v = g.filter((pl.col('comp') > 0) | (pl.col('valid') > 0))
    chaves = v.group_by(KEY).agg(n_turnos=pl.col('NR_TURNO').n_unique())
    d = v.join(chaves, on=KEY).filter(pl.col('n_turnos') == 1)
    return (d.group_by(['SG_UF', 'NR_TURNO'])
             .agg(secoes=pl.len(), aptos=pl.col('apt').sum(), comparecimento=pl.col('comp').sum(),
                  validos=pl.col('valid').sum(), lula=pl.col('lula').sum(), flavio=pl.col('flavio').sum())
             .sort(['SG_UF', 'NR_TURNO']))


def agrega_descartes(d):
    """Publicado só por turno, sem UF: linhas por UF teriam 1 ou poucas seções."""
    return d.group_by('NR_TURNO').agg(pl.col(SOMAS_DESCARTES).sum()).sort('NR_TURNO')


def agrega_pequenos(m, k=MIN_SECOES_PUBLICAS):
    """Tabela municipal publicável. Município com menos de k seções equivale ao resultado da seção e vai para
    '<UF>-OUTROS'; se o grupo ficar com menos de k seções ou com um só município, absorve o menor município
    publicado da UF (supressão complementar), senão o município seria identificável pelo complemento. O exterior
    (ZZ) é uma linha só. A soma total é preservada."""
    nums = [c for c in m.columns if c not in ('SG_UF', 'mun')]
    linhas = []

    def soma(g, nome, uf):
        return {**{c: int(g[c].sum()) for c in nums}, 'SG_UF': uf, 'mun': nome, 'municipios_agregados': g.height}

    for (uf,), g in sorted(m.partition_by('SG_UF', as_dict=True).items()):
        if uf == 'ZZ':
            linhas.append(soma(g, 'ZZ-EXTERIOR', uf)); continue
        g = g.sort(['secoes', 'mun'])
        peq, grandes = g.filter(pl.col('secoes') < k), g.filter(pl.col('secoes') >= k)
        if peq.height:
            while (peq['secoes'].sum() < k or peq.height < 2) and grandes.height:
                peq = pl.concat([peq, grandes.head(1)]); grandes = grandes.slice(1)
            linhas.append(soma(peq, f'{uf}-OUTROS', uf))
        linhas += [{**r, 'municipios_agregados': 0} for r in grandes.iter_rows(named=True)]
    r = pl.DataFrame(linhas, infer_schema_length=None).select(['SG_UF', 'mun'] + nums + ['municipios_agregados'])
    return r.sort('mun')


def build(dir, out, private, year, exige=True):
    year = str(year)
    if exige and year == '2026':
        exige_prereg()   # tabela municipal de 2026 só depois do pré-registro congelado
    g = load_sections(dir, year, ALL + ['ZZ'])
    if g['apt'].null_count():
        sys.exit(f'{year}: sem detalhe_votacao_secao; build não é possível')
    bad = fechamento(dir, year, g, exige_munzona=True)
    g = g.sort(KEY + ['NR_TURNO'])
    nac, _ = totais(g)
    nac = {row['NR_TURNO']: row for row in nac.iter_rows(named=True)}
    conteudo = {f'secoes_{year}': conteudo_sha256(g)}
    tabelas = {}
    if {'1', '2'} <= set(g['NR_TURNO'].to_list()):
        ativas = g.filter((pl.col('comp') > 0) | (pl.col('valid') > 0))
        w = pivota(ativas)
        m = muni_table(w).sort('mun')   # 'secoes' = seções ativas nos dois turnos
        d = descartes(g)
        # Partição: municípios + descartes + aptos de seções não instaladas = total nacional, por turno.
        # Pega erro de pivot, merge ou chave duplicada; não é segunda fonte (a independente é o município-zona).
        nao_inst = {t: a for t, a in g.filter((pl.col('comp') == 0) & (pl.col('valid') == 0)).group_by('NR_TURNO').agg(pl.col('apt').sum()).iter_rows()}
        for t in ('1', '2'):
            for c, dc in CHECADOS.items():
                desc = int(d.filter(pl.col('NR_TURNO') == t)[dc].sum()) + (int(nao_inst.get(t, 0)) if c == 'apt' else 0)
                if int(m[f'{c}{t}'].sum()) + desc != int(nac[t][c]):
                    sys.exit(f'{year}: município + descartes != total nacional ({c}, turno {t}); nada foi gravado')
        mp, dp = agrega_pequenos(m), agrega_descartes(d)
        for c in m.columns:
            if c[-1:] in '12' and c not in ('SG_UF', 'mun') and c in mp.columns:
                assert int(mp[c].sum()) == int(m[c].sum()), c   # agregação preserva as somas
        tabelas = {f'municipios_{year}.csv': mp, f'descartes_{year}.csv': dp}
        conteudo[f'municipios_{year}'] = conteudo_sha256(mp)
        print(f'\nDescartes (seção presente em só um turno): {int(d["secoes"].sum()):,} seções, '
              f'{int(d["validos"].sum()):,} votos válidos')
    else:
        print(f'\n[aviso] {year}: só um turno nos dados; tabela municipal e descartes não gerados')
    # Só aqui, depois de todos os testes: nada é gravado se algum falhar.
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    private = pathlib.Path(private); private.mkdir(parents=True, exist_ok=True)
    g.write_parquet(private / f'secoes_{year}.parquet')
    arquivos = []
    for nome, df in tabelas.items():
        df.write_csv(out / nome); arquivos.append(out / nome)
    return {'fechamento': bad, 'arquivos': arquivos, 'conteudo_sha256': conteudo}
