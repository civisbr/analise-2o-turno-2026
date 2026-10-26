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

Nos CSV derivados de 2022 a coluna `flavio` guarda os votos do candidato nº 22 (Bolsonaro).

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

O hash estável é o de **conteúdo** (`conteudo_sha256` no `run_build_<ano>.json`), não o do arquivo Parquet, que embute a versão da biblioteca; ele depende da versão do pandas, registrada junto. O munzona de turnos que não estão nas seções é ignorado (o 2º turno de 2026 não entra antes do pré-registro). Sem o munzona, `verify` e `build` param quando há `MANIFEST.json`. A tabela municipal de 2026 só é gerada com o pré-registro congelado (`make build-2026`).

Regras de publicação em `data/derived` (regra 7):

- `municipios_<ano>.csv` tem Lula, Flávio, válidos, aptos e comparecimento (os insumos do balanço), mais `secoes` (seções ativas nos dois turnos). Município com menos de 10 seções vai para `<UF>-OUTROS`; se esse grupo ficar com menos de 10 seções ou com um só município, absorve o menor município publicado da UF, para que ninguém seja identificável pelo complemento. O exterior (`ZZ`) é a linha `ZZ-EXTERIOR` e não entra nas análises de município (que usam `ALL`, sem `ZZ`). A soma é preservada.
- `descartes_<ano>.csv` é publicado só por turno, sem UF.
- `totais_uf_<ano>.csv` e `totais_nacionais_<ano>.csv` (gravados só por `verify`) são agregados por UF; combinados com a tabela municipal permitem recuperar somas de grupos, mas não de uma seção.

## Saída por seção

Tabelas por seção são gravadas em `data/private/` (fora do git). Em `data/derived/` entram só agregados municipais e por UF.
