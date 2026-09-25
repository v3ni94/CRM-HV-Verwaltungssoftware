# U-Protokoll (Uebergabe-/Abnahmeprotokoll, PHP 8.2) als Container im MHVP-Stack.
# Build-Kontext ist apps/u-protokoll (siehe infra/compose.dev.yaml und scripts/deploy.sh).

FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-interaction --no-progress --optimize-autoloader

FROM php:8.2-apache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libpng-dev \
        libwebp-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j"$(nproc)" gd pdo_mysql \
    && rm -rf /var/lib/apt/lists/*

# Webroot ist public/; Rewrites und Security-Header kommen aus den .htaccess-Dateien der App.
ENV APACHE_DOCUMENT_ROOT=/var/www/html/public
RUN a2enmod rewrite headers \
    && sed -ri -e 's!/var/www/html!${APACHE_DOCUMENT_ROOT}!g' /etc/apache2/sites-available/*.conf \
    && printf '<Directory ${APACHE_DOCUMENT_ROOT}>\n    AllowOverride All\n    Require all granted\n</Directory>\n' \
        > /etc/apache2/conf-available/z-uprotokoll.conf \
    && a2enconf z-uprotokoll

RUN { \
        echo 'upload_max_filesize=32M'; \
        echo 'post_max_size=40M'; \
        echo 'memory_limit=256M'; \
        echo 'expose_php=Off'; \
    } > /usr/local/etc/php/conf.d/uprotokoll.ini

COPY . /var/www/html
COPY --from=vendor /app/vendor /var/www/html/vendor

# Uploads/Logs/Cache liegen auf einem Volume (compose); Rechte fuer www-data vorbereiten.
RUN mkdir -p /var/www/html/storage/uploads /var/www/html/storage/logs /var/www/html/storage/cache \
    && chown -R www-data:www-data /var/www/html/storage
