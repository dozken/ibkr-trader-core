FROM oven/bun:latest AS builder
WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .

# NO VITE_IBKR_API_KEY build ARG. Vite inlines VITE_* vars into the hashed
# bundle, so accepting the key here put a live credential inside the published
# image and made rotation require a rebuild. It is injected at container start
# instead — see docker-entrypoint.sh.

# Skip typecheck in Docker (tsgo native binary may not match platform);
# types are checked during dev, not production builds.
RUN bunx --bun vite build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
