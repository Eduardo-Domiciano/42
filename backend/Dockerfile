FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# INSTALL_NN=1 instala torch/transformers (imagem bem maior)
ARG INSTALL_NN=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-nn.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_NN" = "1" ]; then pip install --no-cache-dir -r requirements-nn.txt; fi

COPY app ./app
COPY source_profiles.yml ./source_profiles.yml
COPY catalog ./catalog

RUN mkdir -p /data

ENV DATABASE_URL=sqlite:////data/veracidade.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
