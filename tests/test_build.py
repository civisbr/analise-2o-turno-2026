import json

import polars as pl
import pytest

from auditoria import cli
from auditoria.build import agrega_descartes, agrega_pequenos, build, descartes
from auditoria.load import load_sections
from auditoria.munzona import crosscheck, load_munzona
from synth import UFS


@pytest.fixture(scope='module')
def longo(synth_dir):
    return load_sections(synth_dir, 2026, UFS)


descartes_falso = pl.DataFrame([{'SG_UF': 'BA', 'NR_TURNO': '1', 'secoes': 1, 'aptos': 5, 'comparecimento': 0,
                                 'validos': 0, 'lula': 0, 'flavio': 0}])


def _build(synth_dir, tmp_path, year=2026):
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return build(synth_dir, tmp_path / 'derived', tmp_path / 'private', year, exige=False)


def test_build_gera_parquet_privado_e_tabelas_municipais(synth_dir, tmp_path):
    r = _build(synth_dir, tmp_path)
    secoes = pl.read_parquet(tmp_path / 'private' / 'secoes_2026.parquet')
    assert {'NR_SECAO', 'NR_ZONA', 'lula', 'nominais'} <= set(secoes.columns)
    nomes = {p.name for p in (tmp_path / 'derived').iterdir()}
    assert {'municipios_2026.csv', 'descartes_2026.csv'} <= nomes
    for f in (tmp_path / 'derived').glob('*.csv'):
        cols = set(pl.read_csv(f, n_rows=0).columns)
        assert not cols & {'NR_SECAO', 'NR_ZONA'}, f
    m = pl.read_csv(tmp_path / 'derived' / 'municipios_2026.csv')
    assert m.height == 160 and (m['valid1'] > 0).all() and m['secoes'].min() >= 29 and (m['municipios_agregados'] == 0).all()
    assert r['fechamento']['nulos_tecnicos'] == {'1': 0, '2': 0}


def test_conteudo_sha256_estavel_entre_execucoes(synth_dir, tmp_path):
    a = _build(synth_dir, tmp_path / 'a')['conteudo_sha256']
    b = _build(synth_dir, tmp_path / 'b')['conteudo_sha256']
    assert a == b and set(a) == {'secoes_2026', 'municipios_2026'}


def test_descartes_conta_secao_presente_em_um_turno_so(longo):
    g = longo.filter(~((pl.col('NR_TURNO') == '2') & (pl.col('NR_SECAO') == '5') & (pl.col('CD_MUNICIPIO') == '00003') & (pl.col('SG_UF') == 'BA')))
    d = descartes(g)
    assert int(d['secoes'].sum()) == 1 and d['NR_TURNO'][0] == '1'
    assert descartes(longo).is_empty()


def _ajusta_primeira(mz, **deltas):
    """Soma deltas à primeira zona do agregado do TSE (para simular divergências)."""
    i = pl.int_range(pl.len())
    return mz.with_columns([pl.when(i == 0).then(pl.col(c) + d).otherwise(pl.col(c)) for c, d in deltas.items()])


def test_crosscheck_fecha_no_sintetico(synth_dir, longo):
    ruins, tecnicos = crosscheck(longo, load_munzona(synth_dir, 2026, {'1', '2'}))
    assert not any(ruins.values()) and tecnicos == {'1': 0, '2': 0}


def test_nulos_tecnicos_reclassificam_validos_sem_falhar(synth_dir, longo):
    mz = _ajusta_primeira(load_munzona(synth_dir, 2026, {'1', '2'}), QT_TOTAL_VOTOS_VALIDOS=-7, QT_VOTOS_NULOS_TECNICOS=7,
                          QT_TOTAL_VOTOS_NULOS=7)
    ruins, tecnicos = crosscheck(longo, mz)
    assert not any(ruins.values()) and tecnicos == {'1': 7, '2': 0}


def test_crosscheck_detecta_voto_a_menos_sem_explicacao(synth_dir, longo):
    mz = _ajusta_primeira(load_munzona(synth_dir, 2026, {'1', '2'}), QT_TOTAL_VOTOS_VALIDOS=-1)
    ruins, _ = crosscheck(longo, mz)
    assert ruins['válidos != nominais − nulos técnicos'] == 1


def test_crosscheck_zona_sem_par(synth_dir, longo):
    mz = load_munzona(synth_dir, 2026, {'1', '2'}).slice(1)
    ruins, _ = crosscheck(longo, mz)
    assert ruins['zonas sem par (só numa das fontes)'] == 1


def test_build_2026_via_cli_exige_prereg(synth_dir, tmp_path, monkeypatch):
    monkeypatch.setattr('auditoria.prereg.ROOT', tmp_path)
    with pytest.raises(SystemExit, match='prereg-v1'):
        cli.main(['build', '--dir', str(synth_dir), '--out', str(tmp_path / 'o'),
                  '--private-dir', str(tmp_path / 'p'), '--year', '2026'])
    assert not (tmp_path / 'p').exists()


def test_build_via_cli_grava_run_com_conteudo(synth_dir, tmp_path):
    cli.main(['build', '--dir', str(synth_dir), '--out', str(tmp_path / 'o'),
              '--private-dir', str(tmp_path / 'p'), '--year', '2022', '--sem-prereg'])
    r = json.loads((tmp_path / 'o' / 'run_build_2022.json').read_text())
    assert set(r['conteudo_sha256']) == {'secoes_2022', 'municipios_2022'}
    assert 'secoes_2022.parquet' not in r['saidas']   # privado: só o hash de conteúdo é registrado


def _muni(linhas):
    return pl.DataFrame(linhas, schema=['SG_UF', 'mun', 'lula1', 'secoes'], orient='row')


def test_municipio_pequeno_vira_outros_com_supressao_complementar():
    m = _muni([('AA', 'AA-1', 10, 50), ('AA', 'AA-2', 20, 2), ('AA', 'AA-3', 30, 3),
               ('BB', 'BB-1', 40, 40), ('BB', 'BB-2', 5, 1), ('BB', 'BB-3', 6, 30)])
    r = agrega_pequenos(m, k=10)
    assert r['lula1'].sum() == m['lula1'].sum() and r['secoes'].sum() == m['secoes'].sum()
    assert (r['secoes'] >= 10).all()                                        # nenhuma linha equivale a poucas seções
    assert ((r['municipios_agregados'] == 0) | (r['municipios_agregados'] >= 2)).all()   # OUTROS nunca é um município só
    assert 'AA-OUTROS' in set(r['mun']) and 'BB-OUTROS' in set(r['mun'])
    assert 'BB-2' not in set(r['mun'])


def test_exterior_vira_uma_linha_so():
    m = _muni([('ZZ', 'ZZ-1', 1, 1), ('ZZ', 'ZZ-2', 2, 40), ('ZZ', 'ZZ-3', 3, 2), ('SP', 'SP-1', 9, 90)])
    r = agrega_pequenos(m, k=10)
    z = r.filter(pl.col('SG_UF') == 'ZZ')
    assert list(z['mun']) == ['ZZ-EXTERIOR'] and z['municipios_agregados'][0] == 3 and z['secoes'][0] == 43


def test_descartes_publicados_so_por_turno_sem_uf():
    d = pl.DataFrame({'SG_UF': ['ZZ', 'SP'], 'NR_TURNO': ['2', '2'], 'secoes': [1, 3], 'aptos': [718, 900],
                      'comparecimento': [253, 700], 'validos': [248, 680], 'lula': [1, 2], 'flavio': [3, 4]})
    r = agrega_descartes(d)
    assert 'SG_UF' not in r.columns and r['secoes'][0] == 4 and r['lula'][0] == 3


def test_build_nao_grava_nada_se_a_particao_falha(synth_dir, tmp_path, monkeypatch):
    monkeypatch.setattr('auditoria.build.descartes', lambda g: descartes_falso)
    with pytest.raises(SystemExit, match='nada foi gravado'):
        _build(synth_dir, tmp_path)
    assert not (tmp_path / 'derived').exists() and not (tmp_path / 'private').exists()


def test_turno_unico_gera_so_parquet(synth_dir, tmp_path):
    import shutil, io, zipfile
    for n in ('votacao_secao_2026_BR.zip', 'detalhe_votacao_secao_2026.zip', 'detalhe_votacao_munzona_2026.zip'):
        member = n.replace('.zip', '_BR.csv') if 'secao_2026.zip' not in n else n.replace('.zip', '_BR.csv')
        with zipfile.ZipFile(synth_dir / n) as z:
            nome = [i for i in z.namelist() if i.endswith('.csv')][0]
            df = pl.read_csv(io.BytesIO(z.read(nome)), separator=';', encoding='utf8-lossy', infer_schema=False)
        with zipfile.ZipFile(tmp_path / n, 'w') as z:
            z.writestr(nome, df.filter(pl.col('NR_TURNO') == '1').write_csv(separator=';').encode('latin1'))
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        r = build(tmp_path, tmp_path / 'o', tmp_path / 'p', 2026, exige=False)
    assert (tmp_path / 'p' / 'secoes_2026.parquet').exists() and r['arquivos'] == []


def test_munzona_com_turno_a_mais_nao_entra(synth_dir, longo):
    mz = load_munzona(synth_dir, 2026, {'1'})
    assert set(mz['NR_TURNO']) == {'1'}
    ruins, _ = crosscheck(longo.filter(pl.col('NR_TURNO') == '1'), mz)
    assert not any(ruins.values())


def test_munzona_ausente_com_manifesto_para_o_pipeline(synth_dir, tmp_path):
    import shutil
    for n in ('votacao_secao_2026_BR.zip', 'detalhe_votacao_secao_2026.zip'):
        shutil.copy(synth_dir / n, tmp_path / n)
    (tmp_path / 'MANIFEST.json').write_text('{}')
    from auditoria.verify import fechamento
    g = load_sections(tmp_path, 2026, UFS)
    with pytest.raises(SystemExit, match='obrigatória'):
        fechamento(tmp_path, 2026, g)


def test_sem_prereg_recusado_com_dados_reais(synth_dir, tmp_path):
    (tmp_path / 'MANIFEST.json').write_text('{}')
    with pytest.raises(SystemExit):
        cli.main(['build', '--dir', str(tmp_path), '--out', str(tmp_path / 'o'),
                  '--private-dir', str(tmp_path / 'p'), '--year', '2022', '--sem-prereg'])
