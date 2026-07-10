FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
RUN mkdir -p /data
EXPOSE 3000
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
