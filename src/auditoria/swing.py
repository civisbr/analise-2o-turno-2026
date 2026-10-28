import pathlib

import numpy as np
import pandas as pd

from .closing import closing_test
from .load import MIN_SECOES_PUBLICAS, load_year
from .robust import mad_sigma


MIN_VOTOS = 50   # seção com menos votos nominais em qualquer turno fica fora do swing


def secoes_por_municipio(wide, min_votes=MIN_VOTOS):
    """Seções que entram no swing, por município: é a contagem que vale para o corte de publicação (regra 7)."""
    d = wide[(wide.lula1 + wide.flavio1 >= min_votes) & (wide.lula2 + wide.flavio2 >= min_votes)]
    return (d.SG_UF + '-' + d.CD_MUNICIPIO).value_counts()


def swing_table(wide, min_votes=MIN_VOTOS):
    d = wide.copy()
    d = d[(d.lula1 + d.flavio1 >= min_votes) & (d.lula2 + d.flavio2 >= min_votes)].copy()
    n1 = d.lula1 + d.flavio1; n2 = d.lula2 + d.flavio2
    d['s1'] = d.lula1 / n1; d['s2'] = d.lula2 / n2
    d['swing'] = (d.s2 - d.s1) * 100
    p = (d.s1 + d.s2) / 2
    d['se'] = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) * 100          # ruído binomial esperado (pp)
    d['dturn'] = (d.comp2 / d.apt2 - d.comp1 / d.apt1) * 100
    d['mun'] = d.SG_UF + '-' + d.CD_MUNICIPIO
    d['ref'] = d.groupby('mun').swing.transform('median')           # swing típico do município
    d['resid'] = d.swing - d.ref
    r = (d.resid / d.se).where(d.se > 0, 0.0)                       # se=0 (p=0 ou 1 nos dois turnos): z indefinido, a seção não é sinalizável
    kappa = mad_sigma(r)                                            # sobredispersão robusta
    d['z'] = r / kappa
    d.attrs['kappa'] = kappa
    return d


def summarize(d):
    """Dois níveis: (1) seções fora do padrão do próprio município (z); (2) municípios inteiros fora
    do padrão da UF (z_mun) – o nível 2 pega anomalia concentrada que a mediana municipal absorveria."""
    flagged = d[np.abs(d.z) > 4]
    d = d.assign(exc=d.resid / 100 * (d.lula2 + d.flavio2), w=d.lula2 + d.flavio2,
                 n1=d.lula1 + d.flavio1, wsw=d.swing * (d.lula2 + d.flavio2),
                 wl1=d.s1 * (d.lula1 + d.flavio1))
    g = d.groupby('mun')
    muni = g.agg(uf=('SG_UF', 'first'), secoes=('swing', 'size'), swing_mediano=('swing', 'median'),
                 votos_2t=('w', 'sum'), n1=('n1', 'sum'), wsw=('wsw', 'sum'), wl1=('wl1', 'sum'),
                 flag_pos=('z', lambda s: (s > 4).sum()), flag_neg=('z', lambda s: (s < -4).sum()))
    muni['swing_medio'] = muni.wsw / muni.votos_2t
    muni['excesso_liquido_votos'] = g.exc.sum()
    p = (muni.wl1 / muni.n1 + (muni.wl1 / muni.n1 + muni.swing_medio / 100)) / 2
    se = np.sqrt(p * (1 - p) * (1 / muni.n1 + 1 / muni.votos_2t)) * 100
    z = pd.Series(np.nan, index=muni.index)
    for uf, m in muni[muni.secoes >= 10].groupby('uf'):
        r = (m.swing_medio - m.swing_medio.median()) / se[m.index]
        z[m.index] = r / max(mad_sigma(r), 1e-9)
    muni['z_mun'] = z
    # Município com poucas seções: contagem de seções sinalizadas apontaria a seção (regra 7).
    small = muni.secoes < MIN_SECOES_PUBLICAS
    muni.loc[small, ['flag_pos', 'flag_neg', 'excesso_liquido_votos', 'swing_mediano', 'swing_medio', 'votos_2t']] = np.nan
    muni = muni.drop(columns=['n1', 'wsw', 'wl1'])
    return flagged, muni.reindex(muni.z_mun.abs().sort_values(ascending=False, na_position='last').index)


def analyze(dir, out, year, control_year, ufs, closing=None, private_dir='data/private'):
    # Saída por seção fica fora de data/derived (versionado): project.md, seção 1, regra 7.
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    private = pathlib.Path(private_dir); private.mkdir(parents=True, exist_ok=True)
    d = swing_table(load_year(dir, year, ufs))
    flagged, muni = summarize(d)
    print(f'\n{year}: seções analisadas {len(d):,}; sobredispersão kappa={d.attrs["kappa"]:.2f}')
    print(f'seções com |z|>4: {len(flagged):,} ({len(flagged)/len(d):.3%}) '
          f'– Lula+: {(flagged.z>0).sum():,}  Lula−: {(flagged.z<0).sum():,}')
    for uf, g in d.groupby('SG_UF'):
        rho = g[['swing', 'dturn']].corr(method='spearman').iloc[0, 1]
        print(f'  {uf}: swing mediano {g.swing.median():+.2f} pp; ρ(swing, Δcomparecimento)={rho:+.2f}')
    d.to_csv(private / f'secoes_{year}.csv', index=False)
    flagged.to_csv(private / f'secoes_sinalizadas_{year}.csv', index=False)
    muni.to_csv(out / f'swing_municipios_{year}.csv')   # municipios_<ano>.csv é a tabela pública do build
    print('\nTop 15 municípios por |z_mun| (≥ 10 seções):')
    print(muni[muni.secoes >= 10].head(15).round(2).to_string())
    if control_year:
        c = swing_table(load_year(dir, control_year, ufs))
        cf, cm = summarize(c)
        j = pd.concat([muni.swing_mediano.rename('swing_mediano_a'), cm.swing_mediano.rename('swing_mediano_c')],
                      axis=1, join='inner')
        print(f'\nControle {control_year}: seções sinalizadas {len(cf)/len(c):.3%} (vs {len(flagged)/len(d):.3%})')
        print(f'correlação do swing mediano municipal {year} x {control_year}: {j.corr().iloc[0,1]:+.2f} '
              f'({len(j)} municípios)')
    if closing:
        closing_test(d, closing)
