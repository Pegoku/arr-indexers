FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARR_INDEXERS_HOST=0.0.0.0 \
    ARR_INDEXERS_PORT=9697

WORKDIR /app

COPY pyproject.toml ./
COPY arr_indexers ./arr_indexers

RUN addgroup -S arrindexers \
    && adduser -S -G arrindexers arrindexers

USER arrindexers

EXPOSE 9697

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9697/health', timeout=3).read()"

CMD ["python", "-m", "arr_indexers"]
