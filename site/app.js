'use strict';

const COR = {verde: 'var(--verde)', azul: 'var(--azul)', amarelo: 'var(--amarelo)', roxo: 'var(--roxo)'};
const CLASSES = ['verde', 'azul', 'amarelo', 'roxo', 'vermelho', 'laranja'];
const cor = (c) => COR[c] || 'var(--muted)';
const classeCor = (c) => (CLASSES.includes(c) ? 'cor-' + c : 'cor-muted');
const NS = 'http://www.w3.org/2000/svg';
const fmt = new Intl.NumberFormat('pt-BR');
const fmt2 = new Intl.NumberFormat('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt1 = new Intl.NumberFormat('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1});

const fmt1c = (n) => fmt2.format(n);
const sinal = (n) => (n > 0 ? '+' : n < 0 ? '−' : '');
const num = {
  int: (v) => fmt.format(v),
  sint: (v) => sinal(v) + fmt.format(Math.abs(v)),
  pct: (v) => fmt2.format(v) + '%',
  pp: (v) => sinal(v) + fmt2.format(Math.abs(v)) + ' p.p.',
  pctsinal: (v) => sinal(v) + fmt2.format(Math.abs(v)) + '%',
  par_pct: (v) => v.map((x) => fmt2.format(x) + '%').join(' / '),
  par_int: (v) => v.map((x) => fmt.format(x)).join(' / '),
};

const fmtNum = (tipo, v) => (v != null && Object.hasOwn(num, tipo) ? num[tipo](v) : '—');

function el(tag, attrs = {}, texto) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (texto !== undefined) e.textContent = texto;
  return e;
}

function svg(tag, attrs = {}) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

function spark(serie, c) {
  const w = 62, h = 26, max = Math.max(...serie), min = Math.min(...serie);
  const pts = serie.map((v, i) => `${(i / (serie.length - 1)) * w},${h - 2 - ((v - min) / (max - min || 1)) * (h - 4)}`).join(' ');
  const s = svg('svg', {viewBox: `0 0 ${w} ${h}`, class: 'spark', 'aria-hidden': 'true'});
  s.style.stroke = cor(c);   // setAttribute('style') seria bloqueado pelo CSP
  s.appendChild(svg('polyline', {points: pts}));
  return s;
}

function kpi(k) {
  const c = el('article', {class: 'kpi'});
  const r = el('div', {class: 'kpi-r'});
  if (k.ponto) { const p = el('i'); p.style.background = cor(k.ponto); r.appendChild(p); }
  r.appendChild(document.createTextNode(k.rotulo));
  c.appendChild(r);
  c.appendChild(el('div', {class: 'kpi-v'}, fmtNum(k.tipo, k.valor)));
  c.appendChild(el('div', {class: 'kpi-2'}, [fmtNum(k.linha2.tipo, k.linha2.valor), k.linha2.sufixo].filter(Boolean).join(' ')));
  const d = el('div', {class: 'kpi-d'});
  const txt = k.delta.texto ? k.delta.texto : [fmtNum(k.delta.tipo, k.delta.valor), k.delta.sufixo].filter(Boolean).join(' ');
  d.appendChild(el('span', k.delta.texto || k.delta.valor == null || k.delta.valor < 0 ? {class: 'neutro'} : {}, txt));
  if (k.serie) d.appendChild(spark(k.serie, k.cor));
  c.appendChild(d);
  return c;
}

function vazio(id, texto) {
  document.getElementById(id).appendChild(el('p', {class: 'muted peq'}, texto));
}

function donut(ganho) {
  if (!ganho) return vazio('donut', 'Aguardando resultados.');
  const box = document.getElementById('donut');
  const R = 68, C = 2 * Math.PI * R;
  const s = svg('svg', {viewBox: '0 0 168 168', role: 'img', 'aria-label': 'Decomposição do ganho de votos válidos'});
  let off = 0;
  const total = ganho.partes.reduce((a, p) => a + p.valor, 0);
  for (const p of ganho.partes) {
    if (p.valor <= 0) continue;   // arco negativo não existe; a legenda mostra o valor
    const len = (p.valor / total) * C;
    const arco = svg('circle', {cx: 84, cy: 84, r: R, 'stroke-dasharray': `${len} ${C - len}`,
      'stroke-dashoffset': -off, transform: 'rotate(-90 84 84)'});
    arco.style.stroke = cor(p.cor);
    s.appendChild(arco);
    off += len;
  }
  box.appendChild(s);
  const c = el('div', {class: 'donut-c'});
  c.appendChild(el('b', {}, sinal(total) + fmt2.format(Math.abs(total) / 1e6) + ' mi'));
  c.appendChild(el('span', {}, 'ganho conjunto'));
  c.appendChild(el('span', {}, 'dos finalistas'));
  box.appendChild(c);
  const leg = document.getElementById('ganho-leg');
  for (const p of ganho.partes) {
    const li = el('li');
    const i = el('i'); i.style.background = cor(p.cor); li.appendChild(i);
    li.appendChild(document.createTextNode(p.rotulo));
    li.appendChild(el('small', {}, `${sinal(p.valor)}${fmt.format(Math.abs(p.valor))} (${fmt1.format(p.valor / total * 100)}%)`));
    leg.appendChild(li);
  }
}

function barras(div) {
  if (!div) { document.getElementById('div-txt').textContent = 'Aguardando resultados.'; return; }
  const box = document.getElementById('barras');
  const eixo = el('div', {class: 'eixo', 'aria-hidden': 'true'});
  for (const t of ['100%', '75%', '50%', '25%', '0%']) eixo.appendChild(el('span', {}, t));
  box.appendChild(eixo);
  for (const a of div.anos) {
    const col = el('div', {class: 'col', role: 'img', 'aria-label': `${a.ano}: Lula ${a.lula}%, ${a.candidato_22} ${a.flavio}%`});
    const topo = el('span', {class: 'cor-verde'}); topo.style.height = a.lula + '%';
    const base = el('span', {class: 'cor-azul'}); base.style.height = a.flavio + '%';
    col.append(topo, base, el('em', {}, String(a.ano)));
    box.appendChild(col);
  }
  const [a0, a1] = div.anos;
  document.getElementById('div-txt').textContent =
    `Em ${a0.ano}, Lula ficou com ~${a0.lula}% do ganho conjunto. Em ${a1.ano}, ficou com ~${a1.lula}%.`;
}

function atipicos(lista) {
  if (!lista) return vazio('atipicos', 'Aguardando resultados.');
  const box = document.getElementById('atipicos');
  const max = Math.max(...lista.map((x) => x.pct));
  for (const x of lista) {
    const l = el('div', {class: 'hb'});
    const r = el('span', {class: 'r'}, x.rotulo);
    if (x.faixa) r.appendChild(el('small', {}, `(${x.faixa})`));
    const b = el('span', {class: 'b ' + classeCor(x.cor)}); b.style.width = (x.pct / max) * 100 + '%';
    l.append(r, b, el('span', {class: 'p'}, fmt1.format(x.pct) + '%'));
    box.appendChild(l);
  }
}

function perguntas(lista) {
  if (!lista) return;
  const box = document.getElementById('perguntas');
  for (const q of lista) {
    const c = el('article', {class: 'cartao'});
    const h = el('h3');
    h.append(el('small', {}, q.id), document.createTextNode(' ' + q.titulo));
    const ul = el('ul');
    for (const l of q.linhas || []) ul.appendChild(el('li', {}, l));
    c.append(h, ul);
    box.appendChild(c);
  }
}

function explicacoes() {
  function abrir(hash) {
    const detalhe = document.getElementById(hash.slice(1));
    if (detalhe && detalhe.tagName === 'DETAILS') {
      detalhe.open = true;
      detalhe.scrollIntoView({block: 'start'});
      detalhe.querySelector('summary').focus({preventScroll: true});
    }
  }
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (link) abrir(link.getAttribute('href'));
  });
  window.addEventListener('hashchange', () => abrir(location.hash));
  abrir(location.hash);
}

function concentracao(dados) {
  if (!dados) return vazio('concentracao-resumo', 'Comparação municipal indisponível.');
  const resumo = document.getElementById('concentracao-resumo');
  for (const ano of ['2026', '2022']) {
    const r = dados.resumo[ano];
    const c = el('article', {class: 'cartao'});
    c.append(el('h3', {}, `${ano}: ${fmt.format(r.acima_90)} municípios`),
      el('p', {class: 'nota'}, `Acima de 90%, entre ${fmt.format(r.avaliados)} avaliados.`));
    for (const [nome, n] of Object.entries(r.por_candidato)) c.append(el('p', {class: 'nota'}, `${nome}: ${fmt.format(n)}`));
    resumo.append(c);
  }
  resumo.append(el('p', {class: 'nota'}, `${fmt.format(dados.nos_dois_anos)} municípios ultrapassaram 90% nos dois anos.`));
  const busca = document.getElementById('busca-municipio');
  const filtro = document.getElementById('filtro-concentracao');
  const normaliza = (s) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  const fmt3 = new Intl.NumberFormat('pt-BR', {minimumFractionDigits: 3, maximumFractionDigits: 3});
  function celula(r) {
    const td = el('td');
    if (!r) { td.textContent = 'Não disponível individualmente nesta base'; return td; }
    td.append(el('strong', {}, r.candidato), el('span', {class: 'voto-pct'}, `${fmt3.format(r.pct)}%`),
      el('small', {}, `${fmt.format(r.votos)} / ${fmt.format(r.validos)} válidos`),
      el('small', {class: r.acima_90 ? 'destaque' : 'muted'}, r.acima_90 ? 'Mais de 90%' : 'Até 90%'));
    return td;
  }
  function render() {
    const termo = normaliza(busca.value.trim());
    const linhas = dados.linhas.filter((r) => {
      const texto = normaliza(`${r.nome} ${r.uf} ${r.mun} ${r['2022']?.nome || ''}`);
      return texto.includes(termo) && (filtro.value === 'todos' ||
        (filtro.value === 'ambos' ? r.situacao === 'Nos dois anos' : r[filtro.value]?.acima_90));
    });
    const corpo = document.getElementById('concentracao-linhas');
    corpo.replaceChildren();
    for (const r of linhas) {
      const tr = el('tr');
      const cidade = el('th', {scope: 'row'}, `${r.nome} / ${r.uf}`);
      cidade.append(el('small', {class: 'muted'}, `Código TSE: ${r.mun}`));
      tr.append(cidade, celula(r['2026']), celula(r['2022']), el('td', {}, r.situacao));
      corpo.append(tr);
    }
    if (!linhas.length) {
      const tr = el('tr'); tr.append(el('td', {colspan: '4'}, 'Nenhum município corresponde aos filtros.')); corpo.append(tr);
    }
    document.getElementById('concentracao-contagem').textContent = `${fmt.format(linhas.length)} município(s) exibido(s).`;
  }
  busca.addEventListener('input', render); filtro.addEventListener('change', render); render();
}

function distribuicaoSecoes(dados) {
  if (!dados) return vazio('secoes-resumo', 'Contagem de seções indisponível.');
  const total = dados.anos['2026'].brasil_exterior.candidatos.flavio.ate_10;
  document.getElementById('secoes-verificacao').textContent = `Conferência de 2026: ${fmt.format(total)} seções com até 10 votos para Flávio Bolsonaro, incluindo ` +
    `${fmt.format(dados.anos['2026'].brasil.candidatos.flavio.ate_10)} no Brasil e ${fmt.format(dados.anos['2026'].exterior.candidatos.flavio.ate_10)} no exterior.`;
  const seletor = document.getElementById('escopo-secoes');
  const candidatoUF = document.getElementById('candidato-secoes-uf');
  function render() {
    const escopo = seletor.value;
    const resumo = document.getElementById('secoes-resumo'); resumo.replaceChildren();
    const corpo = document.getElementById('secoes-linhas'); corpo.replaceChildren();
    const detalhes = document.getElementById('secoes-tamanho'); detalhes.replaceChildren();
    for (const ano of ['2026', '2022']) {
      const b = dados.anos[ano][escopo]; const f = b.candidatos.flavio;
      const cartao = el('article', {class: 'cartao'});
      cartao.append(el('h3', {}, `${ano} — ${f.nome}`), el('strong', {class: 'kpi-v'}, fmt.format(f.ate_10)),
        el('p', {class: 'nota'}, `seções com até 10 votos (${fmtNum('pct', f.pct_ate_10)} de ${fmt.format(b.avaliadas)} avaliadas).`));
      resumo.append(cartao);
      for (const c of ['flavio', 'lula']) {
        const r = b.candidatos[c]; const tr = el('tr');
        tr.append(el('th', {scope: 'row'}, `${ano} — ${r.nome}`));
        for (const v of [b.avaliadas, r.zero, r.de_1_a_5, r.de_6_a_10, r.ate_10]) tr.append(el('td', {}, fmt.format(v)));
        tr.append(el('td', {}, fmtNum('pct', r.pct_ate_10)), el('td', {}, fmt.format(r.acima_90))); corpo.append(tr);
        const t = r.validos_nas_secoes_ate_10;
        detalhes.append(el('p', {}, `${ano}, ${r.nome}: das ${fmt.format(r.ate_10)} seções com até 10 votos, ` +
          `${fmt.format(r.ate_10_e_adversario_acima_90)} tinham mais de 90% dos válidos para o adversário, e ` +
          `${fmt.format(r.ate_10_com_50_mais_validos)} tinham pelo menos 50 votos válidos. ` +
          (t.min == null ? 'Não há seções nesse recorte.' : `Válidos por seção desse grupo: mínimo ${fmt.format(t.min)}, mediana ${fmt.format(t.mediana)}, máximo ${fmt.format(t.max)}.`)));
      }
      detalhes.append(el('p', {}, `${ano}: ${fmt.format(b.sem_validos_excluidas)} seções sem votos válidos excluídas neste recorte.`));
    }
    const a = dados.anos['2026'][escopo].candidatos.flavio, b = dados.anos['2022'][escopo].candidatos.flavio;
    document.getElementById('secoes-comparacao').textContent = `Candidato nº 22: ${num.sint(a.ate_10 - b.ate_10)} seções com até 10 votos em 2026 frente a 2022` +
      (a.pct_ate_10 != null && b.pct_ate_10 != null ? ` (${num.pp(a.pct_ate_10 - b.pct_ate_10)} na proporção de seções).` : '.');
  }
  function renderUF() {
    const corpo = document.getElementById('secoes-uf-linhas'); corpo.replaceChildren();
    const mapas = Object.fromEntries(['2026', '2022'].map(ano => [ano, new Map(dados.anos[ano].ufs.map(r => [r.uf, r]))]));
    const ufs = [...new Set([...mapas['2026'].keys(), ...mapas['2022'].keys()])].sort();
    for (const uf of ufs) {
      const tr = el('tr'); tr.append(el('th', {scope: 'row'}, uf));
      for (const ano of ['2026', '2022']) {
        const r = mapas[ano].get(uf)?.candidatos[candidatoUF.value];
        tr.append(el('td', {}, r ? fmt.format(r.ate_10) : '—'), el('td', {}, r ? fmtNum('pct', r.pct_ate_10) : '—'));
      }
      corpo.append(tr);
    }
  }
  seletor.addEventListener('change', render); candidatoUF.addEventListener('change', renderUF); render(); renderUF();
}

function contextoMunicipal(dados) {
  if (!dados) return vazio('contexto-resumo', 'Contexto municipal indisponível.');
  const a = dados.anos['2026'];
  const decimal = new Intl.NumberFormat('pt-BR', {minimumFractionDigits: 3, maximumFractionDigits: 3});
  const dinheiro = new Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'});
  const valor = (v, moeda = false) => v == null ? 'Não disponível' : (moeda ? dinheiro : decimal).format(v);
  const resumo = document.getElementById('contexto-resumo');
  for (const g of a.grupos) {
    const c = el('article', {class: 'cartao'});
    c.append(el('h3', {}, `${g.rotulo}: ${fmt.format(g.n)} municípios`));
    for (const [k, rotulo] of [['idhm_2010', 'IDHM 2010'], ['pib_pc_2023', 'PIB/hab. 2023'], ['pib_2023', 'PIB total 2023']]) {
      const i = g.indicadores[k];
      c.append(el('p', {class: 'nota'}, `Mediana de ${rotulo}: ${valor(i.mediana, k !== 'idhm_2010')} (n = ${fmt.format(i.n)}).`));
    }
    resumo.append(c);
  }
  const cobertura = a.cobertura;
  document.getElementById('contexto-cobertura').append(el('p', {}, `Cobertura: ${fmt.format(cobertura.avaliados)} municípios. ` +
    `${fmt.format(cobertura.sem_ibge)} sem correspondência exata no IBGE; ${fmt.format(cobertura.sem_prefeito_2024)} sem prefeito eleito identificado na base de 2024. ` +
    'Esses casos permanecem na lista com a ausência indicada.'));
  const blocos = document.getElementById('contexto-blocos');
  for (const b of a.blocos) {
    const tr = el('tr'); tr.append(el('th', {scope: 'row'}, b.bloco));
    for (const v of [fmt.format(b.municipios), fmt.format(b.acima_90), fmtNum('pct', b.pct)]) tr.append(el('td', {}, v));
    blocos.append(tr);
  }
  const busca = document.getElementById('contexto-busca'), filtro = document.getElementById('contexto-filtro');
  const mais = document.getElementById('contexto-mais'); let limite = 50;
  const normaliza = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  function render() {
    const termo = normaliza(busca.value.trim());
    const linhas = a.linhas.filter(r => (filtro.value === 'todos' || r.acima_90 || (filtro.value === 'historico' && r.acima_90_2022)) &&
      normaliza(`${r.nome} ${r.uf} ${r.prefeito_2024?.partido || ''}`).includes(termo));
    const corpo = document.getElementById('contexto-linhas'); corpo.replaceChildren();
    for (const r of linhas.slice(0, limite)) {
      const tr = el('tr'); const local = el('th', {scope: 'row'}, `${r.nome} / ${r.uf}`);
      local.append(el('small', {}, `TSE ${r.mun} · IBGE ${r.ibge || 'não associado'}`));
      tr.append(local, el('td', {}, `${r.candidato}: ${decimal.format(r.pct_lider)}%`),
        el('td', {}, r.pct_lider_2022 == null ? 'Não disponível' : `${r.candidato_2022}: ${decimal.format(r.pct_lider_2022)}%`),
        el('td', {}, valor(r.idhm_2010)), el('td', {}, valor(r.pib_pc_2023, true)));
      const prefeito = el('td', {}, r.prefeito_2024?.nome_urna || 'Não identificado');
      if (r.prefeito_2024) prefeito.append(el('small', {}, r.prefeito_2024.nome));
      const ver = r.verificacao_prefeitura;
      if (ver) {
        const d = el('details', {class: 'explicacao'});
        d.append(el('summary', {}, 'Fonte sobre a gestão'), el('p', {}, `${ver.nome}. ${ver.referencia}. Consultada em ${ver.consulta}. Partido atual não verificado.`),
          el('a', {href: ver.url}, 'Consultar fonte institucional'));
        prefeito.append(d);
      }
      tr.append(prefeito, el('td', {}, `${r.prefeito_2024?.partido || '—'} · ${r.ideologia?.bloco || 'Sem classificação'}`)); corpo.append(tr);
    }
    if (!linhas.length) { const tr = el('tr'); tr.append(el('td', {colspan: '7'}, 'Nenhum município corresponde aos filtros.')); corpo.append(tr); }
    mais.hidden = linhas.length <= limite;
    document.getElementById('contexto-contagem').textContent = `${fmt.format(Math.min(limite, linhas.length))} de ${fmt.format(linhas.length)} municípios exibidos.`;
  }
  function reinicia() { limite = 50; render(); }
  busca.addEventListener('input', reinicia); filtro.addEventListener('change', reinicia);
  mais.addEventListener('click', () => { limite += 50; render(); }); render();
  const grafico = document.getElementById('contexto-grafico'); const indicador = document.getElementById('contexto-indicador');
  function desenha() {
    if (!grafico.open) return;
    const k = indicador.value; const pontos = a.linhas.filter(r => r[k] != null && r[k] > 0);
    const log = k === 'pib_pc_2023'; const conv = v => log ? Math.log10(v) : v;
    const xs = pontos.map(r => conv(r[k])); const lo = Math.min(...xs), hi = Math.max(...xs);
    const s = svg('svg', {viewBox: '0 0 800 350', class: 'scatter', role: 'img', 'aria-label': 'Indicador municipal versus percentual do candidato mais votado em 2026'});
    const x = v => 65 + (conv(v) - lo) / (hi - lo || 1) * 700; const y = v => 290 - (v - 50) / 50 * 250;
    for (const v of [50, 70, 90, 100]) {
      s.append(svg('line', {x1: 65, x2: 765, y1: y(v), y2: y(v), class: 'scatter-grade'}));
      const t = svg('text', {x: 8, y: y(v) + 5}); t.textContent = `${v}%`; s.append(t);
    }
    for (let i = 0; i <= 4; i++) {
      const v = lo + (hi - lo) * i / 4; const t = svg('text', {x: 65 + 700 * i / 4, y: 320, 'text-anchor': 'middle'});
      t.textContent = log ? fmt.format(Math.round(10 ** v)) : decimal.format(v); s.append(t);
    }
    for (const r of [...pontos].sort((u, v) => Number(u.acima_90) - Number(v.acima_90))) {
      const c = svg('circle', {cx: x(r[k]), cy: y(r.pct_lider), r: r.acima_90 ? 4 : 2, class: r.acima_90 ? 'scatter-alto' : 'scatter-base'});
      const texto = `${r.nome} / ${r.uf}: ${valor(r[k], log)}; ${r.candidato}, ${decimal.format(r.pct_lider)}% dos válidos.`;
      const title = svg('title'); title.textContent = texto; c.append(title);
      c.addEventListener('click', () => { document.getElementById('contexto-ponto').textContent = texto; }); s.append(c);
    }
    document.getElementById('contexto-scatter').replaceChildren(s);
    const corr = a.correlacoes[k];
    document.getElementById('contexto-correlacao').textContent = `Spearman: ${corr.rho == null ? 'não avaliável' : decimal.format(corr.rho)}; ${fmt.format(corr.n)} municípios. Sem ajuste por região ou porte; associação não implica causalidade.`;
  }
  grafico.addEventListener('toggle', desenha); indicador.addEventListener('change', desenha);
}

function tema() {
  const raiz = document.documentElement;
  try { const t = localStorage.getItem('tema'); if (t === 'light' || t === 'dark') raiz.dataset.theme = t; } catch (e) { /* sem armazenamento */ }
  const botao = document.getElementById('tema');
  botao.setAttribute('aria-pressed', String(raiz.dataset.theme === 'light'));
  botao.addEventListener('click', () => {
    const novo = raiz.dataset.theme === 'light' ? 'dark' : 'light';
    raiz.dataset.theme = novo;
    botao.setAttribute('aria-pressed', String(novo === 'light'));
    try { localStorage.setItem('tema', novo); } catch (e) { /* sem armazenamento */ }
  });
}

async function main() {
  tema();
  explicacoes();
  const r = await fetch('data/painel.json');
  if (!r.ok) throw new Error('data/painel.json: HTTP ' + r.status);
  const d = await r.json();
  if (d.atualizado) {
    const [y, m, dia] = d.atualizado.split('-');
    document.getElementById('atualizado').textContent = `Atualizado em ${dia}/${m}/${y}`;
  } else {
    document.getElementById('atualizado').textContent = 'Aguardando resultados';
  }
  const ilus = d.ilustrativo !== false;   // sem a chave, assume ilustrativo
  document.getElementById('aviso').hidden = !ilus;
  document.body.classList.toggle('ilustrativo', ilus);
  document.getElementById('kpis').append(...d.kpis.map(kpi));
  const notas = document.getElementById('notas');
  for (const n of d.notas || []) notas.appendChild(el('p', {}, n));
  donut(d.ganho); barras(d.divisao); atipicos(d.atipicos); perguntas(d.perguntas);
  concentracao(d.concentracao);
  distribuicaoSecoes(d.distribuicao_secoes);
  contextoMunicipal(d.contexto);
}

main().catch(() => {
  document.body.classList.add('ilustrativo');
  const av = document.getElementById('aviso');
  av.hidden = false; av.textContent = 'Não foi possível carregar os dados desta página.';
});
