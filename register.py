#!/usr/bin/python
import argparse
import sys
import os
import etcd
import json


def load_config():
    # We use a Python file as the config to make it easier with trailing commas
    import etcd_config
    return etcd_config


def send_config(client, config, host=None):
    """

    :param client:
    :param config:
    :param host: Override host for each container.
    :return:
    """
    try:
        client.read("/services")
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/services", None, dir=True)

    services = {}
    for service in config:
        name = service['name']
        hosts = service.get('hosts')
        ports = service.get('ports', [80])
        if name not in services:
            services[name] = {
                'name': name,
                'backends': [],
            }
            if hosts:
                services[name]['hosts'] = hosts
            if ports:
                services[name]['ports'] = ports
        for backend in service.get('backends', []):
            services[name]['backends'].append(backend)

    for name, service in services.items():
        backends = service.get('backends', [])
        if not backends:
            continue
        hosts = service.get('hosts')
        ports = service.get('ports', [80])

        try:
            client.read("/services/{name}".format(name=name))
        except (etcd.EtcdKeyNotFound, KeyError):
            client.write("/services/{name}".format(name=name), None, dir=True)
        try:
            client.read("/services/{name}/backends".format(name=name))
        except (etcd.EtcdKeyNotFound, KeyError):
            client.write("/services/{name}/backends".format(name=name), None, dir=True)

        if hosts:
            client.write("/services/{name}/config".format(name=name), json.dumps({
                'hosts': hosts,
                'ports': ports,
            }), ttl=15)
        for backend in backends:
            backend_name = backend.get('name')
            backend_host = backend['host']
            if host:
                backend_host = host
            if not backend_name:
                backend_name = backend_host + ':' + backend['port']
            try:
                client.read("/services/{name}/backends/{backend}".format(name=name, backend=backend_name))
            except (etcd.EtcdKeyNotFound, KeyError):
                client.write("/services/{name}/backends/{backend}".format(name=name, backend=backend_name), None, dir=True)
            client.write("/services/{name}/backends/{backend}/config".format(
                name=name, backend=backend_name), json.dumps({
                    'host': backend_host,
                    'port': backend['port'],
                }), ttl=15)


def main():
    etcd_host = os.environ.get("ETCD_HOST")
    backend_host = os.environ.get("HOST_IP")
    if not etcd_host:
        print("ETCD_HOST not set")
        sys.exit(1)

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    sys.path.insert(0, '/tmp')

    client = etcd.Client(host=host, port=int(port))

    config_module = load_config()
    send_config(client, config_module.services, host=backend_host)


if __name__ == "__main__":
    main()
