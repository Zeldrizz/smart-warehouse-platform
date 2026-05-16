FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc librdkafka-dev && \
    rm -rf /var/lib/apt/lists/*

COPY wms_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wms_service/app ./app
COPY common ./common
COPY schemas ./schemas

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
