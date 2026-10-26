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

Essa definição difere em 5.246 votos da totalização divulgada no 1º turno de 2026 (válidos 119.306.034 contra 119.300.788; nulos 3.669.003 contra 3.674.249). Os 5.246 são os votos do candidato nº 28, que constam como válidos nos arquivos de seção e como nulos na totalização divulgada. Efeito: terceira via de 9.321.993 (11 candidatos) em vez de 9.316.747 (10 candidatos). Os 5.246 são 0,06% da terceira via. No 2º turno há dois candidatos, então não há efeito equivalente.

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

## Saída por seção

Tabelas por seção são gravadas em `data/private/` (fora do git). Em `data/derived/` entram só agregados municipais e por UF.
