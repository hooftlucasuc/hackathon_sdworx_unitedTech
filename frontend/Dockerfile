# CallSight dashboard for Cloud Run. Build context: frontend/
# VITE_* values are baked in at build time (Vite inlines them); pass them as build args.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_DATA_SOURCE=mock
ARG VITE_API_BASE=http://localhost:8080
ARG VITE_LISTENER_URL=
ARG VITE_DEMO_MODE=true
ARG VITE_FIREBASE_API_KEY=
ARG VITE_FIREBASE_AUTH_DOMAIN=
ARG VITE_FIREBASE_PROJECT_ID=
ARG VITE_FIREBASE_APP_ID=
ARG VITE_FIREBASE_ANON_AUTH=true
ENV VITE_DATA_SOURCE=$VITE_DATA_SOURCE VITE_API_BASE=$VITE_API_BASE VITE_DEMO_MODE=$VITE_DEMO_MODE \
    VITE_LISTENER_URL=$VITE_LISTENER_URL \
    VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID \
    VITE_FIREBASE_ANON_AUTH=$VITE_FIREBASE_ANON_AUTH
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# Cloud Run sends traffic to 8080
EXPOSE 8080
