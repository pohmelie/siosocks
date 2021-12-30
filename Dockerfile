FROM python:3.10-slim
COPY . /siosocks
RUN pip install -e /siosocks
ENTRYPOINT ["python", "-m", "siosocks"]
