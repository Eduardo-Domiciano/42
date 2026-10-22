FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npx ng build --configuration=production

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
# Arquivos vindos do host podem vir sem permissão de leitura para o user nginx
RUN chmod -R a+rX /usr/share/nginx/html

EXPOSE 80
