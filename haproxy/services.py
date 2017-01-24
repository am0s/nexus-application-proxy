# -*- coding: utf-8 -*-
class NoServices(Exception):
    pass


class Service(object):
    name = None
    ports = []
    hosts = []
    backends = []
    is_default = False

    def __init__(self, name, ports=None, hosts=None, backends=None):
        self.name = name
        self.ports = ports or []
        self.hosts = hosts or []
        self.backends = backends or []

    def __cmp__(self, other):
        return self.name == other.name and self.ports == other.ports and self.hosts == other.hosts and \
               self.backends == other.backends and self.is_default == other.is_default

    def __repr__(self):
        return "Service({!r},ports={!r},hosts={!r},backends={!r})".format(
            self.name, self.ports, self.hosts, self.backends)


class Backend(object):
    name = None
    port = None
    host = None

    def __init__(self, name, port=None, host=None):
        self.name = name
        self.port = port
        self.host = host

    def __cmp__(self, other):
        return self.name == other.name and self.port == other.port and self.host == other.host

    def __repr__(self):
        return "Backend({!r},port={!r},host={!r})".format(self.name, self.port, self.host)