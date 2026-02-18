FROM python:3.12-slim
WORKDIR /app
COPY app.py ./
RUN useradd -m appuser && mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser
EXPOSE 5002
CMD ["python", "app.py"]
