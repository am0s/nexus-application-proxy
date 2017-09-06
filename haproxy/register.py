# -*- coding: utf-8 -*-
import argparse
import socket
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
            }))
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
                }))


def register_target_group(client: etcd.Client, identifier, name, targets, protocol="http"):
    try:
        client.read("/target_group/{identifier}".format(identifier=identifier))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/target_group/{identifier}".format(identifier=identifier), None, dir=True)
    client.write("/target_group/{identifier}/name".format(identifier=identifier), name)
    client.write("/target_group/{identifier}/id".format(identifier=identifier), identifier)
    # only http for now
    client.write("/target_group/{identifier}/protocol".format(identifier=identifier), 'http')
    # Health check config is hardcoded for now
    client.write("/target_group/{identifier}/healthcheck".format(identifier=identifier), json.dumps({
        'protocol': 'http',
        'path': '/',
        # traffic port is the port of the first target
        'port': 'traffic',
        'healthy': 2,
        'unhealthy': 10,
        'timeout': 4,
        'interval': 5,
        'success': 200,
    }))

    try:
        client.read("/target_group/{identifier}/targets".format(identifier=identifier))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/target_group/{identifier}/targets".format(identifier=identifier), None, dir=True)
    for target in targets:
        host = target['host']
        port = target['port']
        alb = target.get('alb')
        # TODO: If the target is an ALB, then we need to register this ALB as the listener
        # in the target ALB. We also need to transfer any rules from the target to the listener
        client.write(
            "/target_group/{identifier}/targets/{name}".format(identifier=identifier, name="{}:{}".format(host, port)),
            json.dumps({
                'host': host,
                'port': port,
            }))


def unregister_targets(client: etcd.Client, identifier, targets):
    try:
        client.read("/target_group/{identifier}/targets".format(identifier=identifier))
    except (etcd.EtcdKeyNotFound, KeyError):
        return
    for target in targets:
        host = target['host']
        port = target['port']
        alb = target.get('alb')
        try:
            client.delete("/target_group/{identifier}/targets/{name}".format(identifier=identifier,
                                                                             name="{}:{}".format(host, port)))
        except (etcd.EtcdKeyNotFound, KeyError):
            pass


def remove_listener(client: etcd.Client, alb, identifier):
    try:
        client.delete("/alb/{alb}/listeners/{identifier}".format(alb=alb, identifier=identifier), recursive=True)
    except (etcd.EtcdKeyNotFound, KeyError):
        pass


def register_listener(client: etcd.Client, alb, identifier, name, port, rules):
    try:
        client.read("/alb/{alb}/listeners/{identifier}".format(alb=alb, identifier=identifier))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/listeners/{identifier}".format(alb=alb, identifier=identifier), None, dir=True)
    client.write("/alb/{alb}/listeners/{identifier}/name".format(alb=alb, identifier=identifier), name)
    client.write("/alb/{alb}/listeners/{identifier}/port".format(alb=alb, identifier=identifier), port)
    try:
        client.read("/alb/{alb}/listeners/{identifier}/rules".format(alb=alb, identifier=identifier))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/listeners/{identifier}/rules".format(alb=alb, identifier=identifier), None, dir=True)

    for rule in rules:
        rule_id = rule['id']
        rule_host = rule.get('host')
        rule_path = rule.get('path')
        action = rule.get('action')
        try:
            client.read(
                "/alb/{alb}/listeners/{identifier}/rules/{rule}".format(alb=alb, identifier=identifier, rule=rule_id))
        except (etcd.EtcdKeyNotFound, KeyError):
            client.write(
                "/alb/{alb}/listeners/{identifier}/rules/{rule}".format(alb=alb, identifier=identifier, rule=rule_id),
                None, dir=True)
        client.write(
            "/alb/{alb}/listeners/{identifier}/rules/{rule}/config".format(
                alb=alb, identifier=identifier, rule=rule_id),
            json.dumps({
                'host': rule_host,
                'path': rule_path,
                'action': action,
            }))


def auto_register_docker(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)

    parser.add_argument("--etcd-host", dest="etcd_host", default=None,
                        help="hostname for etcd server")

    args = parser.parse_args(args)
    verbosity = os.environ.get('VERBOSITY_LEVEL', None)
    if verbosity is not None:
        try:
            verbosity = int(verbosity)
        except ValueError:
            verbosity = None
    if verbosity is None:
        verbosity = args.verbosity

    etcd_host = os.environ.get("ETCD_HOST", args.etcd_host)
    backend_host = os.environ.get("HOST_IP")
    if not etcd_host:
        print("ETCD_HOST not set", file=sys.stderr)
        sys.exit(1)

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    sys.path.insert(0, '/tmp')

    client = etcd.Client(host=host, port=int(port))

    config_module = load_config()
    send_config(client, config_module.services, host=backend_host)


def register_vhost(args=None):
    """
    Register a virtual-host in the load balancer.
    The virtual host can contain one or more domains, the primary domain should be listed first.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)

    parser.add_argument("--etcd-host", dest="etcd_host", default=None,
                        help="hostname for etcd server")

    parser.add_argument("--reset", default=None,
                        help="Resets any existing configuration before writing the new configuration")
    parser.add_argument("--id", default=None,
                        help="ID of target group, defaults to first domain")
    parser.add_argument("--port", default='https',
                        help="Which port to use for listener in load-balancer, specify a number "
                             "or use http for HTTP only, https for https only or mixed for http and https. "
                             "defaults to https")
    parser.add_argument("--certificate", default=None,
                        help="Path to certificate file (pem) to upload")
    parser.add_argument("--certificate-name", default=None,
                        help="Name of certificate entry to use, or specify 'letsencrypt' for auto "
                             "creation using letsencrypt")
    parser.add_argument("virtual_host",
                        help="domains to register")
    parser.add_argument("target",
                        help="The hostname/ip of target, either use <host>:<port> or just <host>. "
                             "Defaults to port 80 if no port is set. Specify multiple targets with "
                             "a comma separated list")

    args = parser.parse_args(args)
    verbosity = os.environ.get('VERBOSITY_LEVEL', None)
    if verbosity is not None:
        try:
            verbosity = int(verbosity)
        except ValueError:
            verbosity = None
    if verbosity is None:
        verbosity = args.verbosity

    etcd_host = os.environ.get("ETCD_HOST", args.etcd_host)
    dockerhost_ip = os.environ.get("DOCKERHOST_IP")
    if not etcd_host:
        print("ETCD_HOST not set", file=sys.stderr)
        sys.exit(1)

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    client = etcd.Client(host=host, port=int(port))

    listener_domains = args.virtual_host.split(",")
    listener_port = args.port

    main_domain = listener_domains[0]
    tg_id = args.id or ('vhost-' + main_domain)
    tg_name = 'VirtualHost: ' + main_domain
    alb_identifier = 'vhost'

    targets = []
    removed_targets = []
    for target in args.target.split(","):  # type: str
        host, port = (target.split(":", 1) + ["80"])[0:2]
        to_remove = False
        if host[:1] == '-':
            host = host[1:]
            to_remove = True

        # Targets must always be turned into IP address as the load-balancer may not know
        # the hostname ip
        if host == 'dockerhost':
            # Special case which exposes the dockerhost ip
            if not dockerhost_ip:
                print("No docker host IP set, please set env DOCKERHOST_IP", file=sys.stderr)
                sys.exit(1)
            host = dockerhost_ip
        else:
            host = socket.gethostbyname(host)
        if to_remove:
            removed_targets.append({
                'host': host,
                'port': port,
            })
        else:
            targets.append({
                'host': host,
                'port': port,
            })

    # Remove targets from target group
    unregister_targets(client, identifier=tg_id, targets=removed_targets)

    # First the target group which will receive the requests
    register_target_group(client, identifier=tg_id, name=tg_name, targets=targets)

    # Then setup listeners for all incoming ports, each listener has a set of
    # rules made from the registered domains. Each domain may also have a path
    # specified.
    listener_port_num = None
    try:
        listener_port_num = int(listener_port)
        if listener_port_num == 80:
            listener_port = 'http'
        elif listener_port_num == 443:
            listener_port = 'https'
    except ValueError:
        pass
    if listener_port == 'http':
        remove_listener(client, alb=alb_identifier, identifier='http-' + main_domain)
        remove_listener(client, alb=alb_identifier, identifier='https-' + main_domain)
        rules = []
        for domain in listener_domains:
            domain, path = (domain.split('/', 1) + [None])[0:2]
            rules.append({
                'id': 'vhost-' + domain,
                'host': domain,
                'path': path,
                'action': 'tg:' + tg_id,
            })
        register_listener(client, alb=alb_identifier, identifier='http-' + main_domain, name='HTTP 80', port=80,
                          rules=rules)
    elif listener_port == 'https':
        remove_listener(client, alb=alb_identifier, identifier='http-' + main_domain)
        remove_listener(client, alb=alb_identifier, identifier='https-' + main_domain)
        rules = []
        for domain in listener_domains:
            domain, path = (domain.split('/', 1) + [None])[0:2]
            rules.append({
                'id': 'vhost-' + domain,
                'host': domain,
                'path': path,
                'action': 'tg:' + tg_id,
            })
        register_listener(client, alb=alb_identifier, identifier='https-' + main_domain, name='HTTPS 443', port=443,
                          rules=rules)
        # TODO: Add a rule which upgrades http to https
    elif listener_port == 'mixed':
        remove_listener(client, alb=alb_identifier, identifier='http-' + main_domain)
        remove_listener(client, alb=alb_identifier, identifier='https-' + main_domain)
        rules = []
        for domain in listener_domains:
            domain, path = (domain.split('/', 1) + [None])[0:2]
            rules.append({
                'id': 'vhost-' + domain,
                'host': domain,
                'path': path,
                'action': 'tg:' + tg_id,
            })
        register_listener(client, alb=alb_identifier, identifier='http-' + main_domain, name='HTTP 80', port=80,
                          rules=rules)
        register_listener(client, alb=alb_identifier, identifier='https-' + main_domain, name='HTTPS 443', port=443,
                          rules=rules)
    else:
        try:
            remove_listener(client, alb=alb_identifier,
                            identifier='custom-{}-{}'.format(listener_port_num, main_domain))
            rules = []
            for domain in listener_domains:
                domain, path = (domain.split('/', 1) + [None])[0:2]
                rules.append({
                    'id': 'vhost-' + domain,
                    'host': domain,
                    'path': path,
                    'action': 'tg:' + tg_id,
                })
            register_listener(client, alb=alb_identifier,
                              identifier='custom-{}-{}'.format(listener_port_num, main_domain), name='HTTP 80',
                              port=listener_port_num,
                              rules=rules)
        except ValueError:
            print("Listener port number '{}' must be a number or on of 'http', 'https', 'mixed'".format(listener_port),
                  file=sys.stderr)
            sys.exit(1)


def cli_register_vhost(args=None):
    try:
        register_vhost(args=args)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
