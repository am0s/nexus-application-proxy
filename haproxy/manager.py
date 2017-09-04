# -*- coding: utf-8 -*-
import json

import etcd

from haproxy.services import NoServices, Service, Backend
from haproxy.utils import get_etcd_addr


def get_services(max_tries=3):
    tries = 0
    while tries < max_tries:
        try:
            return get_services2()
        except etcd.EtcdConnectionFailed:
            tries += 1
    raise NoServices()


def get_services2():
    host, port = get_etcd_addr()
    client = etcd.Client(host=host, port=int(port))
    all_ports = set()
    services = {}

    try:
        for i in client.read('/services').children:
            service_name = i.key[1:].split("/")[-1]

            service_path = '/services/' + service_name
            service = Service(service_name, ports=[80])
            try:
                config = json.loads(client.get(service_path + '/config').value)
            except (etcd.EtcdKeyNotFound, KeyError, ValueError):
                continue
            if 'ports' in config and isinstance(config['ports'], list):
                service.ports = config['ports']
            if 'hosts' in config and isinstance(config['hosts'], list):
                service.hosts = config['hosts']

            try:
                for backend_item in client.read(service_path + '/backends').children:
                    backend_name = backend_item.key[1:].split("/")[-1]
                    backend_path = service_path + '/backends/' + backend_name
                    try:
                        backend_config = json.loads(client.get(backend_path + '/config').value)
                        service.backends.append(Backend(
                            backend_name,
                            port=backend_config['port'] or 80,
                            host=backend_config['host'],
                        ))
                    except (etcd.EtcdKeyNotFound, KeyError, ValueError):
                        continue
            except (etcd.EtcdKeyNotFound, KeyError):
                pass
            if service.backends:
                services[service_name] = service
                all_ports.update(list(service.ports))
    except (etcd.EtcdKeyNotFound, KeyError, ValueError):
        pass

    return {
        'services': services,
        'ports': list(all_ports),
    }