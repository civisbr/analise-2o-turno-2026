"""Concentração descritiva do 2º turno na base municipal publicável."""
import argparse
import csv
import io
import json
from pathlib import Path
import zipfile

from .runinfo import _sha, confere_insumos


def candidato(ano, coluna):
    return 'Lula' if coluna == 'lula' else ('Jair Bolsonaro' if str(ano) == '2022' else 'Flávio Bolsonaro')


def nomes_municipios(raw, out):
    """Extrai apenas o cadastro municipal dos arquivos já fechados pelo pipeline."""
    raw, out = Path(raw), Path(out)
    confere_insumos(raw)
    nomes = {}
    fontes = {}
    for ano in (2022, 2026):
        arq = raw / f'detalhe_votacao_munzona_{ano}.zip'
        sha = _sha(arq)
        fontes[arq.name] = sha
        with zipfile.ZipFile(arq) as z:
            with io.TextIOWrapper(z.open(f'detalhe_votacao_munzona_{ano}_BR.csv'), encoding='latin1') as f:
                for r in csv.DictReader(f, delimiter=';'):
                    if r['SG_UF'] == 'ZZ' or r['CD_CARGO'] != '1':
                        continue
                    chave = (ano, f'{r["SG_UF"]}-{int(r["CD_MUNICIPIO"])}')
                    nome = r['NM_MUNICIPIO']
                    if chave in nomes and nomes[chave] != nome:
                        raise ValueError(f'Nome municipal conflitante: {chave}')
                    nomes[chave] = nome
    out.mkdir(parents=True, exist_ok=True)
    destino = out / 'nomes_municipios.csv'
    with destino.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['ano', 'mun', 'nome'])
        w.writerows((ano, mun, nome) for (ano, mun), nome in sorted(nomes.items()))
    (out / 'fontes_nomes_municipios.json').write_text(json.dumps({
        'fontes_sha256': fontes, 'saida_sha256': _sha(destino),
        'origem': 'TSE, detalhe_votacao_munzona, membro BR, cargo Presidente; cadastro por ano e código TSE',
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def concentracao(derived):
    d = Path(derived)
    with (d / 'nomes_municipios.csv').open(encoding='utf-8') as f:
        nomes = {(r['ano'], r['mun']): r['nome'] for r in csv.DictReader(f)}
    anos, resumo = {}, {}
    for ano in ('2022', '2026'):
        with (d / f'municipios_{ano}.csv').open(encoding='utf-8') as f:
            linhas = list(csv.DictReader(f))
        cidades = {}
        for r in linhas:
            if r['SG_UF'] == 'ZZ' or int(r['municipios_agregados']) or r['mun'].endswith('-OUTROS'):
                continue
            validos = int(r['valid2'])
            if validos <= 0:
                continue
            votos = {c: int(r[c + '2']) for c in ('lula', 'flavio')}
            if min(votos.values()) < 0 or sum(votos.values()) != validos:
                raise ValueError(f'{ano}, {r["mun"]}: votos dos finalistas não fecham com os válidos')
            c = max(votos, key=votos.get)
            nome = nomes.get((ano, r['mun']))
            if nome is None:
                raise ValueError(f'Nome municipal ausente: {ano}, {r["mun"]}')
            cidades[r['mun']] = {'nome': nome, 'uf': r['SG_UF'], 'candidato': candidato(ano, c),
                                 'votos': votos[c], 'validos': validos, 'pct': votos[c] / validos * 100,
                                 'acima_90': votos[c] * 10 > validos * 9}
        anos[ano] = cidades
        resumo[ano] = {'avaliados': len(cidades), 'acima_90': sum(r['acima_90'] for r in cidades.values()),
                       'por_candidato': {candidato(ano, c): sum(r['acima_90'] and r['candidato'] == candidato(ano, c)
                                                             for r in cidades.values()) for c in ('lula', 'flavio')}}
    chaves = {k for cidades in anos.values() for k, r in cidades.items() if r['acima_90']}
    linhas = []
    for mun in chaves:
        a, b = anos['2026'].get(mun), anos['2022'].get(mun)
        status = ('Sem comparação' if a is None or b is None else
                  'Nos dois anos' if a['acima_90'] and b['acima_90'] else
                  'Só em 2026' if a['acima_90'] else 'Só em 2022')
        linhas.append({'mun': mun, 'nome': (a or b)['nome'], 'uf': (a or b)['uf'],
                       '2026': a, '2022': b, 'situacao': status})
    linhas.sort(key=lambda r: (not bool(r['2026'] and r['2026']['acima_90']),
                               -(r['2026'] or r['2022'])['pct'], r['uf'], r['nome'], r['mun']))
    return {'resumo': resumo, 'linhas': linhas,
            'nos_dois_anos': sum(r['situacao'] == 'Nos dois anos' for r in linhas)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Extrai nomes municipais do cadastro do TSE, sem votos por seção.')
    p.add_argument('--raw', default='data/raw'); p.add_argument('--out', default='data/derived')
    a = p.parse_args()
    nomes_municipios(a.raw, a.out)
