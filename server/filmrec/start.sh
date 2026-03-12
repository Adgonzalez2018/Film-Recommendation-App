#!/usr/bin/env bash
set -o errexit

python manage.py migrate

exec gunicorn filmrec.wsgi:application