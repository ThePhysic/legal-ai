#!/bin/sh
set -eu
alembic -c migrations/alembic.ini upgrade head
exec uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log
