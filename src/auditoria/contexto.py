"""Contextualização municipal descritiva, com fontes e anos explícitos."""
import argparse
import csv
import datetime
import gzip
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import statistics
import unicodedata
import urllib.request
import zipfile

import polars as pl

from .concentracao import candidato
from .runinfo import _sha

FONTES = {
    'municipios_ibge.json': 'https://servicodados.ibge.gov.br/api/v1/localidades/municipios',
    'idhm_ipea.json': "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_IDHM')",
    'pib_2023.json': 'https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2023',
    'candidatos_2024.zip': 'https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip',
    'ideologia.html': 'https://www.scielo.br/j/op/a/hv8GBg9hfCCZLwcWktfYhtC/?lang=pt',
}
PIBPC = 'https://servicodados.ibge.gov.br/api/v1/pesquisas/38/periodos/2023/indicadores/47001/resultados/'
ALIASES_PARTIDOS = {'SDD': 'SOLIDARIEDADE', 'CDD': 'CIDADANIA', 'PROGRE': 'PP', 'REP': 'REPUBLICANOS', 'PATRI': 'PATRIOTA'}


def normaliza(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s.upper()) if c.isalnum())


def baixar(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        b = r.read()
    return gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b


class Tabelas(HTMLParser):
    def __init__(self):
        super().__init__(); self.linhas = []; self.linha = []; self.celula = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.linha = []
        if tag in ('td', 'th'): self.celula = []

    def handle_data(self, data):
        if self.celula is not None: self.celula.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.celula is not None:
            self.linha.append(' '.join(''.join(self.celula).split())); self.celula = None
        if tag == 'tr' and self.linha: self.linhas.append(self.linha)


def ideologias(texto):
    p = Tabelas(); p.feed(texto)
    res = {}
    for row in p.linhas:
        if len(row) != 9 or row[0] == 'Partido': continue
        categoria = row[-1]
        if categoria not in ('extrema esquerda', 'esquerda', 'centro-esquerda', 'centro',
                             'centro-direita', 'direita', 'extrema direita'): continue
        sigla = normaliza(ALIASES_PARTIDOS.get(row[0], row[0]))
        res[sigla] = {'categoria': categoria, 'media_2022': float(row[2]),
                     'bloco': 'Esquerda' if 'esquerda' in categoria else 'Direita' if 'direita' in categoria else 'Centro'}
    if not res: raise ValueError('Tabela de ideologia ausente na fonte')
    return res


def prefeitos(zippath):
    res = {}
    with zipfile.ZipFile(zippath) as z:
        with io.TextIOWrapper(z.open('consulta_cand_2024_BRASIL.csv'), encoding='latin1') as f:
            for r in csv.DictReader(f, delimiter=';'):
                if r['CD_CARGO'] != '11' or r['DS_SIT_TOT_TURNO'] != 'ELEITO' or r['CD_TIPO_ELEICAO'] != '2': continue
                chave = r['SG_UF'] + '-' + str(int(r['SG_UE']))
                dado = {'nome': r['NM_CANDIDATO'], 'nome_urna': r['NM_URNA_CANDIDATO'], 'partido': r['SG_PARTIDO'],
                        'eleicao': r['DT_ELEICAO'], 'geracao_fonte': r['DT_GERACAO']}
                if chave in res and res[chave] != dado: raise ValueError(f'Mais de um prefeito eleito: {chave}')
                res[chave] = dado
    return res


def preparar(raw, derived):
    """Congela somente variáveis municipais públicas. Cache externo não é publicado."""
    raw, d = Path(raw), Path(derived); raw.mkdir(parents=True, exist_ok=True)
    for nome, url in FONTES.items():
        if not (raw / nome).exists(): (raw / nome).write_bytes(baixar(url))
    locais = json.loads((raw / 'municipios_ibge.json').read_text())
    if not (raw / 'pibpc_2023.json').exists():
        codigos = [str(r['id']) for r in locais]; valores = []
        for i in range(0, len(codigos), 150):
            valores += json.loads(baixar(PIBPC + '|'.join(codigos[i:i + 150])))[0]['res']
        (raw / 'pibpc_2023.json').write_text(json.dumps(valores, ensure_ascii=False))
    lookup = {}
    for r in locais:
        uf = ((r.get('microrregiao') or {}).get('mesorregiao', {}).get('UF') or
              r['regiao-imediata']['regiao-intermediaria']['UF'])['sigla']
        k = (uf, normaliza(r['nome']))
        if k in lookup: raise ValueError(f'Nome municipal ambíguo no IBGE: {k}')
        lookup[k] = str(r['id'])
    idhm = {str(r['TERCODIGO']): r['VALVALOR'] for r in json.loads((raw / 'idhm_ipea.json').read_text())['value']
            if r['NIVNOME'] == 'Municípios' and r['VALDATA'].startswith('2010-')}
    pib = {r['D1C']: float(r['V']) * 1000 for r in json.loads((raw / 'pib_2023.json').read_text())[1:]
           if r['V'] not in ('-', '..', '...', 'X')}
    pc = {r['localidade']: float(r['res']['2023']) for r in json.loads((raw / 'pibpc_2023.json').read_text())
          if r['res'].get('2023') not in (None, '-', '..', '...', 'X')}
    ideol = ideologias((raw / 'ideologia.html').read_text()); eleitos = prefeitos(raw / 'candidatos_2024.zip')
    nomes = {}
    with (d / 'nomes_municipios.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f): nomes[r['mun']] = r['nome']  # cadastro de 2026 prevalece
    registros = []
    for mun, nome in sorted(nomes.items()):
        ibge = lookup.get((mun[:2], normaliza(nome)))
        prefeito = eleitos.get(mun)
        classe = ideol.get(normaliza(prefeito['partido'])) if prefeito else None
        registros.append({'mun': mun, 'nome': nome, 'ibge': ibge,
                          'idhm_2010': idhm.get(ibge), 'pib_2023': pib.get(ibge),
                          'pib_pc_2023': pc.get(ibge[:6]) if ibge else None,
                          'prefeito_2024': prefeito, 'ideologia': classe})
    dados = {'municipios': registros, 'ideologias': ideol}
    destino = d / 'contexto_municipal.json'
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    fontes = {n: {'url': u, 'sha256': _sha(raw / n)} for n, u in FONTES.items()}
    fontes['pibpc_2023.json'] = {'url_base': PIBPC, 'consulta': 'códigos IBGE em lotes de 150 separados por |; concatenação de res',
                               'sha256': _sha(raw / 'pibpc_2023.json')}
    manifesto = {'coletado_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                 'fontes': fontes, 'nomes_municipios_sha256': _sha(d / 'nomes_municipios.csv'),
                 'saida_sha256': _sha(destino), 'sem_correspondencia_ibge': [r['mun'] for r in registros if r['ibge'] is None]}
    (d / 'fontes_contexto.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + '\n')


def correlacao(linhas, indicador):
    pares = [(r[indicador], r['pct_lider']) for r in linhas if r[indicador] is not None]
    if len(pares) < 3 or len({r[0] for r in pares}) < 2 or len({r[1] for r in pares}) < 2:
        return {'n': len(pares), 'rho': None}
    rho = pl.DataFrame(pares, schema=['x', 'y'], orient='row').select(pl.corr('x', 'y', method='spearman')).item()
    return {'n': len(pares), 'rho': rho if math.isfinite(rho) else None}


def analisar_contexto(derived):
    d = Path(derived)
    fontes = json.loads((d / 'fontes_contexto.json').read_text())
    if fontes['saida_sha256'] != _sha(d / 'contexto_municipal.json'):
        raise ValueError('Contexto municipal difere do snapshot registrado')
    if fontes.get('nomes_municipios_sha256') != _sha(d / 'nomes_municipios.csv'):
        raise ValueError('Cadastro municipal difere do usado no contexto: gere o contexto novamente')
    dados = json.loads((d / 'contexto_municipal.json').read_text())
    contexto = {r['mun']: r for r in dados['municipios']}
    verificacoes = json.loads((d / 'prefeituras_verificadas.json').read_text())
    anos = {}
    with (d / 'municipios_2022.csv').open() as f:
        historico = {r['mun']: r for r in csv.DictReader(f)
                     if r['SG_UF'] != 'ZZ' and int(r['municipios_agregados']) == 0 and int(r['valid2']) > 0}
    # O contexto político é da eleição municipal de 2024; não é atribuído a 2022.
    for ano in ('2026',):
        linhas = []
        with (d / f'municipios_{ano}.csv').open() as f:
            for r in csv.DictReader(f):
                if r['SG_UF'] == 'ZZ' or int(r['municipios_agregados']) or int(r['valid2']) <= 0: continue
                c = contexto[r['mun']]
                voto = {k: int(r[k + '2']) for k in ('lula', 'flavio')}; lider = max(voto, key=voto.get)
                validos = int(r['valid2'])
                if min(voto.values()) < 0 or sum(voto.values()) != validos: raise ValueError(f'Votos municipais inconsistentes: {r["mun"]}')
                h = historico.get(r['mun'])
                h_votos = max(int(h['lula2']), int(h['flavio2'])) if h else None
                linhas.append({**c, 'uf': r['SG_UF'], 'candidato': candidato(ano, lider),
                               'pct_lider': voto[lider] / validos * 100, 'acima_90': voto[lider] * 10 > validos * 9,
                               'pct_lider_2022': h_votos / int(h['valid2']) * 100 if h else None,
                               'candidato_2022': candidato(2022, 'lula' if int(h['lula2']) >= int(h['flavio2']) else 'flavio') if h else None,
                               'acima_90_2022': h_votos * 10 > int(h['valid2']) * 9 if h else None,
                               'verificacao_prefeitura': verificacoes.get(r['mun'])})
        grupos = []
        for acima, rotulo in ((True, 'Acima de 90%'), (False, 'Até 90%')):
            g = [r for r in linhas if r['acima_90'] == acima]
            indicadores = {}
            for k in ('idhm_2010', 'pib_pc_2023', 'pib_2023'):
                vs = [r[k] for r in g if r[k] is not None]
                indicadores[k] = {'n': len(vs), 'mediana': statistics.median(vs) if vs else None}
            grupos.append({'rotulo': rotulo, 'n': len(g), 'indicadores': indicadores})
        blocos = []
        for bloco in ('Esquerda', 'Centro', 'Direita', 'Sem classificação'):
            g = [r for r in linhas if (r['ideologia'] or {}).get('bloco', 'Sem classificação') == bloco]
            n = sum(r['acima_90'] for r in g)
            blocos.append({'bloco': bloco, 'municipios': len(g), 'acima_90': n, 'pct': n / len(g) * 100 if g else None})
        anos[ano] = {'grupos': grupos, 'blocos': blocos,
                     'correlacoes': {k: correlacao(linhas, k) for k in ('idhm_2010', 'pib_pc_2023')},
                     'cobertura': {'avaliados': len(linhas), 'sem_ibge': sum(r['ibge'] is None for r in linhas),
                                   'sem_prefeito_2024': sum(r['prefeito_2024'] is None for r in linhas)},
                     'linhas': sorted(linhas, key=lambda r: (-r['pct_lider'], r['mun']))}
    return {'anos': anos, 'ideologias': dados['ideologias'], 'fontes': fontes}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Prepara contexto municipal a partir de snapshots oficiais e classificação acadêmica.')
    p.add_argument('--raw', default='data/external'); p.add_argument('--derived', default='data/derived')
    a = p.parse_args(); preparar(a.raw, a.derived)
