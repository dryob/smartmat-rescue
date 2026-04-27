FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

# Run as a non-root user. Port 80 binding is enabled at container runtime via
# either `cap_add: NET_BIND_SERVICE` or `sysctls: net.ipv4.ip_unprivileged_port_start=80`
# (see docker-compose.yml). /data is writable by this UID.
RUN groupadd --system --gid 1000 smartmat \
 && useradd --system --uid 1000 --gid smartmat --no-create-home --shell /sbin/nologin smartmat \
 && mkdir -p /data \
 && chown -R smartmat:smartmat /app /data

USER smartmat

VOLUME ["/data"]
EXPOSE 80

CMD ["python", "main.py"]
