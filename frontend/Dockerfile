# ==========================================
# 🎨 Dockerfile — SAVIA Next.js Frontend
# ==========================================
# Multi-stage: dev & production séparés
#
# Usage:
#   Production : docker build --target runner -t savia-frontend .
#   Dev        : docker build --target dev -t savia-frontend-dev .

# ── Stage 1: Dependencies ─────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ── Stage 2: Development ──────────────────
# Usage: docker compose -f docker-compose.yml -f docker-compose.dev.yml up
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
# NEXT_PUBLIC_* vars are baked at build time
# Empty = frontend uses relative URLs (Nginx proxies /api/* to backend)
ENV NEXT_PUBLIC_API_URL=
RUN npm run build

# ── Stage 4: Production Runner ────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copy built assets from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
