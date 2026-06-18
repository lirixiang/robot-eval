#!/usr/bin/env bash
set -e

ENV_FILE="/app/.env"

# Auto-generate HOST_SECRET_KEY if not already present
if [ -z "${HOST_SECRET_KEY}" ]; then
  if grep -q "^HOST_SECRET_KEY=" "$ENV_FILE" 2>/dev/null; then
    export HOST_SECRET_KEY=$(grep "^HOST_SECRET_KEY=" "$ENV_FILE" | cut -d= -f2-)
  else
    KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    echo "HOST_SECRET_KEY=${KEY}" >> "$ENV_FILE"
    export HOST_SECRET_KEY="$KEY"
    echo "[entrypoint] Generated new HOST_SECRET_KEY"
  fi
fi

exec gunicorn backend.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --graceful-timeout 30
