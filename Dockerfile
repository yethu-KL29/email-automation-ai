FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY alembic ./alembic
COPY dashboard ./dashboard
RUN useradd --create-home app && mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8000 8501
CMD ["uv", "run", "--no-sync", "uvicorn", "job_outreach.main:app", "--host", "0.0.0.0", "--port", "8000"]
