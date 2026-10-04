# The web app: one image to check it, one to serve it.

FROM node:24-alpine AS source
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .

# The gate: types, lint, format, tests. `docker compose run --rm --build web-test`.
FROM source AS test
CMD ["npm", "run", "check"]

FROM source AS build
RUN npm run build

# A static build behind Caddy — no Node process in production (PLAN decision 13).
FROM caddy:2-alpine AS runtime
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
