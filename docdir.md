# ④②

App Brasil-first (`veracidade-noticias/`) para coletar notícias, analisar fontes e buscar por URL ou tema+período.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `README.md` | Como subir backend, frontend e Docker. |
| `.gitignore` | Ignora `_reference/`, `.cursor/`, venv, node_modules e bancos locais. |
| `docker-compose.yml` | Backend + frontend; publica `HOST_PORT` (modo IP/local). |
| `docker-compose.edge.yml` | Overlay Traefik/HTTPS (só com `DOMAIN`). |
| `.env.example` | Exemplo de variáveis de ambiente do app. |
| `42.cd.env.example` | Modelo opcional para `~/42.cd.env` (IP ou domínio). |

## Subpastas

| Pasta | O que guarda |
| --- | --- |
| `backend/` | API FastAPI, modelos e seed de fontes BR. |
| `frontend/` | App Angular com a tela de busca. |
| `docs/` | Modelo de `docdir` do projeto. |
| `img/` | Ícones e imagens de referência (ex.: GitHub). |
| `google_gemma-4-e4b_current/` | Referência de modelo (não usada no runtime). |
| `_reference/` | Cópias locais dos projetos originais (fora do Git). |
| `.github/` | Workflows de CI e CD (GitHub Actions). |
| `test/` | Validação local de CI/CD antes do push. |
| `traefik/` | Proxy de borda Traefik (HTTPS na VPS). |

## Observacoes

- Os projetos originais em `../` permanecem intactos.
- `_reference/` existe só para consulta local e está no `.gitignore`.
