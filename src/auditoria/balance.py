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

from .load import MIN_SECOES_PUBLICAS, load_year
from .robust import BOOT_SEED, boot_ci, mad_sigma, wls


def muni_table(wide):
    d = wide.copy()
    d['mun'] = d.SG_UF + '-' + d.CD_MUNICIPIO
    cols = [c for c in d.columns if c[:-1] in ('lula', 'flavio', 'valid', 'apt', 'comp') and c[-1] in '12']
    g = d.groupby(['SG_UF', 'mun'])
    t = g[cols].sum(min_count=1)
    t['secoes'] = g.size()
    return t.reset_index()


def identity_gap(m):
    """ΔLula + ΔFlávio − (terceira via + Δválidos). Zero em qualquer eleição com dados íntegros."""
    return m.dL.sum() + m.dF.sum() - m.pool.sum() - m.dvalid.sum()


def add_flows(m):
    m['pool'] = m.valid1 - m.lula1 - m.flavio1
    m['dvalid'] = m.valid2 - m.valid1
    m['dL'] = m.lula2 - m.lula1; m['dF'] = m.flavio2 - m.flavio1
    return m


def balance(wide, label, out, min_valid=200, boot=300):
    m = add_flows(muni_table(wide))
    bad = m[m.dL + m.dF - m.pool - m.dvalid != 0]
    if len(bad):
        sys.exit(f'{label}: identidade contábil não fecha em {len(bad)} município(s) (ex.: {bad.mun.iloc[0]}); '
                 'dados inconsistentes, pipeline parado')
    m = m[(m.valid1 >= min_valid) & (m.valid2 >= min_valid)].reset_index(drop=True)
    v1 = m.valid1.values.astype(float)
    have = bool(m.comp1.notna().all() and m.comp2.notna().all())
    if have:
        m['dturn'] = m.comp2 - m.comp1
        m['dbn'] = -((m.comp2 - m.valid2) - (m.comp1 - m.valid1))     # queda de brancos+nulos (>0 = caiu)
    tot = {k: m[k].sum() for k in ('pool', 'dvalid', 'dL', 'dF')}
    print(f'\n===== {label}: {len(m):,} municípios (válidos 1T ≥ {min_valid}) =====')
    print(f'terceira via 1T: {tot["pool"]:,.0f} | Δválidos: {tot["dvalid"]:+,.0f} | ΔLula: {tot["dL"]:+,.0f} | '
          f'ΔFlávio/Bolsonaro: {tot["dF"]:+,.0f}')
    print(f'ΔLula/(ΔLula+ΔFlávio) = {tot["dL"]/(tot["dL"]+tot["dF"]):.1%}   '
          f'identidade ΔL+ΔF − (terceira via + Δválidos) = {identity_gap(m):+,.0f} (deve ser 0)')
    print('\nPor UF:  terceira via   Δválidos       ΔLula     ΔFlávio   %Lula do ganho')
    for uf, g in m.groupby('SG_UF'):
        dl, df_ = g.dL.sum(), g.dF.sum()
        print(f'  {uf}  {g.pool.sum():11,.0f} {g.dvalid.sum():+11,.0f} {dl:+11,.0f} {df_:+11,.0f}   {dl/(dl+df_):6.1%}')
    y = (m.dL / v1).values
    cols = {'parcela de Lula por voto da terceira via (a)': (m.pool / v1).values}
    models = {'A': {**cols, 'parcela de Lula por voto válido novo (b)': (m.dvalid / v1).values}}
    if have:
        models['B'] = {**cols, 'parcela de Lula por novo comparecimento (b1)': (m.dturn / v1).values,
                       'parcela de Lula por queda de brancos+nulos (b2)': (m.dbn / v1).values}
    g = m.SG_UF.values if m.SG_UF.nunique() > 1 else None
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
    rs = r * np.sqrt(v1); mad = mad_sigma(rs)
    m['resid_votos'] = r * v1; m['z_resid'] = rs / mad
    top = m.sort_values('z_resid', ascending=False).head(15)
    print(f'\nMunicípios com MAIS votos de Lula do que o modelo {best} explica (top 15):')
    print(top[['mun', 'valid1', 'pool', 'dvalid', 'dL', 'dF', 'resid_votos', 'z_resid']].round(1).to_string(index=False))
    neg = m[m.dF < 0]
    print(f'\nMunicípios onde o 2º colocado perdeu votos absolutos: {len(neg):,} de {len(m):,} '
          f'({len(neg)/len(m):.1%}; {neg.valid1.sum()/m.valid1.sum():.1%} dos válidos)')
    if have:
        unexpl = neg[neg.dturn >= 0].sort_values('dF')
        print(f'   com comparecimento em QUEDA (explicável por abstenção): {int((neg.dturn < 0).sum()):,}')
        print(f'   com comparecimento estável/em ALTA (precisa de outra explicação): {len(unexpl):,}')
        if len(unexpl):
            print(unexpl[['mun', 'valid1', 'dturn', 'dF', 'dL']].head(15).round(0).to_string(index=False))
    # Regra 7: município com poucas seções não é publicado isolado.
    m[m.secoes >= MIN_SECOES_PUBLICAS].to_csv(pathlib.Path(out) / f'balanco_municipios_{label.split()[0]}.csv', index=False)
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
