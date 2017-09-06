#!/usr/bin/env bash

# Copy the next configuration and restart haproxy
cp /etc/haproxy.new.cfg /etc/haproxy.cfg
exec /usr/local/sbin/haproxy -f /etc/haproxy.cfg -p /var/run/haproxy.pid -st $(cat /var/run/haproxy.pid)
