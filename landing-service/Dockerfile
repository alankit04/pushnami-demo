FROM python:3.12-slim
WORKDIR /app
COPY app.py ./
COPY static ./static
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["python", "app.py"]
