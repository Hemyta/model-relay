FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system relay && adduser --system --ingroup relay relay

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app ./app


FROM base AS test

COPY tests ./tests

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]


FROM base AS runtime

USER relay
EXPOSE 7500

CMD ["python", "-m", "app"]