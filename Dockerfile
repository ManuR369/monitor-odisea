FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app
COPY monitor_odisea.py .
RUN pip install playwright==1.62.0 requests

CMD ["python", "monitor_odisea.py", "--loop"]
