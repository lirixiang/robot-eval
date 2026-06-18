# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + serve everything ────────────────────────────────
FROM python:3.12.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
RUN chmod +x /app/backend/entrypoint.sh

COPY --from=frontend-build /app/dist ./frontend/dist

CMD ["/app/backend/entrypoint.sh"]
