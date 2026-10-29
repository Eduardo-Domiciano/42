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
- Portas: **80:80** e **443:443** (nunca `80:8080`).
- App entra na `edge` via `../docker-compose.edge.yml` (sem publish :8080).
- Socket: `/var/run/docker.sock` (Docker Engine na VPS).
- Limites padrão: **0.25 CPU** + **1 GiB**; rate limit + in-flight.
