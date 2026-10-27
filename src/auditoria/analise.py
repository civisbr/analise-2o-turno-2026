"""Q1–Q5 do pré-registro como números estruturados (resultados.json), sem texto interpretativo.

A página lê só este arquivo (regra 5). Município publicado = pelo menos MIN_SECOES_PUBLICAS seções
(regra 7); contagens agregadas incluem todos os elegíveis, listas nominais só os publicáveis.
"""
import json
import math
import pathlib

import numpy as np
import pandas as pd

from .balance import add_flows, identity_gap, muni_table
from .load import MIN_SECOES_PUBLICAS, NE, load_year
from .robust import BOOT_SEED, boot_draws, mad_sigma, wls
from .swing import swing_table

Z_ATIPICO = 4.0
Q_FDR = 0.05
MIN_DP_PP = 0.5          # abaixo disso o coeficiente não é identificado (pré-registro, limiares)
MODELOS = ('A', 'B', 'C')


def prepara(wide, min_valid):
    """Tabela municipal elegível para Q2–Q4. Exterior (ZZ) fica de fora; Q1 usa tabela própria."""
    m = add_flows(muni_table(wide[wide.SG_UF != 'ZZ']))
    m = m[(m.valid1 >= min_valid) & (m.valid2 >= min_valid)].reset_index(drop=True)
    m['tem_comp'] = m.comp1.notna() & m.comp2.notna()
    m['dturn'] = m.comp2 - m.comp1
    m['dbn'] = -((m.comp2 - m.valid2) - (m.comp1 - m.valid1))      # queda de brancos+nulos (>0 = caiu)
    return m


def regressores(m, modelo):
    v1 = m.valid1.values.astype(float)
    c = {'alpha': m.pool / v1}
    if modelo == 'A':
        c['beta'] = m.dvalid / v1
    else:
        c['beta1'] = m.dturn / v1; c['beta2'] = m.dbn / v1
    if modelo == 'C':
        lv = np.log(v1); c['log_tamanho'] = lv - np.average(lv, weights=v1)
    return list(c), np.column_stack([np.asarray(x, float) for x in c.values()])


def dp_pp(x, v1, g):
    """dp ponderado do regressor dentro da UF, em pp dos válidos do 1º turno."""
    xd = x.copy()
    for k in (np.unique(g) if g is not None else [None]):
        mk = (g == k) if k is not None else np.ones(len(x), bool)
        xd[mk] = x[mk] - (v1[mk] / v1[mk].sum()) @ x[mk]
    return float(np.sqrt((v1 * xd ** 2).sum() / v1.sum()) * 100)


def ajusta(m, modelo, fe, excluir=None):
    """Retorna nomes, coeficientes e a máscara usada. excluir = máscara de linhas fora (refit robusto)."""
    nomes, X = regressores(m, modelo)
    y = (m.dL / m.valid1).values; v1 = m.valid1.values.astype(float)
    g = m.SG_UF.values if fe and m.SG_UF.nunique() > 1 else None
    ok = np.ones(len(m), bool) if excluir is None else ~excluir
    return nomes, wls(y[ok], X[ok], v1[ok], None if g is None else g[ok]), ok, (y, X, v1, g)


def z_residuos(m, fe=True, excluir=None):
    """z robusto (MAD) dos resíduos do modelo B, com efeito fixo de UF no ajuste e na centralização."""
    nomes, beta, ok, (y, X, v1, g) = ajusta(m, 'B', fe, excluir)
    r = y - X @ beta; w = v1 * ok
    if g is not None:
        for k in np.unique(g):
            mk = g == k
            if w[mk].sum() > 0:
                r[mk] -= (w[mk] / w[mk].sum()) @ r[mk]
    else:
        r -= (w / w.sum()) @ r
    rs = r * np.sqrt(v1)
    return rs / mad_sigma(rs)


def p_bicaudal(z):
    return np.array([math.erfc(abs(x) / math.sqrt(2)) for x in z])


def benjamini_hochberg(p, q=Q_FDR):
    n = len(p); o = np.argsort(p); sel = np.zeros(n, bool)
    k = np.nonzero(p[o] <= q * np.arange(1, n + 1) / n)[0]
    if len(k):
        sel[o[:k.max() + 1]] = True
    return sel


def _ic(x):
    lo, hi = np.percentile(x, [2.5, 97.5], axis=0)
    return lo, hi


def q1(wide, ano):
    """Decomposição contábil sem filtro de tamanho, com exterior; zero municípios omitidos."""
    m = add_flows(muni_table(wide))
    def bloco(t):
        out = {k: int(t[k].sum()) for k in ('pool', 'dvalid', 'dL', 'dF')}
        if t.comp1.notna().all() and t.comp2.notna().all():
            out['dcomparecimento'] = int((t.comp2 - t.comp1).sum())
            out['queda_brancos_nulos'] = int(-(((t.comp2 - t.valid2) - (t.comp1 - t.valid1)).sum()))
        return out
    return {'ano': int(ano), 'identidade_residuo': int(identity_gap(m)), 'nacional': bloco(m),
            'por_uf': {uf: bloco(g) for uf, g in m.groupby('SG_UF')}}


def q2(m26, m22, boot):
    """Diferença de coeficientes 2026 − 2022 por modelo, com/sem efeito fixo e com/sem refit robusto.
    O IC da diferença vem de bootstraps independentes por ano (sementes distintas)."""
    saida = []
    z26 = z_residuos(m26); z22 = z_residuos(m22)
    ex26 = np.abs(z26) > Z_ATIPICO; ex22 = np.abs(z22) > Z_ATIPICO
    for modelo in MODELOS:
        if modelo != 'A' and not (m26.tem_comp.all() and m22.tem_comp.all()):
            continue
        for fe in (True, False):
            for robusto in (False, True):
                res = {}
                for ano, m, ex, seed in ((2026, m26, ex26, BOOT_SEED), (2022, m22, ex22, BOOT_SEED + 1)):
                    nomes, beta, ok, (y, X, v1, g) = ajusta(m, modelo, fe, ex if robusto else None)
                    d = boot_draws(y[ok], X[ok], v1[ok], None if g is None else g[ok], boot, seed)
                    ident = [dp_pp(X[:, k], v1, g) >= MIN_DP_PP for k in range(len(nomes))]
                    res[ano] = (nomes, beta, d, ident)
                nomes = res[2026][0]; coef = {}
                for k, nm in enumerate(nomes):
                    dif = res[2026][2][:, k] - res[2022][2][:, k]
                    lo, hi = _ic(dif); l6, h6 = _ic(res[2026][2][:, k]); l2, h2 = _ic(res[2022][2][:, k])
                    coef[nm] = {'identificado': bool(res[2026][3][k] and res[2022][3][k]),
                                '2026': float(res[2026][1][k]), 'ic_2026': [float(l6), float(h6)],
                                '2022': float(res[2022][1][k]), 'ic_2022': [float(l2), float(h2)],
                                'dif': float(res[2026][1][k] - res[2022][1][k]), 'ic_dif': [float(lo), float(hi)]}
                saida.append({'modelo': modelo, 'efeito_fixo': fe, 'refit_robusto': robusto,
                              'n_2026': int(len(m26) - (ex26.sum() if robusto else 0)),
                              'n_2022': int(len(m22) - (ex22.sum() if robusto else 0)), 'coef': coef})
    return {'ajustes': saida, 'explicado_alpha': _explicado(saida)}


def _explicado(ajustes):
    """Critério do pré-registro: a diferença de α cai abaixo da metade com as covariáveis (modelo C
    contra o A), ou o IC da diferença inclui zero. Avaliado com efeito fixo e sem refit robusto."""
    d = {a['modelo']: a['coef']['alpha'] for a in ajustes if a['efeito_fixo'] and not a['refit_robusto']}
    if 'A' not in d or 'C' not in d:
        return None
    base, cov = d['A']['dif'], d['C']['dif']
    metade = abs(cov) < abs(base) / 2
    zero = d['C']['ic_dif'][0] <= 0 <= d['C']['ic_dif'][1]
    return {'dif_modelo_a': base, 'dif_modelo_c': cov, 'cai_abaixo_da_metade': bool(metade),
            'ic_inclui_zero': bool(zero), 'explicado': bool(metade or zero)}


def q3(m, secoes_por_mun):
    z_cheio = z_residuos(m); z_rob = z_residuos(m, excluir=np.abs(z_cheio) > Z_ATIPICO)
    sel_cheio = benjamini_hochberg(p_bicaudal(z_cheio)); sel_rob = benjamini_hochberg(p_bicaudal(z_rob))
    manter = sel_cheio & sel_rob
    pub = m.mun.map(secoes_por_mun).fillna(0).values >= MIN_SECOES_PUBLICAS
    n = len(m)
    lista = m[manter & pub].assign(z=z_cheio[manter & pub]).sort_values('z', key=np.abs, ascending=False)
    return {'testados': int(n), 'sinalizados_q05_ajuste_cheio': int(sel_cheio.sum()),
            'sinalizados_q05_refit_robusto': int(sel_rob.sum()), 'sinalizados_nos_dois': int(manter.sum()),
            'esperado_p05_por_acaso': float(Q_FDR * n),
            'falsos_admitidos_no_maximo': float(Q_FDR * manter.sum()),
            'lista_publicavel': [{'mun': r.mun, 'z': float(r.z)} for r in lista.itertuples()]}


def q4(m, secoes_por_mun):
    neg = m[m.dF < 0]
    pub = neg.mun.map(secoes_por_mun).fillna(0) >= MIN_SECOES_PUBLICAS
    out = {'elegiveis': int(len(m)), 'com_queda_de_flavio': int(len(neg))}
    if m.tem_comp.all():
        sem = neg[neg.dturn >= 0]
        out.update({'comparecimento_em_queda': int((neg.dturn < 0).sum()),
                    'comparecimento_estavel_ou_alta': int(len(sem)),
                    'lista_estavel_ou_alta': [{'mun': r.mun, 'dF': int(r.dF), 'dturn': int(r.dturn)}
                                              for r in sem[pub[sem.index]].sort_values('dF').itertuples()]})
    return out


def _fracoes(d):
    f = (np.abs(d.z) > Z_ATIPICO)
    por_uf = {uf: {'secoes': int(len(g)), 'fracao': float((np.abs(g.z) > Z_ATIPICO).mean())}
              for uf, g in d.groupby('SG_UF')}
    return float(f.mean()), por_uf


def _simula(d, kappa, rng):
    """Seção sob o modelo nulo: mesma taxa de Lula nos dois turnos, binomial mais sobredispersão κ."""
    n1 = (d.lula1 + d.flavio1).values; n2 = (d.lula2 + d.flavio2).values
    p = ((d.s1 + d.s2) / 2).values
    extra = rng.normal(0, 1, len(d)) * d.se.values / 100 * math.sqrt(max(kappa ** 2 - 1, 0))
    p2 = np.clip(p + extra, 0, 1)
    s = d[['SG_UF', 'CD_MUNICIPIO', 'comp1', 'comp2', 'apt1', 'apt2']].copy()
    s['lula1'] = rng.binomial(n1, p); s['flavio1'] = n1 - s.lula1
    s['lula2'] = rng.binomial(n2, p2); s['flavio2'] = n2 - s.lula2
    return swing_table(s)


def q5(w26, w22, n_sim):
    d26 = swing_table(w26[w26.SG_UF != 'ZZ']); d22 = swing_table(w22[w22.SG_UF != 'ZZ'])
    f26, uf26 = _fracoes(d26); f22, uf22 = _fracoes(d22)
    rng = np.random.default_rng(BOOT_SEED + 2)
    sim = [float((np.abs(_simula(d26, d26.attrs['kappa'], rng).z) > Z_ATIPICO).mean()) for _ in range(n_sim)]
    esp = float(np.mean(sim)) if sim else None
    max22 = max(v['fracao'] for v in uf22.values())
    return {'secoes_2026': int(len(d26)), 'secoes_2022': int(len(d22)),
            'kappa_2026': float(d26.attrs['kappa']), 'kappa_2022': float(d22.attrs['kappa']),
            'fracao_2026': f26, 'fracao_2022': f22, 'por_uf_2026': uf26, 'por_uf_2022': uf22,
            'maximo_por_uf_2022': float(max22), 'esperado_por_acaso_simulacao': esp,
            'simulacoes': int(n_sim), 'esperado_normal_teorico': math.erfc(Z_ATIPICO / math.sqrt(2)),
            'conjunto_atipico': bool(esp is not None and f26 > max22 and f26 > esp)}


def sensibilidade(w26, w22):
    """Estimativas pontuais de α e β (modelo B) 2026 e 2022 sob cada escolha analítica."""
    saida = []
    for mv in (100, 200, 500):
        for regiao, filtro in (('todas', None), ('nordeste', True), ('fora_do_nordeste', False)):
            ms = []
            for w in (w26, w22):
                if filtro is not None:
                    w = w[w.SG_UF.isin(NE) == filtro]
                ms.append(prepara(w, mv))
            if any(len(x) < 30 or not x.tem_comp.all() for x in ms):
                continue
            ex = [np.abs(z_residuos(x)) > Z_ATIPICO for x in ms]
            for fe in (True, False):
                for robusto in (False, True):
                    b = [ajusta(x, 'B', fe, e if robusto else None)[1] for x, e in zip(ms, ex)]
                    saida.append({'min_valid': mv, 'regiao': regiao, 'efeito_fixo': fe, 'refit_robusto': robusto,
                                  'alpha': {'2026': float(b[0][0]), '2022': float(b[1][0]),
                                            'dif': float(b[0][0] - b[1][0])},
                                  'beta1': {'2026': float(b[0][1]), '2022': float(b[1][1]),
                                            'dif': float(b[0][1] - b[1][1])}})
    return saida


def analise(dir, out, year, control_year, ufs, min_valid=200, boot=2000, n_sim=20):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    w26 = load_year(dir, year, ufs); w22 = load_year(dir, control_year, ufs)
    m26 = prepara(w26, min_valid); m22 = prepara(w22, min_valid)
    sec = w26.assign(mun=w26.SG_UF + '-' + w26.CD_MUNICIPIO).groupby('mun').size().to_dict()
    res = {'parametros': {'ano': int(year), 'controle': int(control_year), 'ufs': list(ufs), 'min_valid': min_valid,
                          'boot': boot, 'simulacoes': n_sim, 'z_atipico': Z_ATIPICO, 'q_fdr': Q_FDR,
                          'min_secoes_publicas': MIN_SECOES_PUBLICAS},
           'q1': {'2026': q1(w26, year), '2022': q1(w22, control_year)},
           'q2': q2(m26, m22, boot), 'q3': q3(m26, sec), 'q4': q4(m26, sec),
           'q5': q5(w26, w22, n_sim), 'sensibilidade': sensibilidade(w26, w22),
           'q6': {'testavel': False, 'motivo': 'hora de encerramento por seção não existe nos CSV do TSE'}}
    (out / 'resultados.json').write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    print(f'resultados.json: Q3 {res["q3"]["sinalizados_nos_dois"]} município(s) nos dois ajustes de '
          f'{res["q3"]["testados"]}; Q5 fração 2026 {res["q5"]["fracao_2026"]:.2e} '
          f'(esperado {res["q5"]["esperado_por_acaso_simulacao"]})')
    return res
