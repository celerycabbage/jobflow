FROM python:3.14-slim

WORKDIR /app
COPY pyproject.toml constraints.lock ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir --constraint constraints.lock .

EXPOSE 8000
CMD ["sh", "-c", "python -m app.wait_for_database && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
