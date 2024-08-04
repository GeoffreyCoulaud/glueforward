FROM python:3.12-slim
COPY glueforward /glueforward
WORKDIR /glueforward
RUN pip install -r requirements.txt
CMD ["python", "main.py"]