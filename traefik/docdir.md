# traefik

Proxy de borda (Traefik) na VPS: HTTPS (Let's Encrypt), roteamento Docker e dashboard.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `docker-compose.yml` | Sobe Traefik (v3.6.4+) nas portas 80/443; usa rede `edge` externa. |
| `.env.example` | E-mail ACME, host do dashboard e senha htpasswd. |
| `docdir.md` | Este arquivo. |

## Observacoes

- Sobe com o app via `../docker-compose.edge.yml` (`include` deste compose).
- Auth/dashboard: `../.env` e/ou `.env` (`TRAEFIK_DASHBOARD_AUTH` com `$$`).
- Painel: **http://IP/dashboard/** (basic auth).
- Portas: **80:80** e **443:443** (nunca `80:8080`).
- Socket: `/var/run/docker.sock` (Docker Engine na VPS).

