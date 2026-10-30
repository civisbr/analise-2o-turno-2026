"""painel.json da página: lê resultados e snapshots municipais rastreáveis. Nenhum número é digitado à mão
(regra 5). Texto aqui é descritivo; interpretação fica fora da página até a revisão externa."""
import html
import json
import pathlib
from types import SimpleNamespace

import polars as pl

from .runinfo import _sha
from .concentracao import candidato, concentracao
from .contexto import analisar_contexto


def _br(x, casas=0, sinal=False):
    s = f'{abs(x):,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('+' if x > 0 else '−' if x < 0 else '') + s if sinal else ('−' if x < 0 else '') + s


def _soma(q1_ano):
    """Brasil e exterior juntos, para bater com os totais do TSE (o exterior segue separado no JSON de origem)."""
    blocos = [q1_ano['nacional']] + ([q1_ano['exterior']] if 'exterior' in q1_ano else [])
    return {k: sum(b[k] for b in blocos) for k in ('pool', 'dvalid', 'dL', 'dF', 'dcomparecimento', 'queda_brancos_nulos')}


def _kpis(t1, t2):
    p = lambda a, b: round(a / b * 100, 2)
    pu = lambda a, b: a / b * 100    # sem arredondar, para os deltas
    comp1, comp2 = p(t1.comp, t1.apt), p(t2.comp, t2.apt)
    bn1 = (t1.branco + t1.nulo) / t1.comp; bn2 = (t2.branco + t2.nulo) / t2.comp
    return [
        {'id': 'comparecimento', 'rotulo': 'Comparecimento 2º turno', 'valor': comp2, 'tipo': 'pct',
         'linha2': {'valor': int(t2.comp), 'tipo': 'int', 'sufixo': 'eleitores'},
         'delta': {'valor': round(pu(t2.comp, t2.apt) - pu(t1.comp, t1.apt), 2), 'tipo': 'pp', 'sufixo': 'vs 1º turno'}, 'serie': None, 'cor': 'verde'},
        {'id': 'validos', 'rotulo': 'Votos válidos', 'valor': int(t2.valid), 'tipo': 'int',
         'linha2': {'valor': int(t2.valid - t1.valid), 'tipo': 'sint', 'sufixo': 'vs 1º turno'},
         'delta': {'valor': round((t2.valid / t1.valid - 1) * 100, 2), 'tipo': 'pctsinal'}, 'serie': None, 'cor': 'verde'},
        {'id': 'lula', 'rotulo': 'Lula', 'ponto': 'verde', 'valor': int(t2.lula), 'tipo': 'int',
         'linha2': {'valor': p(t2.lula, t2.valid), 'tipo': 'pct', 'sufixo': 'dos válidos'},
         'delta': {'valor': int(t2.lula - t1.lula), 'tipo': 'sint', 'sufixo': 'vs 1º turno'}, 'serie': None, 'cor': 'verde'},
        {'id': 'flavio', 'rotulo': 'Flávio Bolsonaro', 'ponto': 'azul', 'valor': int(t2.flavio), 'tipo': 'int',
         'linha2': {'valor': p(t2.flavio, t2.valid), 'tipo': 'pct', 'sufixo': 'dos válidos'},
         'delta': {'valor': int(t2.flavio - t1.flavio), 'tipo': 'sint', 'sufixo': 'vs 1º turno'}, 'serie': None, 'cor': 'azul'},
        {'id': 'abstencao', 'rotulo': 'Abstenção', 'valor': p(t2.abstencao, t2.apt), 'tipo': 'pct',
         'linha2': {'valor': int(t2.abstencao), 'tipo': 'int', 'sufixo': 'eleitores'},
         'delta': {'valor': round(pu(t2.abstencao, t2.apt) - pu(t1.abstencao, t1.apt), 2), 'tipo': 'pp', 'sufixo': 'vs 1º turno'},
         'serie': None, 'cor': 'amarelo'},
        {'id': 'brancos_nulos', 'rotulo': 'Brancos / Nulos', 'valor': [p(t2.branco, t2.comp), p(t2.nulo, t2.comp)], 'tipo': 'par_pct',
         'linha2': {'valor': [int(t2.branco), int(t2.nulo)], 'tipo': 'par_int'},
         'delta': {'texto': ('queda' if bn2 < bn1 else 'alta' if bn2 > bn1 else 'estável') + ' vs 1º turno'}, 'serie': None, 'cor': 'roxo'},
    ]


def _ganho(g):
    total = g['pool'] + g['dcomparecimento'] + g['queda_brancos_nulos']
    if total <= 0:
        raise SystemExit('ganho conjunto não positivo: decomposição inconsistente, painel não gerado')
    partes = [('terceira_via', 'Terceira via', g['pool'], 'roxo'),
              ('comparecimento', 'Mais comparecimento', g['dcomparecimento'], 'azul'),
              ('brancos_nulos', 'Queda de brancos/nulos', g['queda_brancos_nulos'], 'amarelo')]
    return {'total': int(total), 'partes': [{'id': i, 'rotulo': r, 'valor': int(v), 'pct': round(v / total * 100, 1), 'cor': c}
                                            for i, r, v, c in partes]}


def _divisao(g26, g22):
    def ano(a, g):
        if g['dL'] < 0 or g['dF'] < 0 or g['dL'] + g['dF'] == 0:
            raise SystemExit(f'ganho de {a} sem divisão definida (dL={g["dL"]}, dF={g["dF"]}): painel não gerado')
        l = round(g['dL'] / (g['dL'] + g['dF']) * 100)
        return {'ano': a, 'lula': l, 'flavio': 100 - l, 'candidato_22': candidato(a, 'flavio')}
    return {'anos': [ano(2022, g22), ano(2026, g26)]}


def _atipicos(q3_26, q3_22):
    if not q3_26['testados'] or not q3_22['testados']:
        return None
    pct = lambda n, t: round(n / t * 100, 2)
    return [
        {'rotulo': '2026, sem correção', 'faixa': 'p < 0,05', 'pct': pct(q3_26['observado_p05'], q3_26['testados']), 'cor': 'azul'},
        {'rotulo': '2022, controle', 'faixa': 'p < 0,05', 'pct': pct(q3_22['observado_p05'], q3_22['testados']), 'cor': 'amarelo'},
        {'rotulo': 'Esperado por acaso', 'faixa': 'p < 0,05', 'pct': round(q3_26['esperado_p05_por_acaso'] / q3_26['testados'] * 100, 2), 'cor': 'muted'},
        {'rotulo': '2026, FDR 5%', 'faixa': 'nos dois ajustes', 'pct': pct(q3_26['sinalizados_nos_dois'], q3_26['testados']), 'cor': 'azul'},
        {'rotulo': '2022, FDR 5%', 'faixa': 'controle, nos dois ajustes', 'pct': pct(q3_22['sinalizados_nos_dois'], q3_22['testados']), 'cor': 'amarelo'},
    ]


def _coef_a(q2, nome):
    for a in q2.get('ajustes', []):
        if a['modelo'] == 'A' and a['efeito_fixo'] and not a['refit_robusto']:
            return a['coef'].get(nome)


NAO_AVALIAVEL = 'não avaliável nesta rodada.'


def _perguntas(r, g26, g22):
    q2, q3, q4, q5 = r['q2'], r['q3'], r['q4'], r['q5']; a26, a22 = '2026', '2022'
    exp = q2.get('explicado')
    veredito = 'não avaliável' if exp is None else ('sim' if exp['explicado'] else 'não')
    al, be = _coef_a(q2, 'alpha'), _coef_a(q2, 'beta')
    ic = lambda c: f'IC 95%: {_br(c["ic_dif"][0], 2, True)} a {_br(c["ic_dif"][1], 2, True)}'
    dif = lambda nome, c: (f'{nome}: {_br(c["dif"], 2, True)} ({ic(c)}).' if c else f'{nome}: {NAO_AVALIAVEL}')

    def q4_linha(ano):
        q = q4[ano]; base = f'{_br(q["com_queda_de_flavio"])} municípios com queda de {candidato(ano, "flavio")}'
        if 'comparecimento_estavel_ou_alta' not in q:
            return f'{ano}: {base}; comparecimento {NAO_AVALIAVEL}'
        return f'{ano}: {base}, {_br(q["comparecimento_estavel_ou_alta"])} sem queda de comparecimento.'
    return [
        {'id': 'Q1', 'titulo': 'De onde veio o ganho conjunto dos finalistas?', 'linhas': [
            f'2026: Lula {_br(g26["dL"], 0, True)}, Flávio {_br(g26["dF"], 0, True)} votos.',
            f'2022: Lula {_br(g22["dL"], 0, True)}, Jair Bolsonaro {_br(g22["dF"], 0, True)} votos.']},
        {'id': 'Q2', 'titulo': 'A divisão do ganho difere de 2022?', 'linhas': [
            dif('Diferença de α (2026 − 2022)', al), dif('Diferença de β (voto válido novo)', be),
            f'Explicado pelas covariáveis dos dados oficiais: {veredito}.']},
        {'id': 'Q3', 'titulo': 'Há municípios que destoam do padrão do estado?', 'linhas': [
            f'Sinalizados (FDR 5%, nos dois ajustes): {_br(q3[a26]["sinalizados_nos_dois"])} de {_br(q3[a26]["testados"])} em 2026; '
            f'{_br(q3[a22]["sinalizados_nos_dois"])} de {_br(q3[a22]["testados"])} em 2022.']},
        {'id': 'Q4', 'titulo': 'Onde o candidato nº 22 perdeu votos absolutos, o comparecimento caiu?', 'linhas': [q4_linha(a26), q4_linha(a22)]},
        {'id': 'Q5', 'titulo': 'Há excesso de seções extremas?', 'linhas': [
            f'Seções com |z| > 4: {_br(q5["fracao_" + a26] * 100, 3)}% em 2026, {_br(q5["fracao_" + a22] * 100, 3)}% em 2022; '
            f'esperado por acaso (simulação): {_br(q5["esperado_por_acaso_simulacao"] * 100, 3)}%.',
            'Conjunto atípico de seções: ' + ('sim' if q5['conjunto_atipico'] else 'não') + '.']},
        {'id': 'Q6', 'titulo': 'Seções que fecharam tarde tiveram swing diferente?', 'linhas': [
            'Não testável com dados públicos: a hora de encerramento por seção não existe nos CSV do TSE.']},
    ]


def _notas(t1, t2, g26):
    """Quadros com fontes distintas (totais do TSE x decomposição Q1, que só usa seções presentes nos dois turnos)."""
    dif = abs((t2.lula - t1.lula) - g26['dL']) + abs((t2.flavio - t1.flavio) - g26['dF'])
    if dif:
        return [f'Diferença de {_br(dif)} votos entre os totais do TSE e a decomposição: seções presentes em só um turno '
                'ficam fora da decomposição (descartes_2026.csv).']
    return []


def _fmt(tipo, v):
    if v is None:
        return '—'
    return {'int': lambda: _br(v), 'sint': lambda: _br(v, 0, True), 'pct': lambda: _br(v, 2) + '%',
            'pp': lambda: _br(v, 2, True) + ' p.p.', 'pctsinal': lambda: _br(v, 2, True) + '%',
            'par_pct': lambda: ' / '.join(_br(x, 2) + '%' for x in v),
            'par_int': lambda: ' / '.join(_br(x) for x in v)}[tipo]()


def _distribuicao(d, exige_real):
    nome = 'distribuicao_secoes.json'
    run = json.loads((d / 'run_distribuicao-secoes_2026.json').read_text(encoding='utf-8'))
    if run['saidas'].get(nome) != _sha(d / nome):
        raise SystemExit('distribuicao_secoes.json difere da rodada: rode `auditoria distribuicao-secoes` de novo')
    if exige_real and (run.get('insumos') is None or run.get('prereg_tag') is None):
        raise SystemExit('distribuição de seções sem insumos do MANIFEST.json ou sem tag prereg-v1 (dado sintético?)')
    return json.loads((d / nome).read_text(encoding='utf-8'))


def tabelas_html(p):
    """Versão sem JavaScript: as mesmas tabelas da página, a partir do painel.json já gerado."""
    e = html.escape

    def tabela(titulo, cab, linhas):
        th = ''.join(f'<th scope="col">{e(c)}</th>' for c in cab)
        tr = ''.join('<tr>' + (f'<th scope="row">{e(l[0])}</th>' + ''.join(f'<td>{e(c)}</td>' for c in l[1:])) + '</tr>' for l in linhas)
        return f'<section class="cartao"><table class="tabela"><caption>{e(titulo)}</caption><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></section>'

    def kpi(k):
        d = k['delta']; var = d['texto'] if d.get('texto') else ' '.join(x for x in (_fmt(d['tipo'], d['valor']), d.get('sufixo', '')) if x)
        l2 = k['linha2']; seg = ' '.join(x for x in (_fmt(l2['tipo'], l2['valor']), l2.get('sufixo', '')) if x)
        return (k['rotulo'], _fmt(k['tipo'], k['valor']), seg, var)
    corpos = [
        tabela('Panorama nacional', ['Indicador', 'Valor', 'Detalhe', 'Variação'], [kpi(k) for k in p['kpis']]),
        tabela('De onde veio o ganho conjunto dos finalistas', ['Origem', 'Votos', 'Participação'],
               [(x['rotulo'], _br(x['valor'], 0, True), _br(x['pct'], 1) + '%') for x in p['ganho']['partes']]
               + [('Total', _br(p['ganho']['total'], 0, True), '')]),
        tabela('Divisão do ganho entre os finalistas', ['Ano', 'Lula', 'Candidato nº 22', 'Parcela do ganho'],
               [(str(a['ano']), f'{a["lula"]}%', a['candidato_22'], f'{a["flavio"]}%') for a in p['divisao']['anos']]),
    ]
    if p['atipicos']:   # 1 casa decimal nos percentuais, como na página com JS
        corpos.append(tabela('Municípios com padrão atípico (Q3), com controle de 2022', ['Critério', 'Base', '% dos municípios'],
                             [(x['rotulo'], x['faixa'], _br(x['pct'], 1) + '%') for x in p['atipicos']]))
    con = p['concentracao']
    def resultado(r):
        if r is None:
            return 'Não disponível individualmente nesta base'
        return (f'{r["candidato"]}: {_br(r["pct"], 3)}% '
                f'({_br(r["votos"])} / {_br(r["validos"])} válidos); '
                + ('mais de 90%' if r['acima_90'] else 'até 90%'))
    corpos.append('<section class="cartao"><h2>Municípios com mais de 90% dos votos válidos</h2>'
                  + ''.join(f'<p>{ano}: {_br(r["acima_90"])} de {_br(r["avaliados"])} municípios avaliados.</p>'
                            for ano, r in con['resumo'].items())
                  + f'<p>Nos dois anos: {_br(con["nos_dois_anos"])} municípios.</p>'
                  + '<details class="explicacao"><summary>Como ler esta comparação</summary>'
                  '<p>Segundo turno; votos do candidato divididos pelos válidos. O corte é estritamente maior que 90%, '
                  'antes de arredondar. A tabela mostra o candidato mais votado em cada ano e inclui cidades que '
                  'passaram de 90% em pelo menos um ano. Compara códigos municipais do TSE, sem ajuste de limites territoriais. '
                  'A base contém só seções presentes nos dois turnos; municípios pequenos agrupados em OUTROS e exterior '
                  'ficam fora. Ausência não significa zero. Análise descritiva adicional, sem teste de irregularidade.</p></details></section>')
    corpos.append(tabela('Comparação municipal: 2º turno de 2026 × 2022',
                         ['Município / UF (código TSE)', '2026: líder e votação', '2022: líder e votação', 'Mais de 90%'],
                         [(f'{r["nome"]} / {r["uf"]} ({r["mun"]})', resultado(r['2026']), resultado(r['2022']), r['situacao'])
                          for r in con['linhas']]))
    ds = p['distribuicao_secoes']
    corpos.append('<section class="cartao"><h2>Seções com até 10 votos — 2º turno</h2>'
                  '<details class="explicacao"><summary>Como contamos as seções</summary>'
                  '<p>De zero a dez votos, inclusive. Uma seção é a combinação de UF, município, zona e número da seção. '
                  'Entram todas as seções com votos válidos no segundo turno, sem exigir presença no primeiro e sem piso '
                  'de tamanho. Seções sem válidos ficam fora. Brasil exclui exterior; os dois recortes adicionais mostram '
                  'o efeito dessa escolha. A unidade é a seção apurada, não o equipamento físico da urna.</p>'
                  '<p>Até dez votos é um limite absoluto; mais de 90% é uma proporção dos válidos, calculada sem arredondar. '
                  'Dez de cinquenta votos equivalem a 20%; dez de trezentos, a 3,33%. '
                  'As contagens de 2022 e 2026 são de universos próprios, sem parear seções entre eleições. '
                  'Análise descritiva adicional; isoladamente, essas contagens não demonstram irregularidade.</p></details></section>')
    for escopo, rotulo in [('brasil', 'Brasil, sem exterior'), ('exterior', 'Exterior'), ('brasil_exterior', 'Brasil + exterior')]:
        linhas = []
        for ano in ('2026', '2022'):
            b = ds['anos'][ano][escopo]
            for c in ('flavio', 'lula'):
                r = b['candidatos'][c]
                linhas.append((f'{ano} — {r["nome"]}', _br(b['avaliadas']), _br(r['zero']),
                               _br(r['de_1_a_5']), _br(r['de_6_a_10']), _br(r['ate_10']),
                               _fmt('pct', r['pct_ate_10']), _br(r['acima_90'])))
        corpos.append(tabela(f'Seções: {rotulo}', ['Ano / candidato', 'Seções avaliadas', 'Zero voto', '1–5 votos',
                                                '6–10 votos', 'Até 10 votos', '% das seções', 'Mais de 90% dos válidos'], linhas))
    for c in ('flavio', 'lula'):
        por_ano = {ano: {r['uf']: r for r in ds['anos'][ano]['ufs']} for ano in ('2026', '2022')}
        linhas = []
        for uf in sorted(set(por_ano['2026']) | set(por_ano['2022'])):
            linha = [uf]
            for ano in ('2026', '2022'):
                b = por_ano[ano].get(uf)
                linha += ([_br(b['candidatos'][c]['ate_10']), _fmt('pct', b['candidatos'][c]['pct_ate_10'])]
                          if b else ['—', '—'])
            linhas.append(tuple(linha))
        corpos.append(tabela(f'Até 10 votos por UF: {candidato(2026, c)} (2026) / {candidato(2022, c)} (2022)',
                             ['UF', '2026: seções', '2026: %', '2022: seções', '2022: %'], linhas))
    ctx = p['contexto']['anos']['2026']
    moeda = lambda v: '—' if v is None else 'R$ ' + _br(v, 2)
    ind = lambda v: '—' if v is None else _br(v, 3)
    corpos.append('<section class="cartao"><h2>Contexto municipal da eleição presidencial de 2026</h2>'
                  '<details class="explicacao"><summary>Fontes e limites do cruzamento</summary>'
                  '<p>IDHM de 2010 (Atlas/PNUD/Ipea/FJP, via Ipeadata); PIB e PIB por habitante de 2023 (IBGE); '
                  'prefeitos e partidos eleitos em 2024 (TSE). PIB por habitante não é renda das pessoas. '
                  'Categorias partidárias da tabela 1 de Bolognesi et al. (2025), pesquisa de 2022; centro-esquerda '
                  'e extrema esquerda agrupadas em Esquerda; centro-direita e extrema direita em Direita. '
                  'Siglas não presentes ficam sem classificação. Isso não mede a posição pessoal do prefeito '
                  'nem seu apoio presidencial. O partido atual não foi verificado.</p>'
                  '<p>Cada município tem o mesmo peso; sem ajuste por região ou porte. Medianas usam apenas os casos '
                  'com indicador disponível. A votação de 2022 é referência eleitoral; governos de 2024 não são '
                  'atribuídos a 2022. As associações não demonstram causalidade ou irregularidade. '
                  '<a href="../index.html#exp-contexto">Fontes e metodologia no painel</a>.</p></details></section>')
    corpos.append(tabela('Medianas por concentração de votos em 2026',
                         ['Grupo', 'Municípios', 'IDHM 2010 (n)', 'PIB/hab. 2023 (n)', 'PIB total 2023 (n)'],
                         [(g['rotulo'], _br(g['n']),
                           f'{ind(g["indicadores"]["idhm_2010"]["mediana"])} ({g["indicadores"]["idhm_2010"]["n"]})',
                           f'{moeda(g["indicadores"]["pib_pc_2023"]["mediana"])} ({g["indicadores"]["pib_pc_2023"]["n"]})',
                           f'{moeda(g["indicadores"]["pib_2023"]["mediana"])} ({g["indicadores"]["pib_2023"]["n"]})') for g in ctx['grupos']]))
    corpos.append(tabela('Bloco do partido eleito para a prefeitura em 2024 × concentração em 2026',
                         ['Bloco', 'Municípios avaliados', 'Acima de 90%', '% dentro do bloco'],
                         [(r['bloco'], _br(r['municipios']), _br(r['acima_90']), _fmt('pct', r['pct'])) for r in ctx['blocos']]))
    corpos.append(tabela('Correlação de Spearman com o percentual do candidato mais votado em 2026',
                         ['Indicador', 'Municípios com dados', 'Correlação'],
                         [(k, _br(r['n']), ind(r['rho'])) for k, r in ctx['correlacoes'].items()]))
    selecionados = [r for r in ctx['linhas'] if r['acima_90'] or r['acima_90_2022']]
    corpos.append(tabela('Contexto: municípios acima de 90% em 2026 ou 2022, presentes na base de 2026',
                         ['Município / UF', '2026', 'IDHM 2010', 'PIB/hab. 2023', 'Eleito em 2024', 'Partido de 2024 / bloco'],
                         [(f'{r["nome"]} / {r["uf"]}', f'{r["candidato"]}: {ind(r["pct_lider"])}%', ind(r['idhm_2010']),
                           moeda(r['pib_pc_2023']), (r['prefeito_2024'] or {}).get('nome', 'Não identificado'),
                           (r['prefeito_2024'] or {}).get('partido', '—') + ' / ' + (r['ideologia'] or {}).get('bloco', 'Sem classificação'))
                          for r in selecionados]))
    links = []
    for r in selecionados:
        v = r['verificacao_prefeitura']
        if v:
            links.append(f'<li>{e(r["nome"])}: {e(v["nome"])} — '
                         f'<a href="{e(v["url"], quote=True)}">{e(v["referencia"])}</a>; consulta {e(v["consulta"])}.</li>')
    corpos.append('<details class="cartao explicacao"><summary>Fontes institucionais sobre as prefeituras</summary><ul>'
                  + ''.join(links) + '</ul><p>Referências com datas distintas; não comprovam filiação atual ou ausência de substituições posteriores.</p></details>')
    for q in p['perguntas']:
        corpos.append(f'<section class="cartao"><h2>{e(q["id"])} — {e(q["titulo"])}</h2><ul>'
                      + ''.join(f'<li>{e(l)}</li>' for l in q['linhas']) + '</ul></section>')
    notas = ''.join(f'<p class="nota">{e(n)}</p>' for n in p.get('notas', []))
    aviso = ('<p class="aviso-ilustrativo">Valores de demonstração: não são resultados publicados.</p>' if p['ilustrativo'] else '')
    return ('<!doctype html>\n<html lang="pt-BR">\n<head>\n  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '  <meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'self\'; '
            'base-uri \'none\'; form-action \'none\'">\n'
            '  <title>Auditoria Pública – 2º turno 2026: tabelas</title>\n  <link rel="icon" type="image/png" href="../assets/icon.png">\n  <link rel="stylesheet" href="../style.css">\n</head>\n<body>\n'
            '  <main class="painel sem-js">\n'
            f'    <div class="painel-cab"><h1>Tabelas, sem JavaScript</h1><span class="muted">Atualizado em {e(p["atualizado"])}</span></div>\n'
            + aviso + '    <p class="nota">Versão preliminar. Associações entre municípios e seções, com 2022 como controle; '
            'um padrão atípico não indica irregularidade. <a href="../index.html">Voltar à página</a>.</p>\n    '
            + '\n    '.join(corpos) + f'\n    {notas}\n  </main>\n'
            '  <footer class="rodape"><span>Projeto independente. Dados: TSE. Não é uma fonte oficial.</span></footer>\n</body>\n</html>\n')


ENTRADAS = ('resultados.json', 'totais_nacionais_2026.csv', 'run_analise_2026.json',
            'municipios_2022.csv', 'municipios_2026.csv', 'nomes_municipios.csv',
            'distribuicao_secoes.json', 'run_distribuicao-secoes_2026.json',
            'contexto_municipal.json', 'fontes_contexto.json', 'prefeituras_verificadas.json')


def entradas(derived):
    """SHA-256 dos arquivos que alimentam o painel, para o registro da rodada."""
    d = pathlib.Path(derived)
    return {n: _sha(d / n) for n in ENTRADAS}


def painel(derived, out, exige_real=True):
    """exige_real: recusa resultados de uma rodada sem MANIFEST.json (dado sintético) ou sem a tag do pré-registro,
    e confere que o resultados.json é o registrado pela rodada de análise."""
    d = pathlib.Path(derived)
    run = json.loads((d / 'run_analise_2026.json').read_text(encoding='utf-8'))
    if run['saidas'].get('resultados.json') != _sha(d / 'resultados.json'):
        raise SystemExit('resultados.json difere do registrado em run_analise_2026.json: rode `auditoria analise` de novo')
    if exige_real and (run.get('insumos') is None or run.get('prereg_tag') is None):
        raise SystemExit('rodada de análise sem insumos do MANIFEST.json ou sem a tag prereg-v1 (dado sintético?)')
    r = json.loads((d / 'resultados.json').read_text(encoding='utf-8'))
    t = {row['NR_TURNO']: SimpleNamespace(**row) for row in pl.read_csv(d / 'totais_nacionais_2026.csv').iter_rows(named=True)}
    g26, g22 = _soma(r['q1']['2026']), _soma(r['q1']['2022'])
    res = {'ilustrativo': not exige_real, 'atualizado': run['gerado_utc'][:10],
           'kpis': _kpis(t[1], t[2]), 'ganho': _ganho(g26), 'divisao': _divisao(g26, g22),
           'atipicos': _atipicos(r['q3']['2026'], r['q3']['2022']), 'perguntas': _perguntas(r, g26, g22),
           'notas': _notas(t[1], t[2], g26), 'concentracao': concentracao(d),
           'distribuicao_secoes': _distribuicao(d, exige_real), 'contexto': analisar_contexto(d)}
    out = pathlib.Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    out.with_name('tabelas.html').write_text(tabelas_html(res), encoding='utf-8')
    return res
