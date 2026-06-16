# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + serve everything ────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built React (served as static files by FastAPI)
COPY --from=frontend-build /app/dist ./frontend/dist

# scripts/configs/results are mounted as volumes at runtime
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
