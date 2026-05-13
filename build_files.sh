#!/bin/bash
# Vercel ejecuta este script como Build Command
export UV_LINK_MODE=copy
pip install -r requirements.txt --break-system-packages
python manage.py collectstatic --noinput
