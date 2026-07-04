FROM python:3.12

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

ENV PYTHONUNBUFFERED=1

# Hosts (Render/Railway/Fly) inject $PORT; default to 8080 locally.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
