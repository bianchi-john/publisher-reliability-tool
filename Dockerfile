FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PRT_CONTAINER_INTERNAL=true

WORKDIR /app
RUN addgroup --gid 10001 app && adduser --uid 10001 --gid 10001 --disabled-password app

COPY requirements.lock pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .

COPY --chown=10001:10001 dataset ./dataset
COPY --chown=10001:10001 models/README.md ./models/README.md

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["publisher-reliability"]
CMD ["serve", "--port", "8000", "--data-dir", "/data", "--models-dir", "/models", "--seed-dataset", "/app/dataset/predictions"]
