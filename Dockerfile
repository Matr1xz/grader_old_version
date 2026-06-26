FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVER=http://10.170.100.83:80 \
    JUDGE_ID=PTIT3 \
    JUDGE_KEY=PTIT3 \
    LOG_FILE=/app/judge.log \
    LOG_SIZE=20M \
    LOG_ROTATE=3 \
    LOGROTATE_INTERVAL=60

RUN apt-get update \
    && apt-get install -y --no-install-recommends logrotate procps \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r grader \
    && useradd -r -g grader -d /app -s /bin/bash grader

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app/ /app/
COPY entrypoint.sh /usr/local/bin/grader1-entrypoint.sh

RUN chmod +x /usr/local/bin/grader1-entrypoint.sh \
    && mkdir -p /app/tmp/labs /app/tmp/locks /app/.local/pregrade \
    && touch /app/judge.log \
    && chown -R grader:grader /app

ENTRYPOINT ["/usr/local/bin/grader1-entrypoint.sh"]
