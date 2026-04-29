FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-install build deps for youtokentome (требует Cython при сборке wheel)
RUN pip install --upgrade pip setuptools wheel Cython
RUN pip install --no-build-isolation youtokentome==1.0.6

# ruclip ставим без зависимостей — иначе он тащит huggingface-hub==0.2.1
# с багом ETag. Совместимый huggingface-hub придёт из requirements.txt.
RUN pip install --no-deps ruclip==0.0.2

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY src ./src
COPY image.png ./image.png

CMD ["python", "-m", "src.bot"]
