FROM ubuntu:14.04
MAINTAINER Jan Borsodi <jborsodi@gmail.com>

RUN apt-get update
RUN apt-get install -y wget make gcc binutils python-pip python-dev libssl-dev libffi-dev bash

WORKDIR /root

RUN wget http://www.haproxy.org/download/1.5/src/haproxy-1.5.1.tar.gz && \
    tar -zxvf haproxy-1.5.1.tar.gz

RUN cd haproxy-1.5.1 && make TARGET=generic && make install

RUN pip install python-etcd Jinja2
RUN touch /var/run/haproxy.pid

RUN apt-get update && apt-get install rsyslog -y && \
    sed -i 's/#$ModLoad imudp/$ModLoad imudp/g' /etc/rsyslog.conf && \
    sed -i 's/#$UDPServerRun 514/$UDPServerRun 514/g' /etc/rsyslog.conf

ADD config/syslog/haproxy.conf /etc/rsyslog.d/70-haproxy.conf

ADD . /app

WORKDIR /app

EXPOSE 1936 80

CMD ["python", "main.py"]
