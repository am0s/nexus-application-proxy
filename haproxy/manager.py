# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
import shutil
from datetime import datetime

import etcd

from subprocess import call

from .services import NoListeners, Listener, Rule, Target, NoTargetGroups, HealthCheck, ListenerGroup, CertBot, \
    Certificate
from .utils import get_etcd_addr
from .services import TargetGroup, LoadBalancerConfig
from .register import mark_certbot_ready

logger = logging.getLogger('docker-alb')

bool_lookup = {
    'true': True,
    'false': False,
}


def get_listeners(alb_id, max_tries=3):
    tries = 0
    while tries < max_tries:
        try:
            return _get_listeners(alb_id)
        except etcd.EtcdConnectionFailed:
            tries += 1
    raise NoListeners()


def get_target_groups(identifiers, max_tries=3):
    tries = 0
    while tries < max_tries:
        try:
            return _get_target_groups(identifiers)
        except etcd.EtcdConnectionFailed:
            tries += 1
    raise NoTargetGroups()


def get_listener_groups(alb_id, max_tries=3):
    tries = 0
    while tries < max_tries:
        try:
            return _get_listener_groups(alb_id)
        except etcd.EtcdConnectionFailed:
            tries += 1
    raise NoTargetGroups()


def get_alb(alb_id, with_listener_group=False, max_tries=3, raw=False) -> LoadBalancerConfig:
    """
    :param alb_id: Identifier for ALB.
    :param with_listener_group: If True then it will also load listener groups.
    :param max_tries: Max number of times to try and fetching data if it fails.
    :param raw: If True then it will only include data found in config, not auto-generated ones
    """
    listeners = get_listeners(alb_id, max_tries=max_tries)
    target_ids = set()
    for listener in listeners.values():
        target_ids |= set(listener.iter_target_group_ids())
    target_groups = get_target_groups(target_ids, max_tries=max_tries)

    listener_groups = None
    # logger.debug("with_listener_group: %s", with_listener_group)
    if with_listener_group:
        listener_groups = get_listener_groups(alb_id, max_tries=max_tries)
        if listener_groups is not None:
            listener_groups = list(listener_groups.values())

        # logger.debug("listener_groups: %s", listener_groups)
        for listener_group in listener_groups:  # type: ListenerGroup
            # If a certbot is active, create the listener rules and target group for it
            # logger.debug("certbot: %s", listener_group.certbot)
            if not raw and listener_group.certbot:
                certbot = listener_group.certbot
                # Figure out if there is a http listener on port 80, if so use it, otherwise create it
                certbot_listener = None
                for listener in listeners.values():  # type: Listener
                    if listener.protocol == 'http' and listener.port == 80:
                        certbot_listener = listener
                # logger.debug("certbot listener: %s", certbot_listener)
                certbot_rules = []
                # Create incoming rules for all domains
                for certbot_domain in certbot.domains:
                    certbot_rules.append(Rule(
                            host=certbot_domain,
                            path='/.well-known/acme-challenge/',
                            action='tg:certbot-' + listener_group.identifier,
                            # High priority to ensure it is matched first
                            pri=1000000,
                        ))
                # Create target group for the certbot target
                certbot_tg = TargetGroup('certbot-' + listener_group.identifier, protocol='http', targets=[
                    Target(host=certbot.target_ip, port=certbot.target_port),
                ])
                if certbot_listener:
                    certbot_listener.rules.extend(certbot_rules)
                else:
                    certbot_listener = Listener('certbot-' + listener_group.identifier, port=80, rules=certbot_rules)
                    listeners[certbot_listener.identifier] = certbot_listener
                target_groups[certbot_tg.identifier] = certbot_tg

    # Assign TargetGroup objects to rules
    for listener in listeners.values():
        for rule in listener.rules:
            if rule.target_group_id and rule.target_group_id in target_groups:
                rule.target_group = target_groups[rule.target_group_id]

    # Load certificates
    for listener in listeners.values():
        if listener.certificate_name:
            # Load certificate details, except PEM data
            certificate = _get_certificate(listener.certificate_name)
            logger.debug("listener: %s, cert: %s", listener, certificate)
            if certificate:
                listener.certificate = certificate

    if not raw:
        # Sort rules in all listeners so that high priority comes first
        for listener in listeners.values():  # type: Listener
            listener.rules.sort(key=lambda r: r.pri, reverse=True)

    return LoadBalancerConfig(alb_id, listeners=listeners, listener_groups=listener_groups,
                              target_groups=target_groups)


def dir_exists(client, key, default=None):
    try:
        return client.read(key)
    except (etcd.EtcdKeyNotFound, KeyError):
        return default


def get_value(client, key, default=None):
    try:
        return client.get(key).value
    except etcd.EtcdKeyNotFound:
        return default


def get_json(client, key, default=None):
    value = get_value(client, key)
    if value is None:
        return default
    return json.loads(value)


def get_int_item(data, key, name):
    value = data.get(key)
    try:
        return int(value)
    except ValueError:
        logger.warning("Expected integer value for %s: %s", name, value)
        return None


def _get_listeners(alb_id):
    """
    """
    host, port = get_etcd_addr()
    client = etcd.Client(host=host, port=int(port))
    listeners = {}

    try:
        listeners_prefix = '/alb/{name}/listeners'.format(name=alb_id)
        for i in client.read(listeners_prefix).children:
            listener_id = i.key[1:].split("/")[-1]

            listener_path = listeners_prefix + '/' + listener_id
            listener_port = get_value(client, listener_path + '/port')
            if listener_port is None:
                continue
            try:
                listener_port = int(listener_port)
            except ValueError:
                # Port is not an integer, skip listener
                continue
            listener_protocol = get_value(client, listener_path + '/protocol', default='http')
            certificate_name = get_value(client, listener_path + '/certificate_name')

            listener = Listener(listener_id, port=listener_port, protocol=listener_protocol,
                                certificate_name=certificate_name)

            rules = []
            try:
                for rule_it in client.read(listener_path + '/rules').children:
                    rule_id = rule_it.key[1:].split("/")[-1]
                    rule_path = listener_path + '/rules/' + rule_id
                    config = get_json(client, rule_path + '/config')
                    if config is None:
                        continue

                    path = config.get('path')
                    host = config.get('host')
                    action = config.get('action')
                    if not action:
                        continue

                    rules.append(Rule(
                        host=host,
                        path=path,
                        action=action
                    ))
            except (etcd.EtcdKeyNotFound, KeyError):
                pass

            # If there are no rules skip the entire listener
            if not rules:
                continue

            listener.rules.extend(rules)
            listeners[listener_id] = listener
    except (etcd.EtcdKeyNotFound, KeyError, ValueError):
        pass

    return listeners


def _get_certificate(certificate_name, with_pem=False, client: etcd.Client = None):
    """
    :param with_pem: If True then it also loads the pem data
    :rtype: Optional[Certificate]
    """
    if client is None:
        host, port = get_etcd_addr()
        client = etcd.Client(host=host, port=int(port))

    cert_path = '/certs/{name}'.format(name=certificate_name)
    try:
        client.read(cert_path)
    except (etcd.EtcdKeyNotFound, KeyError):
        return None

    cert_pem = get_value(client, cert_path + '/cert') or None
    cert_domains = get_json(client, cert_path + '/domains', default=[])
    cert_email = get_value(client, cert_path + '/email') or None
    cert_modified = get_value(client, cert_path + '/modified') or None
    if cert_modified:
        try:
            cert_modified = datetime.strptime(cert_modified, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            try:
                cert_modified = datetime.strptime(cert_modified, "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                try:
                    cert_modified = datetime.strptime(cert_modified, "%Y-%m-%dT%H:%M:%S%z")
                except ValueError:
                    cert_modified = None
    cert_is_valid = get_value(client, cert_path + '/is_valid')
    cert_is_valid = bool_lookup.get(cert_is_valid)

    certificate = Certificate(certificate_name, pem_data=cert_pem, domains=cert_domains, email=cert_email,
                              modified=cert_modified, is_valid=cert_is_valid)
    if with_pem:
        certificate.pem_data = _load_certificate_data(certificate, client=client)

    return certificate


def _load_certificate_data(certificate: Certificate, client: etcd.Client = None):
    if client is None:
        host, port = get_etcd_addr()
        client = etcd.Client(host=host, port=int(port))

    cert_path = '/certs/{name}'.format(name=certificate.identifier)
    cert_pem = get_value(client, cert_path + '/data') or None
    return cert_pem


def transfer_certificates(alb: LoadBalancerConfig, client: etcd.Client = None):
    if client is None:
        host, port = get_etcd_addr()
        client = etcd.Client(host=host, port=int(port))

    certs_path = get_certs_path()
    certs_temp_path = get_temp_certs_path()
    if not os.path.exists(certs_path):
        os.makedirs(certs_path, exist_ok=True)
    if not os.path.exists(certs_temp_path):
        os.makedirs(certs_temp_path, exist_ok=True)

    for listener in alb.listeners:
        logger.debug("Transfer for listener: %s", listener)
        if listener.certificate:
            # If the certificate was transferred, mark it as valid
            if transfer_certificate(listener.certificate, client=client):
                listener.certificate.is_valid = True

    # Sync over changes and delete those that no longer exist
    call(["rsync", "-a", "--delete", certs_temp_path + '/', certs_path + '/'])


def transfer_certificate(certificate: Certificate, client: etcd.Client = None):
    if client is None:
        host, port = get_etcd_addr()
        client = etcd.Client(host=host, port=int(port))

    modified = certificate.modified

    cert_path = get_cert_path(certificate.identifier)
    cert_temp_path = get_temp_cert_path(certificate.identifier)
    cert_temp_dir = os.path.dirname(cert_temp_path)
    if not os.path.exists(cert_temp_dir):
        os.makedirs(cert_temp_dir, exist_ok=True)

    # If the pem already exist and has recent enough data we just copy it directly
    if os.path.exists(cert_path) and datetime.fromtimestamp(os.path.getmtime(cert_path)) >= modified:
        shutil.copy(cert_path, cert_temp_path)
    else:
        # If not load the pem data from the certificate
        if certificate.pem_data is None:
            pem_data = _load_certificate_data(certificate, client=client)
        else:
            pem_data = certificate.pem_data
        if pem_data:
            # TODO: Verify certificate with SSL
            with open(cert_temp_path, "w") as pem_file:
                pem_file.write(pem_data)


def mark_certbots_ready(alb: LoadBalancerConfig, client: etcd.Client = None):
    if client is None:
        host, port = get_etcd_addr()
        client = etcd.Client(host=host, port=int(port))

    for listener_group in alb.listener_groups:
        certbot = listener_group.certbot
        if certbot:
            mark_certbot_ready(client, alb.identifier, certbot.identifier)


def get_certs_path():
    return '/etc/ssl/crt'


def get_temp_certs_path():
    return '/tmp/crt'


def get_cert_path(name):
    return '/etc/ssl/crt/{name}.pem'.format(name=name)


def get_temp_cert_path(name):
    return '/tmp/crt/{name}.pem'.format(name=name)


def _get_target_groups(identifiers: list) -> dict:
    host, port = get_etcd_addr()
    client = etcd.Client(host=host, port=int(port))
    groups = {}

    for group_id in identifiers:
        name = get_value(client, '/target_group/{name}/name'.format(name=group_id))
        if name is None:
            continue

        protocol = get_value(client, '/target_group/{name}/protocol'.format(name=group_id))
        health_check_data = get_json(client, '/target_group/{name}/healthcheck'.format(name=group_id))
        if health_check_data:
            hc_protocol = health_check_data.get('protocol')
            if hc_protocol not in ('http', ):
                logger.warning("Unsupported protocol in healthcheck: %s", hc_protocol)
                hc_protocol = None
            hc_path = health_check_data.get('path')
            if hc_path and hc_path[0] != '/':
                logger.warning("Unsupported path in healthcheck: %s", hc_path)
                hc_path = None
            hc_port = health_check_data.get('port')
            if hc_port == 'traffic':
                pass
            else:
                try:
                    hc_port = int(hc_port)
                except ValueError:
                    logger.warning("Unsupported port value in healthcheck: %s", hc_port)
                    hc_port = None
            hc_healthy = get_int_item(health_check_data, 'healthy', "healthcheck.healthy")
            hc_unhealthy = get_int_item(health_check_data, 'unhealthy', "healthcheck.unhealthy")
            hc_timeout = get_int_item(health_check_data, 'timeout', "healthcheck.timeout")
            hc_interval = get_int_item(health_check_data, 'interval', "healthcheck.interval")
            hc_success = health_check_data.get('success')
            if hc_success:
                if not isinstance(hc_success, list):
                    hc_success = [hc_success]
            else:
                hc_success = None

            health_check = HealthCheck(protocol=hc_protocol, path=hc_path, port=hc_port, healthy=hc_healthy,
                                       unhealthy=hc_unhealthy, timeout=hc_timeout, interval=hc_interval,
                                       success=hc_success)
        else:
            health_check = HealthCheck()

        targets_prefix = '/target_group/{name}/targets'.format(name=group_id)
        targets = []
        for i in client.read(targets_prefix).children:
            target_id = i.key[1:].split("/")[-1]

            target_path = targets_prefix + '/' + target_id
            config = get_json(client, target_path)
            if config is None:
                continue

            host = config.get('host')
            port = config.get('port')
            if not host or not port:
                continue

            targets.append(Target(
                host=host,
                port=port,
            ))

        target_group = TargetGroup(group_id, targets=targets, health_check=health_check, protocol=protocol)
        groups[group_id] = target_group

    return groups


def _get_listener_groups(alb_id):
    host, port = get_etcd_addr()
    client = etcd.Client(host=host, port=int(port))
    listener_groups = {}

    try:
        lg_prefix = '/alb/{name}/listener_groups'.format(name=alb_id)
        for i in client.read(lg_prefix).children:
            lg_id = i.key[1:].split("/")[-1]

            lg_path = lg_prefix + '/' + lg_id
            domains = get_json(client, lg_path + '/domains')
            listener_ids = get_json(client, lg_path + '/listeners')
            certificate_name = get_value(client, lg_path + '/certificate_name')
            use_certbot = get_value(client, lg_path + '/certbot_managed') == 'true'

            certbot_path = '/alb/{name}/certbot/{listener_id}'.format(name=alb_id, listener_id=lg_id)
            certbot_enabled = get_value(client, certbot_path + '/enabled', default='false') == 'true'
            certbot_target = get_json(client, certbot_path + '/target')
            certbot_domains = get_json(client, certbot_path + '/domains')
            certbot_certificate_name = get_value(client, certbot_path + '/certificate_name')
            certbot = None
            logger.debug("use_certbot=%r,cerbot_enabled=%r,domains=%r,target=%r", use_certbot, certbot_enabled,
                         domains, certbot_target)
            if use_certbot and certbot_enabled and domains and isinstance(certbot_target, list) and len(
                    certbot_target) >= 2:
                certbot = CertBot(lg_id, target_ip=certbot_target[0], target_port=certbot_target[1],
                                  domains=certbot_domains, certificate_name=certbot_certificate_name)

            lg = ListenerGroup(lg_id, listeners=listener_ids, domains=domains, certificate_name=certificate_name,
                               use_certbot=use_certbot, certbot=certbot)
            listener_groups[lg_id] = lg
    except (etcd.EtcdKeyNotFound, KeyError, ValueError) as e:
        logger.exception("error reading listener groups: %s: %s", type(e).__name__, e)
        pass

    return listener_groups

