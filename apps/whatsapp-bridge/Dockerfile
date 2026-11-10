FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src ./src
# Session keys are as sensitive as an SSH key: a named volume owned by the unprivileged user, mode 0700.
RUN mkdir -p /data/session && chown -R node:node /data && chmod 700 /data/session
USER node
CMD ["node", "src/main.mjs"]
