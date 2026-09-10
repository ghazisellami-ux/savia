# syntax=docker/dockerfile:1.7
# ==========================================
# 🎨 Dockerfile — SAVIA Next.js Frontend
# ==========================================

# ── Stage 1: Dependencies ─────────────────
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS deps
# libc6-compat doesn't exist in Alpine, using build tools instead for Next.js
RUN apk add --no-cache python3 make g++
RUN npm install --global npm@11.6.3
WORKDIR /app
COPY package.json package-lock.json* ./
# On force l'installation de TOUTES les dépendances (y compris devDeps)
# Try alternative npm registry if default fails
RUN --mount=type=cache,id=savia-next-frontend-npm,target=/root/.npm,sharing=locked \
    npm ci --include=dev --prefer-offline --fetch-timeout=180000 --fetch-retries=10 --no-audit --fund=false && \
    test -x node_modules/.bin/next

# ── Stage 2: Development ──────────────────
FROM deps AS dev
WORKDIR /app
COPY . .
ENV NODE_ENV=development
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ── Stage 3: Build (production) ───────────
FROM deps AS builder
WORKDIR /app
COPY . .

# On récupère les arguments de build passés par Coolify
ARG BACKEND_URL=http://backend:8001
ENV BACKEND_URL=${BACKEND_URL}

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 4: Production Runner ────────────
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
ENV NEXT_TELEMETRY_DISABLED=1

# Récupération des assets optimisés
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
