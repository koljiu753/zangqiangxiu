FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_CATALOG_API_BASE_URL
ARG NEXT_PUBLIC_AI_API_BASE_URL
ARG NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
ENV NEXT_PUBLIC_CATALOG_API_BASE_URL=$NEXT_PUBLIC_CATALOG_API_BASE_URL \
    NEXT_PUBLIC_AI_API_BASE_URL=$NEXT_PUBLIC_AI_API_BASE_URL \
    NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=$NEXT_PUBLIC_ALLOW_DEMO_FALLBACK \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
