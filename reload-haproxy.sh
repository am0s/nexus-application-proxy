#!/bin/bash

touch /var/log/haproxy.log
service rsyslog restart

/usr/local/sbin/haproxy -f /etc/haproxy.cfg -p /var/run/haproxy.pid -sf $(cat /var/run/haproxy.pid)
