FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN KERFUFFLE_FRONTEND_ZONE=public npm run build -- --outDir dist-public \
    && KERFUFFLE_FRONTEND_ZONE=admin npm run build -- --outDir dist-admin

FROM nginx:1.27-alpine AS frontend-public
COPY deploy-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist-public /usr/share/nginx/html

FROM nginx:1.27-alpine AS frontend-admin
COPY deploy-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist-admin /usr/share/nginx/html

EXPOSE 80
