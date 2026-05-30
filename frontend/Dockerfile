FROM oven/bun:latest AS builder
WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .

ARG VITE_IBKR_API_KEY=""
ENV VITE_IBKR_API_KEY=$VITE_IBKR_API_KEY

# Skip typecheck in Docker (tsgo native binary may not match platform);
# types are checked during dev, not production builds.
RUN bunx --bun vite build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
