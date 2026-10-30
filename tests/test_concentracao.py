import csv
import zipfile

import pytest

from auditoria.concentracao import concentracao, nomes_municipios


def base(tmp_path):
    # Exatamente 90%; acima do corte mas arredonda a 90,000%; troca do líder;
    # cidade ausente em 2022; cidade histórica; grupos/exterior; zero válidos.
    rows = {
        '2022': [('BA-1', 900, 1000, 0), ('BA-2', 910, 1000, 0), ('BA-3', 50, 1000, 0),
                 ('BA-5', 950, 1000, 0), ('BA-OUTROS', 950, 1000, 2), ('ZZ-1', 950, 1000, 0), ('BA-6', 0, 0, 0)],
        '2026': [('BA-1', 900, 1000, 0), ('BA-2', 900001, 1000001, 0), ('BA-3', 950, 1000, 0),
                 ('BA-4', 950, 1000, 0), ('BA-5', 800, 1000, 0), ('BA-OUTROS', 950, 1000, 2), ('ZZ-1', 950, 1000, 0), ('BA-6', 0, 0, 0)],
    }
    with (tmp_path / 'nomes_municipios.csv').open('w') as f:
        w = csv.writer(f); w.writerow(['ano', 'mun', 'nome'])
        for ano, rs in rows.items():
            w.writerows((ano, mun, 'São Teste ' + mun) for mun, *_ in rs)
    for ano, rs in rows.items():
        with (tmp_path / f'municipios_{ano}.csv').open('w') as f:
            w = csv.writer(f); w.writerow(['SG_UF', 'mun', 'lula2', 'flavio2', 'valid2', 'municipios_agregados'])
            w.writerows((mun[:2], mun, lula, valid - lula, valid, grupo) for mun, lula, valid, grupo in rs)
    return tmp_path


def test_corte_exato_comparacao_e_recorte(tmp_path):
    r = concentracao(base(tmp_path))
    cidades = {c['mun']: c for c in r['linhas']}
    assert set(cidades) == {'BA-2', 'BA-3', 'BA-4', 'BA-5'}
    assert cidades['BA-2']['2026']['acima_90'] is True
    assert round(cidades['BA-2']['2026']['pct'], 3) == 90.0
    assert cidades['BA-3']['2022']['candidato'] == 'Jair Bolsonaro'
    assert cidades['BA-3']['2026']['candidato'] == 'Lula'
    assert cidades['BA-3']['situacao'] == 'Nos dois anos'
    assert cidades['BA-4']['2022'] is None and cidades['BA-4']['situacao'] == 'Sem comparação'
    assert cidades['BA-5']['situacao'] == 'Só em 2022'
    assert r['nos_dois_anos'] == 2
    assert r['resumo']['2026'] == {'avaliados': 5, 'acima_90': 3, 'por_candidato': {'Lula': 3, 'Flávio Bolsonaro': 0}}
    assert r['resumo']['2022']['por_candidato']['Jair Bolsonaro'] == 1
    assert r == concentracao(tmp_path)


def test_nome_ausente_nao_inventa_cidade(tmp_path):
    d = base(tmp_path)
    (d / 'nomes_municipios.csv').write_text('ano,mun,nome\n')
    with pytest.raises(ValueError, match='Nome municipal ausente'):
        concentracao(d)


def test_extracao_de_nomes_preserva_acentos_e_normaliza_codigo(tmp_path):
    for ano in (2022, 2026):
        with zipfile.ZipFile(tmp_path / f'detalhe_votacao_munzona_{ano}.zip', 'w') as z:
            z.writestr(f'detalhe_votacao_munzona_{ano}_BR.csv',
                       'SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;CD_CARGO\nBA;00001;SÃO TESTE;1\n'.encode('latin1'))
    nomes_municipios(tmp_path, tmp_path / 'out')
    assert (tmp_path / 'out/nomes_municipios.csv').read_text() == 'ano,mun,nome\n2022,BA-1,SÃO TESTE\n2026,BA-1,SÃO TESTE\n'
