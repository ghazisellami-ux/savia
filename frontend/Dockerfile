# ==========================================
# 🐳 Dockerfile — SAVIA Next.js Frontend
# ==========================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy all files
COPY . .

# NEXT_PUBLIC_* vars are baked at build time — set empty so frontend uses relative URLs
# (Nginx proxies /api/* to the backend, no hardcoded host needed)
ENV NEXT_PUBLIC_API_URL=

RUN npm run build

# Production image
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Copy built assets from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
