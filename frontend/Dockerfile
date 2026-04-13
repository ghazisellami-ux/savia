# ==========================================
# 🐳 Dockerfile — SAVIA Next.js Frontend
# ==========================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy all files and build
COPY . .
RUN npm run build

# Production image
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=http://localhost:8000

# Copy built assets from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
