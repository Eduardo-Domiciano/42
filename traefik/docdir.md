# traefik

Proxy de borda (Traefik) na VPS: HTTPS (Let's Encrypt), roteamento Docker e dashboard.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `docker-compose.yml` | Sobe Traefik nas portas 80/443 e cria a rede `edge`. |
| `.env.example` | E-mail ACME, host do dashboard e senha htpasswd. |
| `docdir.md` | Este arquivo. |

## Observacoes

- Preencha `.env` a partir do `.env.example` antes do `up`.
- O frontend do 42 já está na rede `edge` via `../docker-compose.yml`.
- Socket: `/var/run/docker.sock` (Docker Engine na VPS).
- Limites padrão: **0.25 CPU** (1/4 core) e **1 GiB RAM**; rate limit + in-flight contra brute force.
