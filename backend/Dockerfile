FROM docker.mirrors.ustc.edu.cn/library/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional but helps common wheels/ssl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source (includes static/vue build)
COPY . /app

EXPOSE 5001

# Persist sqlite DB under /app/data (mount this in docker run)
VOLUME ["/app/data"]

CMD ["python", "app.py"]

FROM python:3.10-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5001

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]

