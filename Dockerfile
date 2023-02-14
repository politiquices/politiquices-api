# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

WORKDIR /app

COPY requirements.txt requirements.txt

RUN apt-get update

RUN apt-get install -y --no-install-recommends build-essential

RUN pip3 install -r requirements.txt

COPY . .

CMD uvicorn main:app --host 0.0.0.0 --port 8000
