"""Q1–Q5 do pré-registro como números estruturados (resultados.json), sem texto interpretativo.

A página lê só este arquivo (regra 5). Município publicado = pelo menos MIN_SECOES_PUBLICAS seções
(regra 7); contagens agregadas incluem todos os elegíveis, listas nominais só os publicáveis.
"""
import json
import math
import pathlib

import numpy as np
import polars as pl

from .balance import add_flows, identity_gap, muni_table, tem_comparecimento, uf_array
from .load import MIN_SECOES_PUBLICAS, NE, load_year
from .robust import BOOT_SEED, mad_positivo, wls
from .swing import secoes_por_municipio, swing_table

Z_ATIPICO = 4.0
Q_FDR = 0.05
MIN_DP_PP = 0.5          # abaixo disso o coeficiente não é identificado (pré-registro, limiares)
MODELOS = ('A', 'B', 'C')


def prepara(wide, min_valid):
    """Tabela municipal elegível para Q2–Q4. Exterior (ZZ) fica de fora; Q1 usa tabela própria."""
    m = add_flows(muni_table(wide.filter(pl.col('SG_UF') != 'ZZ')))
    m = m.filter((pl.col('valid1') >= min_valid) & (pl.col('valid2') >= min_valid))
    return m.with_columns(
        tem_comp=pl.col('comp1').is_not_null() & pl.col('comp2').is_not_null(),
        dturn=pl.col('comp2') - pl.col('comp1'),
        dbn=-((pl.col('comp2') - pl.col('valid2')) - (pl.col('comp1') - pl.col('valid1'))))   # queda de brancos+nulos (>0 = caiu)


def _v1(m):
    return m['valid1'].to_numpy().astype(float)


def _razao(m, col):
    return (m[col] / m['valid1']).to_numpy()


def regressores(m, modelo):
    v1 = _v1(m)
    c = {'alpha': _razao(m, 'pool')}
    if modelo == 'A':
        c['beta'] = _razao(m, 'dvalid')
    else:
        c['beta1'] = _razao(m, 'dturn'); c['beta2'] = _razao(m, 'dbn')
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
    y = _razao(m, 'dL'); v1 = _v1(m)
    g = uf_array(m) if fe and m['SG_UF'].n_unique() > 1 else None
    ok = np.ones(m.height, bool) if excluir is None else ~excluir
    return nomes, wls(y[ok], X[ok], v1[ok], None if g is None else g[ok]), ok, (y, X, v1, g)


def z_residuos(m, fe=True, excluir=None):
    """z robusto (MAD) dos resíduos do modelo B, com efeito fixo de UF no ajuste e na centralização."""
    nomes, beta, ok, (y, X, v1, g) = ajusta(m, 'B' if m['tem_comp'].all() else 'A', fe, excluir)
    r = y - X @ beta; w = v1 * ok
    if g is not None:
        for k in np.unique(g):
            mk = g == k
            if w[mk].sum() > 0:
                r[mk] -= (w[mk] / w[mk].sum()) @ r[mk]
    else:
        r -= (w / w.sum()) @ r
    rs = r * np.sqrt(v1)
    return rs / mad_positivo(rs, 'z_residuos')


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
    """Decomposição contábil sem filtro de tamanho; o exterior (ZZ) sai em bloco próprio, fora do nacional.
    A tabela municipal usa a mesma supressão da tabela pública (UF-OUTROS com supressão complementar), para que
    total da UF menos a soma dos municípios não isole um município pequeno."""
    m = add_flows(muni_table(wide))

    def bloco(t):
        out = {k: int(t[k].sum()) for k in ('pool', 'dvalid', 'dL', 'dF')}
        if tem_comparecimento(t):
            out['dcomparecimento'] = int((t['comp2'] - t['comp1']).sum())
            out['queda_brancos_nulos'] = int(-(((t['comp2'] - t['valid2']) - (t['comp1'] - t['valid1'])).sum()))
        return out
    ext = m.filter(pl.col('SG_UF') == 'ZZ'); br = m.filter(pl.col('SG_UF') != 'ZZ')
    out = {'ano': int(ano), 'identidade_residuo': int(identity_gap(m)), 'nacional': bloco(br),
           'por_uf': {uf: bloco(g) for (uf,), g in sorted(br.partition_by('SG_UF', as_dict=True).items())}}
    if ext.height:
        out['exterior'] = bloco(ext)
    from .build import agrega_pequenos   # build importa muni_table de balance
    cols = ['secoes', 'valid1', 'valid2', 'pool', 'dvalid', 'dL', 'dF'] + (['comp1', 'comp2'] if tem_comparecimento(br) else [])
    pub = agrega_pequenos(br.select(['SG_UF', 'mun'] + cols))
    out['municipios'] = {row['mun']: bloco(pub.slice(i, 1)) for i, row in enumerate(pub.iter_rows(named=True))}
    return out


def boot_pareado(m26, m22, ok26, ok22, modelo, fe, B, seed):
    """Reamostra municípios (nomes) em comum para os dois anos: os mesmos municípios entram nas duas
    amostras, então a covariância entre 2026 e 2022 fica na diferença."""
    nomes = np.array(sorted(set(m26['mun']) | set(m22['mun'])))
    pos = []
    for m, ok in ((m26, ok26), (m22, ok22)):
        por_nome = {n: i for i, n in enumerate(m['mun']) if ok[i]}
        pos.append(np.array([por_nome.get(n, -1) for n in nomes], dtype=int))
    dados = []
    for m, ok in ((m26, ok26), (m22, ok22)):
        _, _, _, (y, X, v1, g) = ajusta(m, modelo, fe)
        dados.append((y, X, v1, g))
    rng = np.random.default_rng(seed); out = [[], []]
    for _ in range(B):
        s_ = rng.integers(0, len(nomes), len(nomes))
        for k in (0, 1):
            y, X, v1, g = dados[k]; i = pos[k][s_]; i = i[i >= 0]
            out[k].append(wls(y[i], X[i], v1[i], None if g is None else g[i]))
    return np.array(out[0]), np.array(out[1])


def q2(m26, m22, boot, a26='2026', a22='2022'):
    """Diferença de coeficientes 2026 − 2022 por modelo, com/sem efeito fixo e com/sem refit robusto.
    O IC da diferença vem de bootstraps independentes por ano (sementes distintas)."""
    saida = []
    z26 = z_residuos(m26); z22 = z_residuos(m22)
    ex26 = np.abs(z26) > Z_ATIPICO; ex22 = np.abs(z22) > Z_ATIPICO
    for modelo in MODELOS:
        if modelo != 'A' and not (m26['tem_comp'].all() and m22['tem_comp'].all()):
            continue
        for fe in (True, False):
            for robusto in (False, True):
                if fe and (m26['SG_UF'].n_unique() == 1 or m22['SG_UF'].n_unique() == 1):
                    continue   # com uma UF só o efeito fixo é igual ao ajuste sem ele
                res = {}
                ok26, ok22 = (~ex26, ~ex22) if robusto else (np.ones(m26.height, bool), np.ones(m22.height, bool))
                d26, d22 = boot_pareado(m26, m22, ok26, ok22, modelo, fe, boot, BOOT_SEED)
                for ano, m, ex, ok, d in ((a26, m26, ex26, ok26, d26), (a22, m22, ex22, ok22, d22)):
                    nomes, beta, _, (y, X, v1, g) = ajusta(m, modelo, fe, ex if robusto else None)
                    ident = [dp_pp(X[:, k], v1, uf_array(m)) >= MIN_DP_PP for k in range(len(nomes))]
                    res[ano] = (nomes, beta, d, ident)
                nomes = res[a26][0]; coef = {}
                for k, nm in enumerate(nomes):
                    dif = res[a26][2][:, k] - res[a22][2][:, k]
                    lo, hi = _ic(dif); l6, h6 = _ic(res[a26][2][:, k]); l2, h2 = _ic(res[a22][2][:, k])
                    coef[nm] = {'identificado': bool(res[a26][3][k] and res[a22][3][k]),
                                a26: float(res[a26][1][k]), 'ic_' + a26: [float(l6), float(h6)],
                                a22: float(res[a22][1][k]), 'ic_' + a22: [float(l2), float(h2)],
                                'dif': float(res[a26][1][k] - res[a22][1][k]), 'ic_dif': [float(lo), float(hi)]}
                saida.append({'modelo': modelo, 'efeito_fixo': fe, 'refit_robusto': robusto,
                              'n_' + a26: int(m26.height - (ex26.sum() if robusto else 0)),
                              'n_' + a22: int(m22.height - (ex22.sum() if robusto else 0)), 'coef': coef})
    return {'ajustes': saida, 'explicado': _explicado(saida)}


def _explicado(ajustes):
    """Critério do pré-registro, aplicado a cada coeficiente: a diferença 2026 − 2022 cai abaixo da metade
    do modelo A para o C, ou o IC da diferença no C inclui zero. α compara com α; β1 e β2 (modelo C)
    comparam com o β único do A. Avaliado com efeito fixo e sem refit robusto."""
    d = {a['modelo']: a['coef'] for a in ajustes if a['efeito_fixo'] and not a['refit_robusto']}
    if 'A' not in d or 'C' not in d:
        return None
    por_coef = {}
    for nome, base_nome in (('alpha', 'alpha'), ('beta1', 'beta'), ('beta2', 'beta')):
        if nome not in d['C'] or base_nome not in d['A']:
            continue
        if not (d['C'][nome].get('identificado', True) and d['A'][base_nome].get('identificado', True)):
            por_coef[nome] = {'avaliavel': False}   # sem variação suficiente, o IC incluiria zero sem informação
            continue
        base, cov = d['A'][base_nome]['dif'], d['C'][nome]['dif']
        metade = abs(cov) < abs(base) / 2
        zero = d['C'][nome]['ic_dif'][0] <= 0 <= d['C'][nome]['ic_dif'][1]
        por_coef[nome] = {'dif_modelo_a': base, 'dif_modelo_c': cov, 'cai_abaixo_da_metade': bool(metade),
                          'ic_inclui_zero': bool(zero), 'explicado': bool(metade or zero)}
    avaliados = {k: v for k, v in por_coef.items() if v.get('avaliavel', True)}
    if not avaliados:
        return None
    return {'por_coeficiente': por_coef, 'explicado': bool(all(v['explicado'] for v in avaliados.values()))}


def _publicavel(m, secoes_por_mun):
    return np.array([secoes_por_mun.get(x, 0) for x in m['mun']]) >= MIN_SECOES_PUBLICAS


def q3(m, secoes_por_mun):
    z_cheio = z_residuos(m); z_rob = z_residuos(m, excluir=np.abs(z_cheio) > Z_ATIPICO)
    sel_cheio = benjamini_hochberg(p_bicaudal(z_cheio)); sel_rob = benjamini_hochberg(p_bicaudal(z_rob))
    manter = sel_cheio & sel_rob
    pub = _publicavel(m, secoes_por_mun)
    n = m.height
    lista = (m.filter(pl.Series(manter & pub)).with_columns(z=pl.Series(z_cheio[manter & pub]))
              .sort([pl.col('z').abs(), 'mun'], descending=[True, False]))
    return {'testados': int(n), 'sinalizados_q05_ajuste_cheio': int(sel_cheio.sum()),
            'sinalizados_q05_refit_robusto': int(sel_rob.sum()), 'sinalizados_nos_dois': int(manter.sum()),
            'observado_p05': int((p_bicaudal(z_cheio) < Q_FDR).sum()),
            'esperado_p05_por_acaso': float(Q_FDR * n),
            'falsos_esperados_ate': float(Q_FDR * manter.sum()),
            'lista_publicavel': [{'mun': mun, 'z': float(z)} for mun, z in lista.select('mun', 'z').iter_rows()]}


def q4(m, secoes_por_mun):
    neg = m.filter(pl.col('dF') < 0)
    out = {'elegiveis': int(m.height), 'com_queda_de_flavio': int(neg.height)}
    if m['tem_comp'].all():
        sem = neg.filter(pl.col('dturn') >= 0)
        pub = _publicavel(sem, secoes_por_mun)
        out.update({'comparecimento_em_queda': int(neg.filter(pl.col('dturn') < 0).height),
                    'comparecimento_estavel_ou_alta': int(sem.height),
                    'lista_estavel_ou_alta': [{'mun': mun, 'dF': int(df_), 'dturn': int(dt)}
                                              for mun, df_, dt in sem.filter(pl.Series(pub)).sort(['dF', 'mun'])
                                              .select('mun', 'dF', 'dturn').iter_rows()]})
    return out


def _fracoes(d):
    atipica = pl.col('z').abs() > Z_ATIPICO
    por_uf = {uf: {'secoes': int(g.height), 'fracao': float(g.select(atipica.mean()).item())}
              for (uf,), g in sorted(d.partition_by('SG_UF', as_dict=True).items())}
    return float(d.select(atipica.mean()).item()), por_uf


def _simula(d, kappa, rng):
    """Seção sob o modelo nulo: mesma taxa de Lula nos dois turnos, binomial mais sobredispersão κ."""
    n1 = (d['lula1'] + d['flavio1']).to_numpy(); n2 = (d['lula2'] + d['flavio2']).to_numpy()
    p = ((d['s1'] + d['s2']) / 2).to_numpy()
    extra = rng.normal(0, 1, d.height) * d['se'].to_numpy() / 100 * math.sqrt(max(kappa ** 2 - 1, 0))
    p2 = np.clip(p + extra, 0, 1)
    lula1 = rng.binomial(n1, p); lula2 = rng.binomial(n2, p2)
    s = d.select(['SG_UF', 'CD_MUNICIPIO', 'comp1', 'comp2', 'apt1', 'apt2']).with_columns(
        lula1=pl.Series(lula1), flavio1=pl.Series(n1 - lula1), lula2=pl.Series(lula2), flavio2=pl.Series(n2 - lula2))
    return swing_table(s)[0]


def q5(w26, w22, n_sim, a26='2026', a22='2022'):
    d26, k26 = swing_table(w26.filter(pl.col('SG_UF') != 'ZZ')); d22, k22 = swing_table(w22.filter(pl.col('SG_UF') != 'ZZ'))
    f26, uf26 = _fracoes(d26); f22, uf22 = _fracoes(d22)
    rng = np.random.default_rng(BOOT_SEED + 2)
    sim = [float(_simula(d26, k26, rng).select((pl.col('z').abs() > Z_ATIPICO).mean()).item()) for _ in range(n_sim)]
    esp = float(np.mean(sim)) if sim else None
    max22 = max((v['fracao'] for v in uf22.values()), default=0.0)
    return {'secoes_' + a26: int(d26.height), 'secoes_' + a22: int(d22.height),
            'kappa_' + a26: float(k26), 'kappa_' + a22: float(k22),
            'fracao_' + a26: f26, 'fracao_' + a22: f22, 'por_uf_' + a26: uf26, 'por_uf_' + a22: uf22,
            'maximo_por_uf_' + a22: float(max22), 'esperado_por_acaso_simulacao': esp,
            'simulacoes': int(n_sim), 'esperado_normal_teorico': math.erfc(Z_ATIPICO / math.sqrt(2)),
            'conjunto_atipico': bool(esp is not None and f26 > max22 and f26 > esp)}


def sensibilidade(w26, w22, a26='2026', a22='2022'):
    """Estimativas pontuais de α e β (modelo B) 2026 e 2022 sob cada escolha analítica."""
    saida = []; puladas = []
    for mv in (100, 200, 500):
        for regiao, filtro in (('todas', None), ('nordeste', True), ('fora_do_nordeste', False)):
            ms = []
            for w in (w26, w22):
                if filtro is not None:
                    w = w.filter(pl.col('SG_UF').is_in(NE) == filtro)
                ms.append(prepara(w, mv))
            if any(x.height < 30 or not x['tem_comp'].all() for x in ms):
                puladas.append({'min_valid': mv, 'regiao': regiao})
                continue
            ex = [np.abs(z_residuos(x)) > Z_ATIPICO for x in ms]
            for fe in (True, False):
                for robusto in (False, True):
                    b = [ajusta(x, 'B', fe, e if robusto else None)[1] for x, e in zip(ms, ex)]
                    ident = [all(dp_pp(regressores(x, 'B')[1][:, k], _v1(x), uf_array(x)) >= MIN_DP_PP
                                 for x in ms) for k in range(3)]
                    saida.append({'min_valid': mv, 'regiao': regiao, 'efeito_fixo': fe, 'refit_robusto': robusto,
                                  'identificado': {'alpha': ident[0], 'beta1': ident[1], 'beta2': ident[2]},
                                  'alpha': {a26: float(b[0][0]), a22: float(b[1][0]),
                                            'dif': float(b[0][0] - b[1][0])},
                                  'beta1': {a26: float(b[0][1]), a22: float(b[1][1]),
                                            'dif': float(b[0][1] - b[1][1])},
                                  'beta2': {a26: float(b[0][2]), a22: float(b[1][2]),
                                            'dif': float(b[0][2] - b[1][2])}})
    return {'ajustes': saida, 'puladas': puladas}


def _arredonda(x):
    """10 dígitos significativos: BLAS/NumPy diferentes variam nos últimos bits e quebrariam a comparação byte a byte."""
    if isinstance(x, float):
        return float(f'{x:.10g}')
    if isinstance(x, dict):
        return {k: _arredonda(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_arredonda(v) for v in x]
    return x


def _secoes_publicas(w):
    """Município publicável por lista nominal: pelo menos 10 seções em todas as contagens usadas (tabela municipal e swing)."""
    todas = {mun: n for mun, n in w.with_columns(mun=pl.col('SG_UF') + '-' + pl.col('CD_MUNICIPIO')).group_by('mun').agg(pl.len()).iter_rows()}
    swing = secoes_por_municipio(w.filter(pl.col('SG_UF') != 'ZZ'))
    return {mun: min(n, swing.get(mun, 0)) for mun, n in todas.items()}


def analise(dir, out, year, control_year, ufs, min_valid=200, boot=2000, n_sim=20):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    com_ext = list(ufs) + (['ZZ'] if 'ZZ' not in ufs else [])
    w26 = load_year(dir, year, com_ext); w22 = load_year(dir, control_year, com_ext)
    a26, a22 = str(year), str(control_year)
    m26 = prepara(w26, min_valid); m22 = prepara(w22, min_valid)
    sec26, sec22 = (_secoes_publicas(w) for w in (w26, w22))
    res = {'parametros': {'ano': int(year), 'controle': int(control_year), 'ufs': list(ufs), 'exterior_so_em_q1': True, 'min_valid': min_valid,
                          'boot': boot, 'simulacoes': n_sim, 'z_atipico': Z_ATIPICO, 'q_fdr': Q_FDR,
                          'min_secoes_publicas': MIN_SECOES_PUBLICAS},
           'q1': {a26: q1(w26, year), a22: q1(w22, control_year)},
           'q2': q2(m26, m22, boot, a26, a22), 'q3': {a26: q3(m26, sec26), a22: q3(m22, sec22)}, 'q4': {a26: q4(m26, sec26), a22: q4(m22, sec22)},
           'q5': q5(w26, w22, n_sim, a26, a22), 'sensibilidade': sensibilidade(w26, w22, a26, a22),
           'q6': {'testavel': False, 'motivo': 'hora de encerramento por seção não existe nos CSV do TSE'}}
    res = _arredonda(res)
    (out / 'resultados.json').write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n',
                                          encoding='utf-8')
    print(f'resultados.json: Q3 {res["q3"][a26]["sinalizados_nos_dois"]} município(s) nos dois ajustes de '
          f'{res["q3"][a26]["testados"]}; Q5 fração {a26} {res["q5"]["fracao_" + a26]:.2e} '
          f'(esperado {res["q5"]["esperado_por_acaso_simulacao"]})')
    return res
