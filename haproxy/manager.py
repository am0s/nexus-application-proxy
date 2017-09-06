# -*- coding: utf-8 -*-
import json
import logging

import etcd

from .services import NoListeners, Listener, Rule, Target, NoTargetGroups, HealthCheck
from .utils import get_etcd_addr
from .services import TargetGroup, LoadBalancerConfig

logger = logging.getLogger('docker-alb')


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


def get_alb(alb_id, max_tries=3) -> LoadBalancerConfig:
    listeners = get_listeners(alb_id, max_tries=max_tries)
    target_ids = set()
    for listener in listeners.values():
        target_ids |= set(listener.iter_target_group_ids())
    target_groups = get_target_groups(target_ids, max_tries=max_tries)

    # Assign TargetGroup objects to rules
    for listener in listeners.values():
        for rule in listener.rules:
            if rule.target_group_id and rule.target_group_id in target_groups:
                rule.target_group = target_groups[rule.target_group_id]

    return LoadBalancerConfig(alb_id, listeners=listeners, target_groups=target_groups)


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
            # TODO: certificate

            listener = Listener(listener_id, port=listener_port)

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
