# Pré-registro

**Status: rascunho para revisão humana.** Passa a valer quando a tag `prereg-v1` for criada sobre o commit que o contém. Depois disso, mudanças só como errata em [`erratas.md`](erratas.md). `make analysis` recusa rodar sem a tag.

Data do rascunho: 26/10/2026.

## Pendências conhecidas antes do congelamento

- A definição de votos válidos do código ainda soma como válidos os votos de candidato com votos anulados (1º turno: 5.246 votos do candidato nº 28, que o TSE conta como nulos). Será corrigida na Fase 1 e testada contra o total oficial; a tag `prereg-v1` só é criada depois disso.
- O número de reamostragens padrão da CLI (300) difere do pré-registrado (2.000); `make analysis` usa 2.000.
- O registro de execução (`run.json`: commit, hashes de entrada, parâmetros, semente) ainda não é gerado.

## Declaração de acesso aos dados

Antes deste documento foram vistos: (a) agregados nacionais divulgados pela imprensa nos dois turnos de 2026 (tabela do `project.md`, seção 2); (b) o layout e os nomes de colunas dos arquivos do TSE; (c) os totais nacionais do **1º turno** de 2026 por candidato (Lula, Flávio e os demais, incluindo o nº 28), brancos e nulos, obtidos agregando o arquivo por seção para validar a leitura. Nenhum dado de município ou seção, de nenhum turno, foi analisado. As perguntas abaixo foram formuladas depois de conhecer os agregados nacionais, não antes.

## Perguntas, métodos e dados

| ID | Pergunta | Método | Nível |
|---|---|---|---|
| Q1 | De onde veio o ganho conjunto dos finalistas? | Decomposição contábil: `ΔLula + ΔFlávio = terceira via + Δválidos` e `Δválidos = Δcomparecimento + queda de brancos e nulos` | nacional, UF, município |
| Q2 | A divisão desse ganho entre Lula e Flávio difere de 2022? | Regressão ponderada `ΔL/v1 ~ α·terceira_via/v1 + β·Δválidos/v1` (modelo A) e a variante com comparecimento e brancos/nulos separados (modelo B), ponderada pelos válidos do 1º turno, com e sem efeito fixo de UF; bootstrap por município; comparação 2026 × 2022 | município |
| Q3 | Há municípios cujo ganho de Lula destoa do padrão do estado? | Resíduos do modelo B com efeito fixo de UF; z robusto (MAD) convertido em p bicaudal pela normal padrão; correção por FDR | município |
| Q4 | Onde Flávio perdeu votos absolutos, o comparecimento caiu? | Contagem de municípios com `ΔFlávio < 0` separados por `Δcomparecimento < 0` e `≥ 0` | município |
| Q5 | O swing de Lula por seção destoa do município? Há excesso de seções extremas frente ao ruído binomial? | z por seção com sobredispersão robusta (κ por MAD); fração de seções com `|z| > 4` em 2026 comparada à de 2022 | seção, só agregados publicados |
| Q6 | Seções que fecharam após 17h tiveram swing diferente do resto do município? | Permutação de "fechou tarde" dentro do município (teste principal); IC por bootstrap secundário | seção |

**Q6** depende de hora de encerramento por seção, que não existe nos CSV do TSE avaliados (ver [`metodologia.md`](metodologia.md)). Só roda se a hora de encerramento for extraída dos boletins de urna. Se não for, a página registra "não testável com dados públicos", e isso é um resultado. Colunas de recebimento do BU no TSE não serão usadas como substitutas de hora de fechamento.

**Fora de escopo:** Benford de 1º dígito em seções; qualquer análise que dependa de dado individual de eleitor; análise de urna específica por número de série.

## Definições e filtros

- Cargo Presidente (`CD_CARGO` 1); candidatos: Lula (13) e Flávio Bolsonaro (22). 2022: Lula (13) e Bolsonaro (22).
- Votos válidos, brancos e nulos conforme a totalização oficial do TSE (votos anulados contam como nulos).
- Municípios com válidos `< 200` em qualquer turno são excluídos de Q2–Q4 (`--min-valid 200`). Exterior (`ZZ`) fica fora de Q2–Q5 e é reportado à parte nos totais (Q1).
- Seções com menos de 50 votos de Lula + Flávio em qualquer turno são excluídas de Q5.
- Seções presentes em só um dos turnos são descartadas; o relatório informa quantas e quantos votos.
- Controle histórico: 2022 em toda análise; 2018 e 2014 para abstenção e comparecimento se houver dados.

## Limiares

- Seção atípica (Q5): `|z| > 4`. Município atípico (Q3): `q < 0,05` pelo procedimento de Benjamini-Hochberg sobre todos os municípios testados.
- Refit robusto: excluir `|z| > 4` e reajustar; reportar os dois ajustes.
- Bootstrap: 2.000 reamostragens por município na rodada final; semente fixa registrada em `run.json`. Com poucas UFs, sem erros-padrão agrupados por UF.
- Coeficiente não identificado (dp do regressor dentro da UF `< 0,5 pp`): omitido da página.
- Sensibilidade: `min-valid` (100, 200, 500), com e sem efeito fixo, com e sem refit robusto, só Nordeste, fora do Nordeste.

## Número de testes e esperado por acaso

- Q3: um teste por município elegível (ordem de 5.500; o número exato é declarado no relatório da rodada). Com q = 0,05, o procedimento de Benjamini-Hochberg admite até 5% de falsos entre os sinalizados.
- Q5: um teste por seção elegível (ordem de 5 × 10⁵). Sob normalidade, `|z| > 4` esperaria cerca de 6 × 10⁻⁵ por seção (≈ 30 seções); o valor usado na página vem da simulação descrita abaixo, não deste cálculo.
- A página mostra "esperado por acaso: X; observado: Y". X vem de simulação sob o modelo nulo (binomial com sobredispersão κ estimada) e do controle de 2022, não de normalidade teórica.

## Critério do que conta como "atípico" e como "explicado"

- **Atípico (município):** resíduo do modelo B com `q < 0,05` e mantido nos dois ajustes (com e sem refit robusto). **Atípico (conjunto de seções):** fração de seções com `|z| > 4` em 2026 acima do máximo das frações por UF observadas em 2022, e acima do esperado por acaso.
- **Explicado:** a diferença `α(2026) − α(2022)` (e a de `β`) cai abaixo da metade quando o modelo inclui, como covariáveis, apenas variáveis presentes nos dados oficiais: variação do comparecimento, queda de brancos e nulos, tamanho do município (log dos válidos), peso da terceira via no 1º turno e efeito fixo de UF; ou o IC de 95% da diferença inclui zero. Mobilização, clima, transporte e troca de voto útil não são mensuráveis aqui e entram só como explicações qualitativas ao lado do resultado.
- Se nenhum dos dois ocorrer, o resultado é "não explicado pelo modelo". Isso não é irregularidade.

## Explicações alternativas (escritas antes de ver os resultados)

Mobilização do eleitorado que antes não votava; abstenção seletiva entre eleitores da terceira via; troca de voto útil; voto da terceira via indo para um dos finalistas por orientação; transferência ou criação de seções; clima e transporte no dia; diferença de composição urbana, rural e etária entre municípios; eleitores novos (entrada no cadastro). Cada resultado é publicado com essas hipóteses ao lado.

## Interpretação de `α` e `β`

`α` não é a fração da terceira via que votou em Lula: é a parcela, que fica com Lula, do ganho líquido associado a cada voto da terceira via, mantido fixo `Δválidos`. Só se comparam `α` e `β` entre eleições, nunca com pesquisas de intenção de voto. Gráficos entre municípios levam a nota de inferência ecológica.

## Vocabulário

"Padrão atípico", "associação", "não explicado pelo modelo". Nunca "fraude", "manipulação" ou "irregularidade" como conclusão. Resultados negativos têm o mesmo destaque que os positivos.
