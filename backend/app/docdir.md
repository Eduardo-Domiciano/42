# app

Pacote principal da API FastAPI.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `__init__.py` | Marca o pacote. |
| `config.py` | Configurações e caminhos. |
| `db.py` | Engine SQLAlchemy e sessão. |
| `main.py` | App FastAPI, CORS e seed no startup. |
| `schemas.py` | Contratos Pydantic da API. |
| `db_migrate.py` | ALTER TABLE leve para novas colunas no SQLite. |

## Subpastas

| Pasta | O que guarda |
| --- | --- |
| `api/` | Rotas HTTP. |
| `models/` | Entidades do banco. |
| `services/` | Seed, fetch, busca por tema e análise. |
