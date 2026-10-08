FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY presets ./presets
COPY data ./data
COPY mocksites ./mocksites
COPY Makefile ./Makefile

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////data/lead_engine.db
ENV MOCK_SITES_BASE_URL=http://mocksites:8081

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
