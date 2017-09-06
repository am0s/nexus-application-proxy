#!/usr/bin/env bash
CONFIG_FILE="$1"

exec /usr/local/sbin/haproxy -f $CONFIG_FILE -c
