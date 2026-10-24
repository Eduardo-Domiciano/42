# Catálogo de bias editorial (Brasil)

Arquivo de dados: [`backend/catalog/bias_br.yml`](../backend/catalog/bias_br.yml)

## O que é

Julgamento **curado e versionado** da orientação editorial / papel institucional de veículos e órgãos usados pelo app. Serve para:

- comparar framing entre fontes
- agrupar ownership (mesmo grupo = uma voz)
- explicitar parcialidade possível da fonte

**Não** prova se uma notícia é verdadeira ou falsa.

## Escala

| `bias_label` | `bias_score` (aprox.) | Significado |
| --- | --- | --- |
| `institutional` | `0.0` | Órgão oficial / estatística / norma |
| `left` | ≈ −0.6 a −1.0 | Linha progressista/esquerda explícita |
| `center_left` | ≈ −0.2 a −0.5 | Centro-esquerda |
| `center` | ≈ −0.15 a +0.15 | Mainstream / pouco alinhamento partidário óbvio |
| `center_right` | ≈ +0.2 a +0.45 | Centro-direita |
| `right` | ≈ +0.5 a +1.0 | Linha conservadora/direita explícita |
| `unknown` | `null` | Fora do catálogo |

## Versionamento

Campo `version` no YAML. Ao mudar scores, incremente (ex.: `1.0.0` → `1.1.0`) e atualize `updated_at`. O seed grava `bias_catalog_version` em cada `Source`.

## Fontes oficiais e temas

Perfis `primary` em [`backend/source_profiles.yml`](../backend/source_profiles.yml) podem ter `topics` (ex.: `economia`, `saude`). O seed grava isso em `Source.topics`. No cruzamento F4, a busca web prioriza `site:` dos oficiais cujo tema bate com o claim (lexicon em `topic_officials.py`). Oficiais usam `bias_label: institutional`.

## Como revisar

1. Edite `backend/catalog/bias_br.yml` (e/ou `source_profiles.yml` para hosts/topics)
2. Suba a API (o seed reaplica no startup)
3. Documente a motivação no `note` da fonte
