FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000


# Turbopack (the default `next dev` bundler) has no native binding for linux/arm64 yet, only a
# WASM fallback that doesn't support Turbopack — this only affects Docker (Apple Silicon hosts
# have native Turbopack support). Fall back to Webpack here specifically.
CMD ["npm", "run", "dev", "--", "--webpack"]
