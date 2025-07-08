# ─── Build Astro Frontend ───────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

COPY frontend/ .
RUN npm run build


# ─── Build FastAPI Backend ──────────────────────────
FROM python:3.10-slim AS backend

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y build-essential

# Backend requirements
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY api/ .

# Copy backend code
COPY api/ .

# Copy normalized images
COPY scraper/normalized scraper/normalized


# Copy frontend static build into backend folder
COPY --from=frontend-builder /app/frontend/dist ./static

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port", "8000"]
