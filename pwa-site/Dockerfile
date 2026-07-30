FROM node:20-alpine AS builder
# libc6-compat doesn't exist in Alpine, using glibc compatibility layer instead
RUN apk add --no-cache python3 make g++
RUN npm install --global npm@11.6.3
WORKDIR /app

COPY package.json package-lock.json* ./

# A failed install must stop the build. The assertion prevents npm from
# continuing after an internal error without having installed Next.js.
RUN npm ci --include=dev --fetch-timeout=180000 --fetch-retries=10 --no-audit --fund=false && \
    test -x node_modules/.bin/next

COPY . .

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3001
# Optional: Disable Next.js telemetry during runtime for better performance
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3001

CMD ["node", "server.js"]
