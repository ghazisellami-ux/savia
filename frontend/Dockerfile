# ==========================================
# 🎨 Dockerfile — SAVIA Next.js Frontend
# ==========================================

# ── Stage 1: Dependencies ─────────────────
FROM node:20-alpine AS deps
# libc6-compat doesn't exist in Alpine, using build tools instead for Next.js
RUN apk add --no-cache python3 make g++
WORKDIR /app
COPY package.json package-lock.json* ./
# On force l'installation de TOUTES les dépendances (y compris devDeps)
# Try alternative npm registry if default fails
RUN npm ci --include=dev --registry https://registry.npmmirror.com || \
    npm ci --include=dev

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
FROM node:20-alpine AS runner
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
