# Metodologia

Decisões não óbvias, em ordem cronológica. Hipóteses e limiares estão em [`pre-registro.md`](pre-registro.md).

## Layout dos arquivos do TSE (verificado em 26/10/2026)

Base: `https://cdn.tse.jus.br/estatistica/sead/odsele/`. O layout é o mesmo em 2022 e 2026.

- `votacao_secao/votacao_secao_<ano>_BR.zip`: o cargo Presidente de **todas** as UFs fica no membro `votacao_secao_<ano>_BR.csv` (`CD_CARGO` 1, `SG_UF` é a UF real da seção). Os zips `votacao_secao_<ano>_<UF>.zip` só têm cargos estaduais (3, 5, 6, 7).
- `detalhe_votacao_secao/detalhe_votacao_secao_<ano>.zip`: arquivo **nacional único**, com um membro por UF mais `_BR.csv` (Presidente) e `_BRASIL.csv`. Não existe `detalhe_votacao_secao_<ano>_<UF>.zip` (404).
- Em 26/10/2026 os arquivos de 2026 foram gerados em 05–07/10 e só têm o 1º turno. O 2º turno não estava publicado.
- `ZZ` (exterior) aparece nos dois arquivos e fica fora do conjunto `ALL` até a Fase 2.

## Votos válidos

Os dois arquivos de seção concordam entre si, seção a seção (`make verify`): válidos de `votacao_secao` = `QT_VOTOS_NOMINAIS` de `detalhe_votacao_secao`, e comparecimento = nominais + brancos + nulos. A **definição adotada** é a dos arquivos de seção, porque é a única reproduzível a partir do dado aberto.

O arquivo `detalhe_votacao_munzona` (agregação do próprio TSE por município-zona) usa outra regra: válidos = nominais das seções − `QT_VOTOS_NULOS_TECNICOS`, e `QT_TOTAL_VOTOS_NULOS = QT_VOTOS_NULOS + QT_VOTOS_NULOS_TECNICOS`. No 1º turno de 2026 os nulos técnicos somam 5.246 votos, igual à soma dos votos do candidato nº 28 em `votacao_secao` (conferida à mão, não em código), que os arquivos de seção contam como válidos. Por isso a totalização divulgada tem válidos 119.300.788 e nulos 3.674.249, e as seções têm 119.306.034 e 3.669.003. Em 2022 os nulos técnicos são zero. `make verify` checa essa regra em todas as zonas: qualquer divergência além dela para o pipeline.

Efeito na terceira via: 9.321.993 (11 candidatos) em vez de 9.316.747 (10 candidatos), 0,06%. No 2º turno há dois candidatos.

## Reprodução do baseline (Fase 1)

Nos CSV derivados de 2022 a coluna `flavio` guarda os votos do candidato nº 22 (Jair Bolsonaro).

`make verify` soma os arquivos por seção (27 UFs + exterior `ZZ`) e fecha votação × detalhe. Resultado em 26/10/2026:

| Total | Baseline divulgado (2026: imprensa; 2022: totais do TSE) | Arquivos TSE | Diferença |
|---|---|---|---|
| 1º turno: Lula | 53.879.538 | 53.879.538 | 0 |
| 1º turno: Flávio | 56.104.503 | 56.104.503 | 0 |
| 1º turno: comparecimento | 125.275.835 | 125.275.835 | 0 |
| 1º turno: abstenção (`QT_ABSTENCOES`) | 33.469.244 | 33.469.244 | 0 |
| 1º turno: brancos | 2.300.798 | 2.300.798 | 0 |
| 1º turno: válidos | 119.300.788 | 119.306.034 | +5.246 (candidato nº 28) |
| 1º turno: nulos | 3.674.249 | 3.669.003 | −5.246 (candidato nº 28) |
| 2022, 1º turno: Lula / Bolsonaro | 57.259.504 / 51.072.345 | 57.259.504 / 51.072.345 | 0 |
| 2022, 2º turno: Lula / Bolsonaro | 60.345.999 / 58.206.354 | 60.345.999 / 58.206.354 | 0 |

A abstenção oficial é a coluna `QT_ABSTENCOES`, que não conta 423 dos 495 aptos das 42 seções não instaladas (`aptos − comparecimento` daria 423 a mais). O 2º turno de 2026 ainda não está publicado, então sua linha fica pendente.

## Hora de encerramento por seção (Q6)

Nenhuma coluna de `votacao_secao` ou `detalhe_votacao_secao` traz a hora de encerramento da seção. O detalhe traz `DT_RECEBIMENTO_BU_HOR_TSE` (recebimento do boletim de urna no TSE) e `DT_PRIM_TOT_PARCIAL_HOR_TSE`, que dependem da transmissão e não medem o fechamento. A hora de encerramento consta do boletim de urna (arquivos de urna em `resultados.tse.jus.br`), ainda não avaliado. Decisão sobre Q6: ver pré-registro.

## Pipeline por seção (Fase 2)

`make data` baixa os arquivos (três por ano, com SHA-256 no `MANIFEST.json`), fecha as fontes e, para 2022, grava:

- `data/private/secoes_<ano>.parquet`: uma linha por seção e turno (fora do git).
- `data/derived/municipios_<ano>.csv` e `descartes_<ano>.csv` (seções com votos ou comparecimento em só um turno; ficam fora da tabela municipal), com as regras de publicação abaixo.
- `data/derived/totais_*_<ano>.csv`, gravados por `verify`.

Testes, na ordem em que rodam. Qualquer falha para o pipeline antes de gravar qualquer arquivo:

1. votação × detalhe, por seção (`reconcile`): válidos, brancos, nulos, comparecimento e abstenções. Mesma publicação do TSE, em dois arquivos.
2. soma das seções × `detalhe_votacao_munzona`, por município-zona: agregação feita pelo TSE, portanto a segunda fonte de fato. Cobre aptos, comparecimento, abstenções, brancos, nulos e válidos. **Não cobre votos por candidato** (Lula e Flávio por seção vêm só de `votacao_secao`) e **não verifica** que os nulos técnicos sejam os votos do candidato nº 28: aceita qualquer valor que mantenha as identidades. Conferir candidatos exigiria `votacao_candidato_munzona` (450 a 640 MB por ano).
3. partição: municípios + descartes + aptos de seções não instaladas = total nacional, por turno, para Lula, Flávio, válidos, aptos e comparecimento. Vem do mesmo conjunto de seções: pega erro de pivot, merge ou chave duplicada, não erro de dado.

O hash estável é o de **conteúdo** (`conteudo_sha256` no `run_build_<ano>.json`), não o do arquivo Parquet, que embute a versão da biblioteca; ele depende da versão do polars, registrada junto. O munzona de turnos que não estão nas seções é ignorado (o 2º turno de 2026 não entra antes do pré-registro). Sem o munzona, `verify` e `build` param quando há `MANIFEST.json`. A tabela municipal de 2026 só é gerada com o pré-registro congelado (`make build-2026`).

Regras de publicação em `data/derived` (regra 7):

- `municipios_<ano>.csv` tem Lula, Flávio, válidos, aptos e comparecimento (os insumos do balanço), mais `secoes` (seções ativas nos dois turnos). Município com menos de 10 seções vai para `<UF>-OUTROS`; se esse grupo ficar com menos de 10 seções ou com um só município, absorve o menor município publicado da UF, para que ninguém seja identificável pelo complemento. O exterior (`ZZ`) é a linha `ZZ-EXTERIOR` e não entra nas análises de município (que usam `ALL`, sem `ZZ`). A soma é preservada.
- `descartes_<ano>.csv` é publicado só por turno, sem UF.
- `totais_uf_<ano>.csv` e `totais_nacionais_<ano>.csv` (gravados só por `verify`) são agregados por UF; combinados com a tabela municipal permitem recuperar somas de grupos, mas não de uma seção.

## Saída por seção

Tabelas por seção são gravadas em `data/private/` (fora do git). Em `data/derived/` entram só agregados municipais e por UF.

## Concentração municipal acima de 90% (análise descritiva adicional)

Adicionada em 29/10/2026, depois do pré-registro. Não altera Q1–Q6 nem seus limiares.
`auditoria site` lê `municipios_2022.csv` e `municipios_2026.csv` e calcula, para o
**segundo turno**, `votos do candidato / valid2`. O corte é estrito e usa aritmética
inteira (`10 × votos > 9 × válidos`), antes do arredondamento da apresentação.
Exatamente 90% não entra. Brancos, nulos e abstenção não entram no denominador.

O universo é o da tabela municipal pública: seções presentes nos dois turnos,
municípios publicados individualmente e com votos válidos positivos. Excluem-se
exterior (`ZZ`) e grupos `OUTROS`, inclusive os gerados por supressão complementar.
Logo, a lista não é um censo completo dos municípios, nem necessariamente coincide
com os percentuais da totalização municipal de todas as seções.

A lista une os municípios que passaram do corte em pelo menos um dos anos; cada
coluna mostra o candidato mais votado e os votos válidos daquele ano. A comparação
é por UF e código TSE, sem ajuste de mudanças territoriais. Uma linha municipal
ausente em um ano é “Sem comparação”, nunca zero ou “não passou”. “Nos dois anos”
significa algum candidato acima de 90% em cada ano, não necessariamente a mesma
pessoa. O número de municípios elegíveis é informado separadamente para cada ano.
Não se atribui significância estatística nem irregularidade a esse indicador.

Os nomes são extraídos de `NM_MUNICIPIO` no membro presidencial `_BR.csv` dos ZIP
`detalhe_votacao_munzona` de cada ano, usando os arquivos do mesmo `MANIFEST.json`.
Para reproduzir o cadastro e o painel:

```bash
python -m auditoria.concentracao --raw data/raw --out data/derived
python -m auditoria site --derived data/derived --out site/data/painel.json
```

`nomes_municipios.csv` contém apenas ano, chave municipal e nome;
`fontes_nomes_municipios.json` registra os hashes das fontes e da saída. O registro
da rodada do site inclui hashes das duas tabelas municipais e do cadastro.
Os nomes não dependem de consulta externa no navegador.

A coluna histórica `flavio` dos dados continua sendo uma chave interna para o
candidato nº 22: **Jair Bolsonaro em 2022** e **Flávio Bolsonaro em 2026**. Rótulos,
legendas, textos acessíveis e tabelas HTML usam o nome correspondente ao ano.
As explicações públicas ficam no próprio HTML, em elementos `details` fechados
por padrão, abertos pelo leitor ou pelos links internos de explicação.

## Seções com votação baixa ou concentrada (análise descritiva adicional)

`auditoria distribuicao-secoes` lê e fecha os arquivos de votação, detalhe por seção
 e detalhe município-zona dos dois anos antes de gravar `distribuicao_secoes.json`.
O registro `run_distribuicao-secoes_2026.json` guarda hashes e verificações. A saída
pública contém somente contagens nacionais, por UF e exterior, sem identificar seções.

O universo é **Presidente, segundo turno, seções com pelo menos um voto válido**,
sem pareamento com o primeiro turno e sem mínimo de 50 votos. Chave única:
UF, município, zona e número da seção. Seções sem válidos são contadas à parte como
excluídas, nunca como zero voto para os candidatos. O limite absoluto inclui zero
e dez; as faixas 0, 1–5 e 6–10 somam o total ≤10. O corte proporcional é
`10 × votos > 9 × válidos`, antes de arredondar. Os dois critérios não são equivalentes.

O painel compara frequências em universos de cada eleição; não acompanha as mesmas
seções entre anos. Exterior é selecionável e separado. Mostra também quantas das
seções com ≤10 votos têm ≥50 válidos, quantas têm >90% para o adversário e o mínimo,
a mediana e o máximo de votos válidos desse grupo. Não aplica o teste Q5 a esse recorte.

Na checagem da afirmação de cerca de 3 mil seções, o arquivo de 2026 reproduz 3.042
com Brasil + exterior (3.029 + 13). Para 2022, este recorte produz 4.117, não as
4.118 citadas na página de Wesley Cota consultada em 29/10/2026. A divergência de
uma seção permanece registrada; não se altera o cálculo para forçar concordância.
Fonte da afirmação: https://g.wcota.me/eleicoes2026/distribuicao/.

## Desenvolvimento e partidos das prefeituras (análise descritiva adicional)

Adicionada em 29/10/2026, após o pré-registro, sem alterar Q1–Q6. O cruzamento usa
os municípios individuais elegíveis da base pública de **2026**. A coluna de 2022
é somente uma referência eleitoral: não se atribuem a 2022 os governos de 2024.

Fontes e unidades:

- IDHM municipal de **2010**, Atlas do Desenvolvimento Humano (PNUD/Ipea/FJP),
  série `ADH_IDHM` do [Ipeadata](https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_IDHM')).
  Não é uma estimativa do desenvolvimento em 2026.
- PIB municipal de **2023**, a preços correntes, [SIDRA/IBGE, tabela 5938, variável 37](https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2023).
  A origem está em milhares de reais; a saída multiplica por mil.
- PIB por habitante de **2023**, IBGE, pesquisa 38, indicador 47001, em reais.
  É produção por habitante, não renda recebida por pessoa.
- Prefeitos e partidos da eleição ordinária de **2024**, [cadastro do TSE](https://dadosabertos.tse.jus.br/dataset/candidatos-2024),
  filtrado por cargo 11, situação ELEITO e tipo de eleição 2. Só nomes, partido e
  datas são retidos. Não se presume que partido ou ocupante tenham permanecido até 2026.
- Categorias partidárias da tabela 1 de [Bolognesi, Ribeiro, Codato e Silva (2025)](https://doi.org/10.1590/1807-0191202531120).
  Usa-se a categoria publicada, sem recalculá-la pela média. Centro-esquerda e
  extrema esquerda entram em Esquerda; centro-direita e extrema direita, em Direita;
  Centro permanece separado. A categoria caracteriza o partido nacional, não o
  apoio presidencial ou a posição pessoal do prefeito. Siglas ausentes no estudo,
  como PRD e MOBILIZA, ficam sem classificação. Equivalências de sigla:
  SDD/SOLIDARIEDADE, CDD/CIDADANIA, PROGRE/PP, REP/REPUBLICANOS e PATRI/PATRIOTA.

A ligação TSE–IBGE exige UF e nome coincidentes após normalizar acentos, caixa,
espaços e pontuação. Não há correspondência aproximada: nomes divergentes ficam
sem indicadores. Os indicadores são então unidos pelo código IBGE. O snapshot
registra 13 nomes sem associação; no recorte de 5.239 municípios há também 42 sem
prefeito eleito identificado. Ausência não vira zero nem exclui a cidade da lista.

Nas 11 cidades acima de 90% em 2026, `prefeituras_verificadas.json` registra fontes
institucionais sobre os gestores, a data de referência e a consulta. Essas evidências
datadas não são prova de filiação atual ou de ausência de substituições posteriores;
a coluna partidária continua explicitamente identificada como 2024.

Comparam-se medianas municipais do grupo acima de 90% com o restante, com o mesmo
peso para cada cidade e tamanho amostral por indicador. Para cada bloco partidário,
mostram-se o total elegível, o número acima de 90% e a proporção dentro do bloco.
Spearman usa todos os municípios com o par de dados disponível, com empates por
postos médios, entre o indicador e a participação do **candidato mais votado**.
O gráfico de PIB por habitante usa escala logarítmica. Não há ajuste por região,
população ou outros fatores; associação não estabelece causalidade.

Reprodução, depois de gerar as bases municipais e o cadastro de nomes:

```bash
python -m auditoria distribuicao-secoes --dir data/raw --out data/derived
python -m auditoria.contexto --raw data/external --derived data/derived
python -m auditoria site --derived data/derived --out site/data/painel.json
```

`data/external` é cache local, fora do git. `contexto_municipal.json` contém somente
as variáveis públicas selecionadas; `fontes_contexto.json` guarda URLs, hashes,
data de coleta e faltas de correspondência. O gerador confere o hash do snapshot
e o hash do cadastro municipal usado no cruzamento antes de publicá-lo e registra
as entradas da rodada. O navegador usa dados locais;
não depende das APIs externas para abrir o painel.
