FROM python:3.11-slim

WORKDIR /tests

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc librdkafka-dev && \
    rm -rf /var/lib/apt/lists/*

COPY tests/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tests/. .

CMD ["pytest", "-v", "--tb=short", "-s", "integration", "e2e"]
