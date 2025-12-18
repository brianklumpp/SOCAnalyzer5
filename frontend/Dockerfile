# syntax=docker/dockerfile:1

# Development stage with Vite dev server
FROM node:18-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
EXPOSE 3000
CMD ["npm", "start", "--", "--host", "0.0.0.0"]

# Build stage with Vite
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY . ./
# Vite build is fast and efficient - no memory issues!
RUN npm run build

# Production stage with nginx
FROM nginx:alpine AS prod
# Cache buster 2025-12-13-18:59
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]


