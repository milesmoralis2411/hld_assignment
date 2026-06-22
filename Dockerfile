# Search Typeahead System - container image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (data/ is created at runtime; the dataset is fetched on first start).
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/
COPY run.py ./

EXPOSE 8000

# Bind to 0.0.0.0 so the server is reachable from outside the container.
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]

# First start downloads the dataset + builds the index, so allow a generous
# start period before health checks count failures.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"
