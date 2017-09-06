#!/bin/bash

/usr/local/sbin/haproxy -f /etc/haproxy.cfg -p /var/run/haproxy.pid -st $(cat /var/run/haproxy.pid)
