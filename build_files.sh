#!/bin/bash
# Script de build ejecutado por Vercel al hacer deploy

pip install -r requirements.txt
python manage.py collectstatic --noinput
