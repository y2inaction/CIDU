FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-postgres.txt .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt
COPY . .
RUN mkdir -p instance seeds static
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import requests;r=requests.get('http://localhost:5000/api/health');exit(0 if r.status_code==200 else 1)" || exit 1
CMD ["sh","-c","flask db upgrade && gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 --access-logfile - --error-logfile - 'app:application'"]
