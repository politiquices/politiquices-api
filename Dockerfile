# syntax=docker/dockerfile:1

FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt requirements.txt

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=src

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
