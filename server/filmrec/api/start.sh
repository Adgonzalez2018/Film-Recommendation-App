#!/usr/bin/env bash
set -o errexit

python manage.py migrate
python manage.py seed_tmdb_test
python manage.py bootstrap

exec gunicorn filmrec.wsgi:application