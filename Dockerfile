FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY monitor_dune.py .
CMD ["python", "monitor_dune.py", "--loop"]
