FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
VOLUME /app/data
CMD ["python", "-m", "bot.main"]
