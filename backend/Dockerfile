FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml .
COPY app app
RUN pip install --no-cache-dir .

# Keep the SQLite file on a volume so runs survive container restarts.
ENV DATABASE_PATH=/data/switchboard.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
