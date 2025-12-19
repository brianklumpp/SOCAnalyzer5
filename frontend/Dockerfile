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
# Set production environment variables for Vite build
# Empty VITE_API_BASE means use relative URLs (nginx proxy)
ENV NODE_ENV=production
ENV VITE_API_BASE=
ENV VITE_WS_BASE=
# Debug: Print environment to verify
RUN echo "=== Build Environment ===" && \
    echo "NODE_ENV=$NODE_ENV" && \
    echo "VITE_API_BASE=$VITE_API_BASE" && \
    echo "VITE_WS_BASE=$VITE_WS_BASE"
# Vite build is fast and efficient - no memory issues!
RUN npm run build && ls -la /app/build && echo "Build directory contents:" && ls -la /app/build/ || echo "Build failed!"

# Production stage with nginx
FROM nginx:alpine AS prod
# Cache buster 2025-12-18-v2
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]


