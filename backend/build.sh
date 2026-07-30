#!/usr/bin/env bash
# Backend build step for production (e.g. Render "Build Command").
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input --settings=config.settings.prod
python manage.py migrate --no-input --settings=config.settings.prod
