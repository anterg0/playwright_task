FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    apache2-dev \
    gcc \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN mod_wsgi-express module-config > /etc/apache2/mods-available/wsgi.load \
    && a2enmod wsgi

COPY web_service.py app.wsgi apply_zoom.py test_web_service.py worker.py ./

COPY apache-vhost.conf /etc/apache2/sites-available/000-default.conf

RUN mkdir -p /app/uploads \
    && chown -R www-data:www-data /app/uploads

EXPOSE 80

CMD ["apachectl", "-D", "FOREGROUND"]
