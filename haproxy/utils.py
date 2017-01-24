# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
import sys


POLL_TIMEOUT = 5
NO_SERVICES_TIMEOUT = 5.0


class ConfigurationError(Exception):
    pass


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, object):
            if hasattr(obj, '__json__'):
                return [obj.real, obj.imag]
        return super(JSONEncoder, self).default(obj)


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
