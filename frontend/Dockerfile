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
# BACKEND_URL is used by next.config.ts rewrites at build time
ARG BACKEND_URL=http://backend:8001
ENV BACKEND_URL=${BACKEND_URL}
ENV NEXT_PUBLIC_API_URL=
RUN npm run build

# ── Stage 4: Production Runner ────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# Copy built assets from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
