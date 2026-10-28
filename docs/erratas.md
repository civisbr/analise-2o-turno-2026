# Erratas

Alterações posteriores ao congelamento de [`pre-registro.md`](pre-registro.md) entram aqui, com data, motivo e efeito. Nenhuma edição silenciosa.

## E1 — 28/10/2026 — seção com erro binomial zero (esclarecimento de implementação)

- **O quê:** em Q5, seção com `p = 0` ou `p = 1` nos dois turnos (todos os votos de um só finalista) tem erro binomial esperado `se = 0`. O pré-registro não trata esse caso. A implementação define `z = 0` para essas seções: não são sinalizáveis e continuam no denominador da fração de seções com `|z| > 4`.
- **Motivo:** nos dados de 2022, 68 seções caem nesse caso. Em 3, o resíduo era `0/0` e o κ de 2022 saía `NaN`; nas outras 65, `z` era infinito, o que as sinalizaria como extremas sem base estatística.
- **Efeito (controle 2022):** κ = 0,45266 e fração de `|z| > 4` = 0,000976317. Excluir essas seções em vez de zerá-las dá κ = 0,45277 e fração 0,000976459. A regra vale igual para 2026 e para a simulação nula.
- **Limitação:** seções quase unânimes (erro binomial pequeno, mas positivo) podem ter `z` muito alto pela aproximação normal; em 2022, 11 de 18 seções com `se < 0,5 p.p.` passam de `|z| > 4`.
- **Código:** PR #9.

## E2 — 28/10/2026 — leitura dos dados do 2º turno

- **O quê:** o detalhe município-zona do 2º turno de 2026 foi publicado pelo TSE em 27/10/2026 (19:47 GMT). Os arquivos por seção do 2º turno (`votacao_secao`, `detalhe_votacao_secao`) foram baixados em 27/10/2026, depois da tag `prereg-v1`, e o fechamento entre as fontes passou sem divergência antes de qualquer análise.
- **Efeito:** nenhum no método. Registra que nenhum dado do 2º turno de 2026 foi lido antes do congelamento, como a declaração de acesso do pré-registro prevê.
