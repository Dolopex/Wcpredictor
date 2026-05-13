#!/bin/bash
# Vercel ejecuta este script como Build Command
pip install -r requirements.txt --break-system-packages
python manage.py collectstatic --noinput
