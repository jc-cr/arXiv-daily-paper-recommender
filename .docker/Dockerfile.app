# Dockerfile
FROM python:3.10

WORKDIR /app
RUN chmod 777 /app

# Install dependencies
RUN pip install python-dotenv


RUN pip install --no-cache-dir \
    quart \
    quart-cors \
    msgpack \
    pyzmq \
    requests \