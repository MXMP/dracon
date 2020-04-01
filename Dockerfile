FROM python:3-alpine as base

FROM base as builder
RUN apk update
RUN apk add postgresql-dev gcc python3-dev musl-dev libffi-dev libpq
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

FROM builder
COPY . /app
WORKDIR /app

EXPOSE 20/tcp
EXPOSE 21/tcp
EXPOSE 69/udp

CMD ["python", "dracon.py", "nodaemon"]