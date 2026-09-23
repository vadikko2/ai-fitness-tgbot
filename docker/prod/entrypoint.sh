#!/bin/sh
set -eu

alembic upgrade head
seed-measurement-guides --offline --force
exec fitness-bot
