# -*- coding: utf-8 -*-
import json
import os

POLL_TIMEOUT = 5
NO_SERVICES_TIMEOUT = 5.0


class ConfigurationError(Exception):
    pass


def get_etcd_addr():
    if "ETCD_HOST" not in os.environ:
        raise ConfigurationError("ETCD_HOST not set")

    etcd_host = os.environ["ETCD_HOST"]
    if not etcd_host:
        raise ConfigurationError("ETCD_HOST not set")

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    return host, port
