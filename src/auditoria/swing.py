import pathlib

import numpy as np
import polars as pl

from .closing import closing_test
from .load import MIN_SECOES_PUBLICAS, load_year
from .robust import mad_positivo, mad_sigma


MIN_VOTOS = 50   # seção com menos votos nominais em qualquer turno fica fora do swing


def _entra(min_votes):
    return ((pl.col('lula1') + pl.col('flavio1') >= min_votes) & (pl.col('lula2') + pl.col('flavio2') >= min_votes))


def secoes_por_municipio(wide, min_votes=MIN_VOTOS):
    """Seções que entram no swing, por município: é a contagem que vale para o corte de publicação (regra 7)."""
    d = wide.filter(_entra(min_votes)).with_columns(mun=pl.col('SG_UF') + '-' + pl.col('CD_MUNICIPIO'))
    return {mun: n for mun, n in d.group_by('mun').agg(pl.len()).iter_rows()}


def swing_table(wide, min_votes=MIN_VOTOS):
    """Retorna (tabela por seção, kappa). kappa é a sobredispersão robusta (MAD) de resid/se."""
    n1 = pl.col('lula1') + pl.col('flavio1'); n2 = pl.col('lula2') + pl.col('flavio2')
    d = wide.filter(_entra(min_votes)).with_columns(s1=pl.col('lula1') / n1, s2=pl.col('lula2') / n2)
    d = d.with_columns(swing=(pl.col('s2') - pl.col('s1')) * 100, _p=(pl.col('s1') + pl.col('s2')) / 2)
    d = d.with_columns(
        se=(pl.col('_p') * (1 - pl.col('_p')) * (1 / n1 + 1 / n2)).sqrt() * 100,          # ruído binomial esperado (pp)
        dturn=(pl.col('comp2') / pl.col('apt2') - pl.col('comp1') / pl.col('apt1')) * 100,
        mun=pl.col('SG_UF') + '-' + pl.col('CD_MUNICIPIO')).drop('_p')
    d = d.with_columns(ref=pl.col('swing').median().over('mun'))                           # swing típico do município
    d = d.with_columns(resid=pl.col('swing') - pl.col('ref'))
    # se=0 (p=0 ou 1 nos dois turnos): z indefinido, a seção não é sinalizável
    r = d.select(pl.when(pl.col('se') > 0).then(pl.col('resid') / pl.col('se')).otherwise(0.0)).to_series().to_numpy()
    kappa = mad_positivo(r, 'swing_table')                                                 # sobredispersão robusta
    return d.with_columns(z=pl.Series(r / kappa)), kappa


def summarize(d):
    """Dois níveis: (1) seções fora do padrão do próprio município (z); (2) municípios inteiros fora
    do padrão da UF (z_mun) – o nível 2 pega anomalia concentrada que a mediana municipal absorveria."""
    flagged = d.filter(pl.col('z').abs() > 4)
    w = pl.col('lula2') + pl.col('flavio2'); n1 = pl.col('lula1') + pl.col('flavio1')
    muni = (d.group_by('mun').agg(
                uf=pl.col('SG_UF').first(), secoes=pl.len().cast(pl.Int64), swing_mediano=pl.col('swing').median(),
                votos_2t=w.sum(), n1=n1.sum(), wsw=(pl.col('swing') * w).sum(), wl1=(pl.col('s1') * n1).sum(),
                flag_pos=(pl.col('z') > 4).sum().cast(pl.Int64), flag_neg=(pl.col('z') < -4).sum().cast(pl.Int64),
                excesso_liquido_votos=(pl.col('resid') / 100 * w).sum())
              .sort('mun')
              .with_columns(swing_medio=pl.col('wsw') / pl.col('votos_2t')))
    p = (pl.col('wl1') / pl.col('n1') + (pl.col('wl1') / pl.col('n1') + pl.col('swing_medio') / 100)) / 2
    se = muni.select((p * (1 - p) * (1 / pl.col('n1') + 1 / pl.col('votos_2t'))).sqrt() * 100).to_series().to_numpy()
    sm = muni['swing_medio'].to_numpy(); uf = muni['uf'].to_numpy().astype(str); sec = muni['secoes'].to_numpy()
    z = np.full(len(muni), np.nan)
    for u in np.unique(uf[sec >= 10]):
        i = np.nonzero((uf == u) & (sec >= 10))[0]
        r = (sm[i] - np.median(sm[i])) / se[i]
        z[i] = r / max(mad_sigma(r), 1e-9)
    muni = muni.with_columns(z_mun=pl.Series(z, nan_to_null=True))
    # Município com poucas seções: contagem de seções sinalizadas apontaria a seção (regra 7).
    small = pl.col('secoes') < MIN_SECOES_PUBLICAS
    ocultar = ['flag_pos', 'flag_neg', 'excesso_liquido_votos', 'swing_mediano', 'swing_medio', 'votos_2t']
    muni = muni.with_columns([pl.when(small).then(None).otherwise(pl.col(c)).alias(c) for c in ocultar])
    muni = muni.select(['mun', 'uf', 'secoes', 'swing_mediano', 'votos_2t', 'flag_pos', 'flag_neg', 'swing_medio',
                        'excesso_liquido_votos', 'z_mun'])
    return flagged, muni.sort(pl.col('z_mun').abs(), descending=True, nulls_last=True, maintain_order=True)


def _imprime(df):
    with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_hide_dataframe_shape=True):
        print(df)


def analyze(dir, out, year, control_year, ufs, closing=None, private_dir='data/private'):
    # Saída por seção fica fora de data/derived (versionado): project.md, seção 1, regra 7.
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    private = pathlib.Path(private_dir); private.mkdir(parents=True, exist_ok=True)
    d, kappa = swing_table(load_year(dir, year, ufs))
    flagged, muni = summarize(d)
    print(f'\n{year}: seções analisadas {d.height:,}; sobredispersão kappa={kappa:.2f}')
    print(f'seções com |z|>4: {flagged.height:,} ({flagged.height/d.height:.3%}) '
          f'– Lula+: {flagged.filter(pl.col("z") > 0).height:,}  Lula−: {flagged.filter(pl.col("z") < 0).height:,}')
    for (uf,), g in sorted(d.partition_by('SG_UF', as_dict=True).items()):
        rho = g.select(pl.corr('swing', 'dturn', method='spearman')).item()
        print(f'  {uf}: swing mediano {g["swing"].median():+.2f} pp; ρ(swing, Δcomparecimento)={rho:+.2f}')
    d.write_csv(private / f'secoes_{year}.csv')
    flagged.write_csv(private / f'secoes_sinalizadas_{year}.csv')
    muni.write_csv(out / f'swing_municipios_{year}.csv')   # municipios_<ano>.csv é a tabela pública do build
    print('\nTop 15 municípios por |z_mun| (≥ 10 seções):')
    _imprime(muni.filter(pl.col('secoes') >= 10).head(15))
    if control_year:
        c, _ = swing_table(load_year(dir, control_year, ufs))
        cf, cm = summarize(c)
        j = (muni.select('mun', a=pl.col('swing_mediano')).join(cm.select('mun', c=pl.col('swing_mediano')), on='mun')
                 .drop_nulls())
        print(f'\nControle {control_year}: seções sinalizadas {cf.height/c.height:.3%} (vs {flagged.height/d.height:.3%})')
        print(f'correlação do swing mediano municipal {year} x {control_year}: {j.select(pl.corr("a", "c")).item():+.2f} '
              f'({j.height} municípios)')
    if closing:
        closing_test(d, closing)
