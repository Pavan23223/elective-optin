#!/usr/bin/env bash
# Render build script — runs once on every deploy

set -o errexit   # exit on any error

pip install --upgrade pip
pip install -r requirements.txt

# Collect static files
python elective_optin/manage.py collectstatic --no-input

# Apply database migrations
python elective_optin/manage.py migrate
