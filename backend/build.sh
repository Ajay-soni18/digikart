#!/usr/bin/env bash
# Render (and most PaaS) build step. Runs on every deploy, BEFORE the release
# command in the Procfile — so migrations are not here; they belong there, where
# they run once against the live database rather than once per build.
#
# `set -o errexit` matters: without it a failed pip install still exits 0 and
# the host happily starts a broken container.
set -o errexit
set -o pipefail
set -o nounset

pip install --upgrade pip
pip install -r requirements.txt

# WhiteNoise serves these; STATIC_ROOT is backend/staticfiles. Only Django's own
# admin CSS lives here — the storefront is a separate static deploy.
python manage.py collectstatic --no-input --settings=config.settings.prod
