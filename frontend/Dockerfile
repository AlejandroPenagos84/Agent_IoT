# Build del frontend (Vite) y servidor nginx con el resultado estático.
# La configuración de nginx se monta desde deploy/nginx/default.conf.
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Mismo origen que la API: el navegador llama a /api/v1 y nginx lo reenvía.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
