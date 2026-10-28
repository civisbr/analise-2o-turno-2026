"""Balanço de votos entre turnos (município): de onde veio o ganho de Lula?

  ΔLula = a·(terceira via 1T) + b·(Δ votos válidos)                                   [modelo A]
  ΔLula = a·(terceira via 1T) + b1·(Δ comparecimento) + b2·(queda de brancos+nulos)   [modelo B]

Tudo dividido pelos válidos do 1T e ponderado por eles. Como ΔLula+ΔFlávio = terceira via + Δválidos
(identidade exata), os coeficientes de Flávio são 1−a e 1−b.

ATENÇÃO À LEITURA: 'a' NÃO é "a fração da terceira via que votou em Lula". É a parcela, que fica com
Lula, do ganho líquido associado a cada voto da terceira via, mantido fixo o Δ de válidos (se parte da
terceira via se abstém e é substituída por eleitores novos que votam em Lula, isso entra em 'a';
teórico: a = a_real + b·fração_que_saiu). Por isso só é legítimo comparar 'a' e 'b' entre eleições
(2026 × 2022), não com pesquisas de intenção de voto.
Inferência ecológica: mostra associação entre municípios, não o comportamento de eleitores individuais.
"""
import pathlib
import sys

import numpy as np
import polars as pl

from .load import load_year
from .robust import BOOT_SEED, boot_ci, mad_positivo, wls

PREFIXOS = ('lula', 'flavio', 'valid', 'apt', 'comp')


def muni_table(wide):
    d = wide.with_columns(mun=pl.col('SG_UF') + '-' + pl.col('CD_MUNICIPIO'))
    cols = [c for c in d.columns if c[:-1] in PREFIXOS and c[-1] in '12']
    # soma vazia (sem detalhe: comparecimento todo nulo) fica nula, não 0
    somas = [pl.when(pl.col(c).count() > 0).then(pl.col(c).sum()).alias(c) for c in cols]
    return (d.group_by(['SG_UF', 'mun']).agg(somas + [pl.len().cast(pl.Int64).alias('secoes')])
             .sort(['SG_UF', 'mun']))


def identity_gap(m):
    """ΔLula + ΔFlávio − (terceira via + Δválidos). Zero em qualquer eleição com dados íntegros."""
    return m['dL'].sum() + m['dF'].sum() - m['pool'].sum() - m['dvalid'].sum()


def add_flows(m):
    return m.with_columns(pool=pl.col('valid1') - pl.col('lula1') - pl.col('flavio1'),
                          dvalid=pl.col('valid2') - pl.col('valid1'),
                          dL=pl.col('lula2') - pl.col('lula1'), dF=pl.col('flavio2') - pl.col('flavio1'))


def tem_comparecimento(m):
    return m['comp1'].null_count() == 0 and m['comp2'].null_count() == 0


def uf_array(m):
    return m['SG_UF'].to_numpy().astype(str)


def balance(wide, label, out, min_valid=200, boot=300):
    m = add_flows(muni_table(wide))
    bad = m.filter(pl.col('dL') + pl.col('dF') - pl.col('pool') - pl.col('dvalid') != 0)
    if bad.height:
        sys.exit(f'{label}: identidade contábil não fecha em {bad.height} município(s) (ex.: {bad["mun"][0]}); '
                 'dados inconsistentes, pipeline parado')
    m = m.filter((pl.col('valid1') >= min_valid) & (pl.col('valid2') >= min_valid))
    v1 = m['valid1'].to_numpy().astype(float)
    have = tem_comparecimento(m)
    if have:
        m = m.with_columns(dturn=pl.col('comp2') - pl.col('comp1'),
                           dbn=-((pl.col('comp2') - pl.col('valid2')) - (pl.col('comp1') - pl.col('valid1'))))   # queda de brancos+nulos (>0 = caiu)
    tot = {k: m[k].sum() for k in ('pool', 'dvalid', 'dL', 'dF')}
    print(f'\n===== {label}: {m.height:,} municípios (válidos 1T ≥ {min_valid}) =====')
    print(f'terceira via 1T: {tot["pool"]:,.0f} | Δválidos: {tot["dvalid"]:+,.0f} | ΔLula: {tot["dL"]:+,.0f} | '
          f'ΔFlávio/Bolsonaro: {tot["dF"]:+,.0f}')
    print(f'ΔLula/(ΔLula+ΔFlávio) = {tot["dL"]/(tot["dL"]+tot["dF"]):.1%}   '
          f'identidade ΔL+ΔF − (terceira via + Δválidos) = {identity_gap(m):+,.0f} (deve ser 0)')
    print('\nPor UF:  terceira via   Δválidos       ΔLula     ΔFlávio   %Lula do ganho')
    for (uf,), g in sorted(m.partition_by('SG_UF', as_dict=True).items()):
        dl, df_ = g['dL'].sum(), g['dF'].sum()
        print(f'  {uf}  {g["pool"].sum():11,.0f} {g["dvalid"].sum():+11,.0f} {dl:+11,.0f} {df_:+11,.0f}   {dl/(dl+df_):6.1%}')
    y = (m['dL'] / m['valid1']).to_numpy()
    num = lambda e: (e / m['valid1']).to_numpy()
    cols = {'parcela de Lula por voto da terceira via (a)': num(m['pool'])}
    models = {'A': {**cols, 'parcela de Lula por voto válido novo (b)': num(m['dvalid'])}}
    if have:
        models['B'] = {**cols, 'parcela de Lula por novo comparecimento (b1)': num(m['dturn']),
                       'parcela de Lula por queda de brancos+nulos (b2)': num(m['dbn'])}
    g = uf_array(m) if m['SG_UF'].n_unique() > 1 else None
    # Diagnóstico de identificação: sem variação do regressor entre municípios (dentro da UF), o
    # coeficiente não é estimável e o IC explode. dp em pontos percentuais dos válidos do 1T.
    allx = models['B'] if have else models['A']
    print('\nVariação dos regressores entre municípios (dp ponderado, dentro da UF, em pp dos válidos 1T):')
    for nm, x in allx.items():
        xd = x.copy()
        for k in (np.unique(g) if g is not None else [None]):
            mk = (g == k) if k is not None else np.ones(len(x), bool)
            xd[mk] = x[mk] - (v1[mk] / v1[mk].sum()) @ x[mk]
        sd = np.sqrt((v1 * xd ** 2).sum() / v1.sum()) * 100
        print(f'   {nm}: {sd:.2f} pp' + ('   (!) quase constante: coeficiente NÃO identificado' if sd < 0.5 else ''))
    res = {}
    for name, dct in models.items():
        X = np.column_stack(list(dct.values()))
        for fe in ([True, False] if g is not None else [False]):
            gg = g if fe else None
            beta = wls(y, X, v1, gg); lo, hi = boot_ci(y, X, v1, gg, boot, BOOT_SEED)
            tag = 'com efeito fixo de UF' if fe else 'sem efeito fixo'
            print(f'\n  Modelo {name} ({tag}):')
            for k, nm in enumerate(dct):
                print(f'     {nm:34s} {beta[k]:+.3f}   IC95% bootstrap-município [{lo[k]:+.3f}, {hi[k]:+.3f}]')
            res[(name, fe)] = beta
    # resíduos do melhor modelo (B se houver comparecimento), com efeito fixo de UF
    best = 'B' if have else 'A'
    X = np.column_stack(list(models[best].values())); gg = g
    beta = wls(y, X, v1, gg); r = y - X @ beta
    if gg is not None:
        for k in np.unique(gg):
            mk = gg == k; r[mk] -= (v1[mk] / v1[mk].sum()) @ r[mk]
    else:
        r -= (v1 / v1.sum()) @ r
    rs = r * np.sqrt(v1); mad = mad_positivo(rs, f'{label}: resíduos do balanço')
    m = m.with_columns(resid_votos=pl.Series(r * v1), z_resid=pl.Series(rs / mad))
    top = m.sort('z_resid', descending=True).head(15)
    print(f'\nMunicípios com MAIS votos de Lula do que o modelo {best} explica (top 15):')
    with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_hide_dataframe_shape=True):
        print(top.select(['mun', 'valid1', 'pool', 'dvalid', 'dL', 'dF', 'resid_votos', 'z_resid']).with_columns(pl.col(pl.Float64).round(1)))
    neg = m.filter(pl.col('dF') < 0)
    print(f'\nMunicípios onde o 2º colocado perdeu votos absolutos: {neg.height:,} de {m.height:,} '
          f'({neg.height/m.height:.1%}; {neg["valid1"].sum()/m["valid1"].sum():.1%} dos válidos)')
    if have:
        unexpl = neg.filter(pl.col('dturn') >= 0).sort('dF')
        print(f'   com comparecimento em QUEDA (explicável por abstenção): {neg.filter(pl.col("dturn") < 0).height:,}')
        print(f'   com comparecimento estável/em ALTA (precisa de outra explicação): {unexpl.height:,}')
        if unexpl.height:
            with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_hide_dataframe_shape=True):
                print(unexpl.select(['mun', 'valid1', 'dturn', 'dF', 'dL']).head(15))
    # Regra 7: município com poucas seções vai para '<UF>-OUTROS', com supressão complementar (como no build).
    ints = ['secoes', 'valid1', 'valid2', 'lula1', 'lula2', 'flavio1', 'flavio2', 'pool', 'dvalid', 'dL', 'dF'] + \
        (['comp1', 'comp2', 'dturn', 'dbn'] if have else [])
    from .build import agrega_pequenos   # build importa muni_table daqui
    pub = agrega_pequenos(m.select(['SG_UF', 'mun'] + ints))
    pub = pub.join(m.select(['mun', 'resid_votos', 'z_resid']), on='mun', how='left', maintain_order='left')
    agregado = pl.col('municipios_agregados') > 0
    pub = pub.with_columns([pl.when(agregado).then(None).otherwise(pl.col(c)).alias(c) for c in ('resid_votos', 'z_resid')])
    pub.write_csv(pathlib.Path(out) / f'balanco_municipios_{label.split()[0]}.csv')
    return res


def balanco(dir, out, year, control_year, ufs, min_valid=200, boot=300):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    r26 = balance(load_year(dir, year, ufs), f'{year} (principal)', out, min_valid, boot)
    if control_year:
        rc = balance(load_year(dir, control_year, ufs), f'{control_year} (controle)', out, min_valid, boot)
        for key in r26:
            if key in rc:
                print(f'\nModelo {key[0]} {"c/ FE" if key[1] else "s/ FE"}: coeficientes {year} {np.round(r26[key],3)} '
                      f'vs {control_year} {np.round(rc[key],3)}')
    print('\nLeitura: compare a e b de 2026 com os de 2022 (mesmo modelo, mesmas UFs). 1−a e 1−b são as parcelas de '
          'Flávio/Bolsonaro. Diferença grande e estável entre UFs indica padrão nacional (mobilização, troca de '
          'lado); diferença concentrada em poucos municípios aparece na lista de resíduos. Nada aqui é prova de '
          'irregularidade: é associação entre municípios.')
