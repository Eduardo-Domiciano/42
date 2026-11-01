# frontend

Interface Angular para buscar notícias por URL ou tema+período e ver o resultado.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `package.json` | Scripts e dependências npm. |
| `angular.json` | Configuração do Angular CLI. |
| `Dockerfile` | Build Angular + imagem Nginx. |
| `nginx.conf` | UI + proxy `/api` → `backend:8000` (`$request_uri` + DNS Docker). |
| `.dockerignore` | Arquivos excluídos do build da imagem. |

## Subpastas

| Pasta | O que guarda |
| --- | --- |
| `src/` | Código da aplicação Angular. |
| `public/` | Assets estáticos (favicon, imagem do hero). |
