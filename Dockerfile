# ---------- stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /fe/dist

# ---------- stage 2: runtime (FastAPI serves API + built UI) ----------
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./static

# Run as non-root (Cloud Run best practice).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER 10001

# Cloud Run injects PORT (default 8080).
ENV PORT=8080
EXPOSE 8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
