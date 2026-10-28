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
    const col = el('div', {class: 'col', role: 'img', 'aria-label': `${a.ano}: Lula ${a.lula}%, Flávio ${a.flavio}%`});
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
}

main().catch(() => {
  document.body.classList.add('ilustrativo');
  const av = document.getElementById('aviso');
  av.hidden = false; av.textContent = 'Não foi possível carregar os dados desta página.';
});
