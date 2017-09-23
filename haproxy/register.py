# -*- coding: utf-8 -*-
import argparse
import logging
import socket
import sys
import os
from datetime import datetime

import etcd
import json


logger = logging.getLogger('docker-alb')


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


def register_listener(client: etcd.Client, alb, identifier, name, port, protocol, rules, certificate_name=None):
    try:
        client.read("/alb/{alb}/listeners/{identifier}".format(alb=alb, identifier=identifier))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/listeners/{identifier}".format(alb=alb, identifier=identifier), None, dir=True)
    client.write("/alb/{alb}/listeners/{identifier}/name".format(alb=alb, identifier=identifier), name)
    client.write("/alb/{alb}/listeners/{identifier}/protocol".format(alb=alb, identifier=identifier), protocol)
    client.write("/alb/{alb}/listeners/{identifier}/port".format(alb=alb, identifier=identifier), port)
    client.write("/alb/{alb}/listeners/{identifier}/certificate_name".format(alb=alb, identifier=identifier),
                 certificate_name)
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


def register_listener_group(client: etcd.Client, alb, listener_id, domains=None, listeners=None,
                            certificate_name=None, use_certbot=False):
    try:
        client.read("/alb/{alb}/listener_groups/{identifier}".format(alb=alb, identifier=listener_id))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/listener_groups/{identifier}".format(alb=alb, identifier=listener_id), None, dir=True)
    # client.write("/alb/{alb}/listener_groups/{identifier}/name".format(alb=alb, identifier=listener_id), name)
    client.write("/alb/{alb}/listener_groups/{identifier}/domains".format(alb=alb, identifier=listener_id),
                 json.dumps(domains))
    client.write("/alb/{alb}/listener_groups/{identifier}/listeners".format(alb=alb, identifier=listener_id),
                 json.dumps(listeners))
    client.write("/alb/{alb}/listener_groups/{identifier}/certificate_name".format(alb=alb, identifier=listener_id),
                 certificate_name)
    client.write("/alb/{alb}/listener_groups/{identifier}/certbot_managed".format(alb=alb, identifier=listener_id),
                 'true' if use_certbot else 'false')


def register_certbot(client: etcd.Client, alb, listener_id, domains, target, certificate_name=None):
    """
    Register a certbot for a given listener, this creates special rules for
    this listener for allowing the certbot to verify the domain.
    """
    try:
        client.read("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=listener_id))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=listener_id), None, dir=True)
    client.write("/alb/{alb}/certbot/{identifier}/enabled".format(alb=alb, identifier=listener_id),
                 'true')
    client.write("/alb/{alb}/certbot/{identifier}/ready".format(alb=alb, identifier=listener_id),
                 'false')
    client.write("/alb/{alb}/certbot/{identifier}/certificate_name".format(alb=alb, identifier=listener_id),
                 certificate_name)
    client.write("/alb/{alb}/certbot/{identifier}/domains".format(alb=alb, identifier=listener_id),
                 json.dumps(domains))
    client.write("/alb/{alb}/certbot/{identifier}/target".format(alb=alb, identifier=listener_id),
                 json.dumps(target))


def mark_certbot_ready(client: etcd.Client, alb, cerbot_id, is_ready=True):
    """
    Tell system a certbot is ready
    """
    try:
        client.read("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=cerbot_id))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=cerbot_id), None, dir=True)
    client.write("/alb/{alb}/certbot/{identifier}/ready".format(alb=alb, identifier=cerbot_id),
                 'true' if is_ready else 'false')


def wait_certbot_ready(client: etcd.Client, alb, listener_id):
    try:
        client.read("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=listener_id))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=listener_id), None, dir=True)
    # Wait max 3 seconds for they entry to be ready
    entry = client.watch("/alb/{alb}/certbot/{identifier}/ready".format(alb=alb, identifier=listener_id),
                         timeout=3*60)
    return entry.value == 'true'


def unregister_certbot(client: etcd.Client, alb, listener_id):
    """
    Removes a registered certbot for a given listener. If no certbot has been previously registered
    nothing happens.
    """
    try:
        client.delete("/alb/{alb}/certbot/{identifier}".format(alb=alb, identifier=listener_id), recursive=True,
                      dir=True)
    except KeyError as e:
        logger.exception("Failed to unregister certbot: %s: %s", type(e).__name__, e)


def has_certificate(client: etcd.Client, certificate_name: str):
    """
    Check if certificate exists
    """
    try:
        client.read("/certs/{name}".format(name=certificate_name))
    except (etcd.EtcdKeyNotFound, KeyError):
        return False
    return True


def register_certificate(client: etcd.Client, certificate_name: str, domains: list = None, email: str = None,
                         data: str = None, modified: datetime = None):
    """
    Register a certificate with optional data, domains, email and modification date.
    """
    try:
        client.read("/certs/{name}".format(name=certificate_name))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/certs/{name}".format(name=certificate_name), None, dir=True)
    client.write("/certs/{name}/email".format(name=certificate_name),
                 email)
    client.write("/certs/{name}/data".format(name=certificate_name),
                 data)
    if not modified:
        modified = datetime.now()
    client.write("/certs/{name}/modified".format(name=certificate_name),
                 modified.isoformat())
    client.write("/certs/{name}/domains".format(name=certificate_name),
                 json.dumps(domains))
    # TODO: Verify certificate data with ssl
    if data:
        client.write("/certs/{name}/is_valid".format(name=certificate_name),
                     'true')
    else:
        client.write("/certs/{name}/is_valid".format(name=certificate_name),
                     'false')


def unregister_certificate(client: etcd.Client, certificate_name: str):
    """
    Removes a registered certificate. If no certificate has been previously registered
    nothing happens.
    """
    try:
        client.delete("/certs/{name}".format(name=certificate_name), recursive=True,
                      dir=True)
    except KeyError:
        pass


def upload_certificate_file(client: etcd.Client, certificate_name, certificate_file, modified: datetime = None):
    try:
        client.read("/certs/{cert_name}".format(cert_name=certificate_name))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/certs/{cert_name}".format(cert_name=certificate_name), None, dir=True)
    if isinstance(certificate_file, str):
        with open(certificate_file) as cert_fh:
            certificate_content = cert_fh.read()
    else:
        certificate_content = certificate_file.read()
    client.write("/certs/{cert_name}/cert".format(cert_name=certificate_name), certificate_content)
    if not modified:
        modified = datetime.now()
    client.write("/certs/{name}/modified".format(name=certificate_name),
                 modified.isoformat())
    # TODO: Verify certificate data with ssl
    if certificate_content:
        client.write("/certs/{name}/is_valid".format(name=certificate_name),
                     'true')
    else:
        client.write("/certs/{name}/is_valid".format(name=certificate_name),
                     'false')


def upload_certificate_data(client: etcd.Client, certificate_name, data, modified: datetime = None):
    try:
        client.read("/certs/{cert_name}".format(cert_name=certificate_name))
    except (etcd.EtcdKeyNotFound, KeyError):
        client.write("/certs/{cert_name}".format(cert_name=certificate_name), None, dir=True)
    client.write("/certs/{cert_name}/cert".format(cert_name=certificate_name), data)
    if not modified:
        modified = datetime.now()
    client.write("/certs/{name}/modified".format(name=certificate_name),
                 modified.isoformat())
    # TODO: Verify certificate data with ssl
    if data:
        client.write("/certs/{name}/is_valid".format(name=certificate_name),
                     'true')
    else:
        client.write("/certs/{name}/is_valid".format(name=certificate_name),
                     'false')


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
        logger.error("ETCD_HOST not set")
        sys.exit(1)

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    sys.path.insert(0, '/tmp')

    client = etcd.Client(host=host, port=int(port))

    config_module = load_config()
    send_config(client, config_module.services, host=backend_host)


def etcd_client(etcd_host=None):
    etcd_host = os.environ.get("ETCD_HOST", etcd_host)
    if not etcd_host:
        print("ETCD_HOST not set", file=sys.stderr)
        sys.exit(1)

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    client = etcd.Client(host=host, port=int(port))
    return client


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
                        help="ID of target group and listener group, defaults to first domain")
    parser.add_argument("--port", default='https',
                        help="Which port to use for listener in load-balancer, specify a number "
                             "or use http for HTTP only, https for https only or mixed for http and https. "
                             "defaults to https")
    parser.add_argument("--certificate", default=None,
                        help="Path to certificate file (pem) to upload")
    parser.add_argument("--certbot", action="store_true", default=False,
                        help="Auto creation of certificate using letsencrypt")
    parser.add_argument("--certificate-name", default=None,
                        help="Name of certificate entry to use, default is to use ID of listener group")
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

    dockerhost_ip = os.environ.get("DOCKERHOST_IP")

    client = etcd_client(args.etcd_host)

    listener_domains = args.virtual_host.split(",")
    listener_port = args.port

    main_domain = listener_domains[0]
    tg_id = args.id or ('vhost-' + main_domain)
    listener_id = tg_id
    tg_name = 'VirtualHost: ' + main_domain
    alb_identifier = 'vhost'

    certificate = args.certificate
    certificate_name = args.certificate_name or listener_id
    use_certbot = args.certbot

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

    listeners = []
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
                          protocol='http', rules=rules)
        listeners.append('http-' + main_domain)
    elif listener_port == 'https':
        remove_listener(client, alb=alb_identifier, identifier='http-' + main_domain)
        remove_listener(client, alb=alb_identifier, identifier='https-' + main_domain)
        https_rules = []
        http_rules = []
        for domain in listener_domains:
            domain, path = (domain.split('/', 1) + [None])[0:2]
            https_rules.append({
                'id': 'vhost-' + domain,
                'host': domain,
                'path': path,
                'action': 'tg:' + tg_id,
            })
            http_rules.append({
                'id': 'vhost-https-' + domain,
                'host': domain,
                'path': path,
                'action': 'https',
            })
        register_listener(client, alb=alb_identifier, identifier='https-' + main_domain, name='HTTPS 443', port=443,
                          protocol='https', rules=https_rules, certificate_name=certificate_name)
        register_listener(client, alb=alb_identifier, identifier='http-' + main_domain, name='HTTP 80', port=80,
                          protocol='http', rules=http_rules)
        listeners.append('https-' + main_domain)
        listeners.append('http-' + main_domain)
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
                          protocol='http', rules=rules)
        register_listener(client, alb=alb_identifier, identifier='https-' + main_domain, name='HTTPS 443', port=443,
                          protocol='https', rules=rules, certificate_name=certificate_name)
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
                              protocol='http',
                              rules=rules)
            listeners.append('custom-{}-{}'.format(listener_port_num, main_domain))
        except ValueError:
            print("Listener port number '{}' must be a number or one of 'http', 'https', 'mixed'".format(listener_port),
                  file=sys.stderr)
            sys.exit(1)

    # Register listener groups, contains all domains and listeners
    domains = []
    for domain in listener_domains:
        domain, path = (domain.split('/', 1) + [None])[0:2]
        domains.append(domain)

    register_listener_group(client, alb_identifier, listener_id, domains=domains, listeners=listeners,
                            certificate_name=certificate_name, use_certbot=use_certbot)

    if certificate and not use_certbot:
        upload_certificate_file(client, certificate_name, certificate)


def cli_register_vhost(args=None):
    try:
        register_vhost(args=args)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)


def upload_certificate(args=None):
    """
    Uploads certificate files.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)

    parser.add_argument("--etcd-host", dest="etcd_host", default=None,
                        help="hostname for etcd server")

    parser.add_argument("--certificate-name", default=None,
                        help="Name of certificate entry to use, must match name used in listeners")
    parser.add_argument("--certificate", default=None,
                        help="Path to certificate file (pem) to upload containing full chain and private key")
    parser.add_argument("--full-chain", default=None,
                        help="Path to file containing full chain of certificates")
    parser.add_argument("--private-key", default=None,
                        help="Path to file containing private key")

    parser.add_argument("--email", default=None,
                        help="Email address of owner of certificate")
    parser.add_argument("--domain", dest="domains", metavar="domain", default=[], nargs="*",
                        help="Domain name used in certificate, can be specified multiple times")
    # TODO: See if domains (and email) can be read from certificate using ssl tools

    args = parser.parse_args(args)
    verbosity = os.environ.get('VERBOSITY_LEVEL', None)
    if verbosity is not None:
        try:
            verbosity = int(verbosity)
        except ValueError:
            verbosity = None
    if verbosity is None:
        verbosity = args.verbosity

    client = etcd_client(args.etcd_host)

    certificate = args.certificate
    full_chain = args.full_chain
    private_key = args.private_key
    if certificate and (full_chain or private_key):
        print("Cannot specify both --certificate and --full-chain and --private-key, use either --certificate only or "
              "--full-chain and --private-key", file=sys.stderr)
        sys.exit(1)
    certificate_name = args.certificate_name
    if not certificate_name:
        print("Need to specify name of certificate in store", file=sys.stderr)
        sys.exit(1)

    email = args.email
    domains = args.domains

    pem_data = ""
    if certificate:
        if not os.path.isfile(certificate):
            print("The certificate file {} does not exist".format(certificate), file=sys.stderr)
            sys.exit(1)
        with open(certificate) as certificate_file:
            pem_data = certificate_file.read()
    elif full_chain and private_key:
        if not os.path.isfile(full_chain):
            print("The full chain file {} does not exist".format(full_chain), file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(private_key):
            print("The private key file {} does not exist".format(private_key), file=sys.stderr)
            sys.exit(1)
        with open(full_chain) as full_chain_file:
            pem_data += full_chain_file.read().strip() + "\n"
        with open(private_key) as private_key_file:
            pem_data += private_key_file.read().strip() + "\n"
    elif not full_chain:
        print("Need to specify --private-key when using --full-chain", file=sys.stderr)
        sys.exit(1)
    elif not private_key:
        print("Need to specify --full-chain when using --private-key", file=sys.stderr)
        sys.exit(1)
    else:
        print("Use either --certificate only or --full-chain and --private-key", file=sys.stderr)
        sys.exit(1)

    if not pem_data.strip():
        print("No data found in certificate files", file=sys.stderr)
        sys.exit(1)

    if not has_certificate(client, certificate_name):
        if not email:
            print("Certificate does not exist in store, need an email for first registration", file=sys.stderr)
            sys.exit(1)
        if not domains:
            print("Certificate does not exist in store, need domains to first registration", file=sys.stderr)
            sys.exit(1)
        register_certificate(client, certificate_name, domains=domains, email=email, data=pem_data,
                             modified=datetime.now())
    else:
        upload_certificate_data(client, certificate_name, pem_data)


def cli_upload_certificate(args=None):
    try:
        upload_certificate(args=args)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
