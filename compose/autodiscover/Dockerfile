FROM ubuntu:14.04
MAINTAINER Jan Borsodi <jborsodi@gmail.com>

RUN apt-get update
RUN apt-get install -y wget python3 python3-pip python3-dev libssl-dev libffi-dev bash

RUN mkdir /app
WORKDIR /app

RUN wget https://github.com/jwilder/docker-gen/releases/download/0.7.3/docker-gen-linux-amd64-0.7.3.tar.gz
RUN tar xvzf docker-gen-linux-amd64-0.7.3.tar.gz -C /usr/local/bin

RUN pip3 install python-etcd

ADD . /app

ENV DOCKER_HOST unix:///var/run/docker.sock

CMD docker-gen -interval 10 -watch -notify "python3 register.py" config/docker_gen/etcd_config.tmpl /tmp/etcd_config.py
