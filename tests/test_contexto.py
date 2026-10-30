import csv
import json
import zipfile

import pytest

from auditoria.contexto import analisar_contexto, correlacao, ideologias, normaliza, prefeitos
from auditoria.runinfo import _sha


def test_classificacao_publicada_aliases_e_sem_inventar_siglas():
    h = '<table><tr><th>Partido</th><th>2018</th><th>2022</th></tr>'
    for partido, nota, categoria in [('PT', '2.68', 'esquerda'), ('REP', '8.33', 'extrema direita'),
                                     ('SDD', '6.01', 'centro-direita'), ('PSD', '6.94', 'direita')]:
        h += f'<tr><td>{partido}</td><td>1</td><td>{nota}</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>{categoria}</td></tr>'
    r = ideologias(h + '</table>')
    assert r['PT']['bloco'] == 'Esquerda'
    assert r['REPUBLICANOS']['bloco'] == 'Direita'
    assert r['SOLIDARIEDADE']['categoria'] == 'centro-direita'
    assert r['PSD']['categoria'] == 'direita'  # usa categoria publicada, não reclassifica a média
    assert 'PRD' not in r
    assert normaliza('São Braz do Piauí') == 'SAOBRAZDOPIAUI'


def test_spearman_com_empates_faltantes_e_constantes():
    r = correlacao([{'x': 1, 'pct_lider': 60}, {'x': 2, 'pct_lider': 80}, {'x': 2, 'pct_lider': 80},
                    {'x': 3, 'pct_lider': 90}, {'x': None, 'pct_lider': 50}], 'x')
    assert r['n'] == 4 and r['rho'] == pytest.approx(1)
    assert correlacao([{'x': 1, 'pct_lider': y} for y in (60, 70, 90)], 'x')['rho'] is None


def fixture_contexto(d):
    dados = {'municipios': [
        {'mun': 'BA-1', 'nome': 'Cidade A', 'ibge': '2900001', 'idhm_2010': .5, 'pib_pc_2023': 10000, 'pib_2023': 1000000,
         'prefeito_2024': {'nome': 'Pessoa A', 'partido': 'PT'}, 'ideologia': {'bloco': 'Esquerda'}},
        {'mun': 'PE-1', 'nome': 'Cidade A', 'ibge': None, 'idhm_2010': None, 'pib_pc_2023': None, 'pib_2023': None,
         'prefeito_2024': None, 'ideologia': None},
        {'mun': 'BA-2', 'nome': 'Cidade B', 'ibge': '2900002', 'idhm_2010': .8, 'pib_pc_2023': 50000, 'pib_2023': 3000000,
         'prefeito_2024': {'nome': 'Pessoa B', 'partido': 'MDB'}, 'ideologia': {'bloco': 'Direita'}},
    ], 'ideologias': {}}
    nomes = d / 'nomes_municipios.csv'
    nomes.write_text('ano,mun,nome\n2026,BA-1,Cidade A\n2026,PE-1,Cidade A\n2026,BA-2,Cidade B\n')
    f = d / 'contexto_municipal.json'; f.write_text(json.dumps(dados))
    (d / 'fontes_contexto.json').write_text(json.dumps({
        'saida_sha256': _sha(f), 'nomes_municipios_sha256': _sha(nomes)}))
    (d / 'prefeituras_verificadas.json').write_text('{}')
    for ano in ('2022', '2026'):
        with (d / f'municipios_{ano}.csv').open('w') as f:
            w = csv.writer(f); w.writerow(['SG_UF', 'mun', 'lula2', 'flavio2', 'valid2', 'municipios_agregados'])
            w.writerows([['BA', 'BA-1', 950, 50, 1000, 0], ['PE', 'PE-1', 10, 990, 1000, 0],
                         ['BA', 'BA-2', 800 if ano == '2026' else 950, 200 if ano == '2026' else 50, 1000, 0],
                         ['BA', 'BA-OUTROS', 999, 1, 1000, 2]])
    return d


def test_contexto_cortes_dados_ausentes_blocos_e_ano_politico(tmp_path):
    r = analisar_contexto(fixture_contexto(tmp_path))
    assert set(r['anos']) == {'2026'}  # não atribui o governo eleito em 2024 a 2022
    a = r['anos']['2026']
    assert a['cobertura'] == {'avaliados': 3, 'sem_ibge': 1, 'sem_prefeito_2024': 1}
    assert a['grupos'][0]['n'] == 2
    assert a['grupos'][0]['indicadores']['idhm_2010'] == {'n': 1, 'mediana': .5}
    assert a['grupos'][1]['indicadores']['pib_pc_2023']['mediana'] == 50000
    blocos = {x['bloco']: x for x in a['blocos']}
    assert blocos['Direita']['pct'] == 0 and blocos['Esquerda']['pct'] == 100
    assert blocos['Sem classificação']['acima_90'] == 1
    assert blocos['Centro']['pct'] is None
    cidades = {x['mun']: x for x in a['linhas']}
    assert cidades['PE-1']['candidato_2022'] == 'Jair Bolsonaro'
    assert cidades['BA-2']['acima_90_2022'] and not cidades['BA-2']['acima_90']
    assert cidades['PE-1']['ibge'] is None  # não associa cidade homônima de outra UF
    json.dumps(r, allow_nan=False)


def test_contexto_recusa_snapshot_modificado(tmp_path):
    fixture_contexto(tmp_path)
    f = tmp_path / 'contexto_municipal.json'; f.write_text(f.read_text() + ' ')
    with pytest.raises(ValueError, match='snapshot'):
        analisar_contexto(tmp_path)


def test_contexto_recusa_cadastro_diferente_do_snapshot(tmp_path):
    fixture_contexto(tmp_path)
    f = tmp_path / 'nomes_municipios.csv'
    f.write_text(f.read_text().replace('Cidade A', 'Outro nome'))
    with pytest.raises(ValueError, match='Cadastro municipal difere'):
        analisar_contexto(tmp_path)


def test_eleitos_filtra_cargo_situacao_e_preserva_uf(tmp_path):
    texto = ('CD_CARGO;DS_SIT_TOT_TURNO;CD_TIPO_ELEICAO;SG_UF;SG_UE;NM_CANDIDATO;NM_URNA_CANDIDATO;SG_PARTIDO;DT_ELEICAO;DT_GERACAO\n'
             '11;ELEITO;2;BA;0001;Pessoa A;A;PT;06/10/2024;29/10/2026\n'
             '11;NÃO ELEITO;2;BA;0001;Pessoa B;B;MDB;06/10/2024;29/10/2026\n'
             '12;ELEITO;2;BA;0001;Pessoa C;C;PT;06/10/2024;29/10/2026\n'
             '11;ELEITO;2;PE;0001;Pessoa D;D;MDB;06/10/2024;29/10/2026\n')
    p = tmp_path / 'cand.zip'
    with zipfile.ZipFile(p, 'w') as z: z.writestr('consulta_cand_2024_BRASIL.csv', texto.encode('latin1'))
    r = prefeitos(p)
    assert set(r) == {'BA-1', 'PE-1'} and r['BA-1']['nome'] == 'Pessoa A'
