# scripts

Utilitários CLI do backend (importações e jobs pontuais).

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `import_leis.py` | Importa frontmatter de `leis-main` (CF + federal) para `normas` / FTS. |
| `docdir.md` | Documenta esta pasta. |

## Observacoes

- Não roda no startup da API — executar sob demanda (`python -m scripts.import_leis`).
