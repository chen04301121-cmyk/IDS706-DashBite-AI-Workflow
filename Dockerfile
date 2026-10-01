# Based on docs/docker-k8s-guide.md, Part 1.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/ pipeline/
COPY scripts/check_artifacts.py scripts/check_persistence.py scripts/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 DATA_ROOT=/app/data
CMD ["python", "-m", "pipeline.simulator"]
