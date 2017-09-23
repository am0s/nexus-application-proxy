FROM python:3-alpine
MAINTAINER Jan Borsodi <jborsodi@gmail.com>

EXPOSE 80 443
VOLUME /etc/letsencrypt /var/lib/letsencrypt
WORKDIR /opt/

RUN apk add --no-cache curl
RUN curl -L https://github.com/certbot/certbot/archive/v0.18.1.tar.gz >/tmp/certbot.tar.gz
RUN ls -l /tmp/certbot.tar.gz && tar xfz /tmp/certbot.tar.gz && mv certbot-0.18.1 certbot
WORKDIR /opt/certbot
RUN mkdir src && \
    cp -R CHANGES.rst README.rst setup.py src/ && \
    cp -R acme src/acme && \
    cp -R certbot src/certbot

RUN apk add --no-cache --virtual .certbot-deps \
        libffi \
        libssl1.0 \
        ca-certificates \
        binutils
RUN apk add --no-cache --virtual .build-deps \
        gcc \
        linux-headers \
        openssl-dev \
        musl-dev \
        libffi-dev \
    && pip install --no-cache-dir \
        --editable /opt/certbot/src/acme \
        --editable /opt/certbot/src \
    && apk del .build-deps

RUN apk add --no-cache wget python3-dev libffi-dev bash
RUN pip3 install Jinja2

RUN mkdir /app
WORKDIR /app

RUN pip3 install python-etcd

ADD . /app

#ENTRYPOINT [ "/bin/sh" ]

CMD /bin/true
