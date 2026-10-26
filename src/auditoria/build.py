import hashlib
import pathlib
import sys

import pandas as pd

from .balance import muni_table
from .load import ALL, KEY, MIN_SECOES_PUBLICAS, load_sections
from .prereg import exige_prereg
from .verify import fechamento, totais

CHECADOS = {'lula': 'lula', 'flavio': 'flavio', 'valid': 'validos', 'apt': 'aptos', 'comp': 'comparecimento'}


def conteudo_sha256(df):
    """Hash do conteúdo, não do arquivo: Parquet embute a versão da biblioteca nos metadados."""
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()


def pivota(g):
    w = {}
    for t in ('1', '2'):
        w[t] = g[g.NR_TURNO == t].drop(columns='NR_TURNO').set_index(KEY).add_suffix(t)
    return w['1'].join(w['2'], how='inner').reset_index()


def descartes(g):
    """Seções (com votos ou comparecimento) presentes em só um dos turnos: ficam fora da tabela municipal."""
    v = g[(g.comp > 0) | (g.valid > 0)]
    chaves = v.groupby(KEY).NR_TURNO.nunique().rename('n_turnos').reset_index()
    d = v.merge(chaves, on=KEY)
    d = d[d.n_turnos == 1]
    return (d.groupby(['SG_UF', 'NR_TURNO'])
             .agg(secoes=('apt', 'size'), aptos=('apt', 'sum'), comparecimento=('comp', 'sum'),
                  validos=('valid', 'sum'), lula=('lula', 'sum'), flavio=('flavio', 'sum'))
             .reset_index())


def agrega_descartes(d):
    """Publicado só por turno, sem UF: linhas por UF teriam 1 ou poucas seções."""
    return d.groupby('NR_TURNO', as_index=False)[['secoes', 'aptos', 'comparecimento', 'validos', 'lula', 'flavio']].sum()


def agrega_pequenos(m, k=MIN_SECOES_PUBLICAS):
    """Tabela municipal publicável. Município com menos de k seções equivale ao resultado da seção e vai para
    '<UF>-OUTROS'; se o grupo ficar com menos de k seções ou com um só município, absorve o menor município
    publicado da UF (supressão complementar), senão o município seria identificável pelo complemento. O exterior
    (ZZ) é uma linha só. A soma total é preservada."""
    nums = [c for c in m.columns if c not in ('SG_UF', 'mun')]
    linhas = []

    def soma(g, nome, uf):
        return {**{c: int(g[c].sum()) for c in nums}, 'SG_UF': uf, 'mun': nome, 'municipios_agregados': len(g)}

    for uf, g in m.groupby('SG_UF'):
        if uf == 'ZZ':
            linhas.append(soma(g, 'ZZ-EXTERIOR', uf)); continue
        g = g.sort_values(['secoes', 'mun'])
        peq, grandes = g[g.secoes < k], g[g.secoes >= k]
        if len(peq):
            while (peq.secoes.sum() < k or len(peq) < 2) and len(grandes):
                peq = pd.concat([peq, grandes.iloc[[0]]]); grandes = grandes.iloc[1:]
            linhas.append(soma(peq, f'{uf}-OUTROS', uf))
        linhas += [{**r, 'municipios_agregados': 0} for r in grandes.to_dict('records')]
    r = pd.DataFrame(linhas)[['SG_UF', 'mun'] + nums + ['municipios_agregados']]
    return r.sort_values('mun').reset_index(drop=True)


def build(dir, out, private, year, exige=True):
    year = str(year)
    if exige and year == '2026':
        exige_prereg()   # tabela municipal de 2026 só depois do pré-registro congelado
    g = load_sections(dir, year, ALL + ['ZZ'])
    if g.apt.isna().any():
        sys.exit(f'{year}: sem detalhe_votacao_secao; build não é possível')
    bad = fechamento(dir, year, g, exige_munzona=True)
    g = g.sort_values(KEY + ['NR_TURNO']).reset_index(drop=True)
    nac, _ = totais(g)
    conteudo = {f'secoes_{year}': conteudo_sha256(g)}
    tabelas = {}
    if {'1', '2'} <= set(g.NR_TURNO):
        ativas = g[(g.comp > 0) | (g.valid > 0)]
        w = pivota(ativas)
        m = muni_table(w).sort_values('mun').reset_index(drop=True)
        m['secoes'] = m.mun.map((w.SG_UF + '-' + w.CD_MUNICIPIO).value_counts())   # seções ativas nos dois turnos
        d = descartes(g)
        # Partição: municípios + descartes + aptos de seções não instaladas = total nacional, por turno.
        # Pega erro de pivot, merge ou chave duplicada; não é segunda fonte (a independente é o município-zona).
        nao_inst = g[(g.comp == 0) & (g.valid == 0)].groupby('NR_TURNO').apt.sum()
        for t in ('1', '2'):
            for c, dc in CHECADOS.items():
                desc = int(d[d.NR_TURNO == t][dc].sum()) + (int(nao_inst.get(t, 0)) if c == 'apt' else 0)
                if int(m[f'{c}{t}'].sum()) + desc != int(nac.loc[t, c]):
                    sys.exit(f'{year}: município + descartes != total nacional ({c}, turno {t}); nada foi gravado')
        mp, dp = agrega_pequenos(m), agrega_descartes(d)
        for c in m.columns:
            if c[-1:] in '12' and c not in ('SG_UF', 'mun') and c in mp.columns:
                assert int(mp[c].sum()) == int(m[c].sum()), c   # agregação preserva as somas
        tabelas = {f'municipios_{year}.csv': mp, f'descartes_{year}.csv': dp}
        conteudo[f'municipios_{year}'] = conteudo_sha256(mp)
        print(f'\nDescartes (seção presente em só um turno): {int(d.secoes.sum()):,} seções, '
              f'{int(d.validos.sum()):,} votos válidos')
    else:
        print(f'\n[aviso] {year}: só um turno nos dados; tabela municipal e descartes não gerados')
    # Só aqui, depois de todos os testes: nada é gravado se algum falhar.
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    private = pathlib.Path(private); private.mkdir(parents=True, exist_ok=True)
    g.to_parquet(private / f'secoes_{year}.parquet', index=False)
    arquivos = []
    for nome, df in tabelas.items():
        df.to_csv(out / nome, index=False); arquivos.append(out / nome)
    return {'fechamento': bad, 'arquivos': arquivos, 'conteudo_sha256': conteudo}
