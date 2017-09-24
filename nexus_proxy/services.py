# -*- coding: utf-8 -*-
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger('docker-alb')


class NoListeners(Exception):
    pass


class NoTargetGroups(Exception):
    pass


class LoadBalancerConfig(object):
    def __init__(self, identifier: str, listeners: dict = None, listener_groups=None, target_groups: dict = None):
        self.identifier = identifier
        self.listeners_map = listeners
        self.listener_groups = list(listener_groups or [])
        self.target_groups_map = target_groups

    @property
    def has_listeners(self):
        return bool(self.listeners_map)

    @property
    def has_target_groups(self):
        return bool(self.target_groups_map)

    @property
    def listeners(self):
        """
        :rtype: List[Listener]
        """
        return list(self.listeners_map.values())

    @property
    def port_groups(self):
        """
        :rtype: List[PortGroup]
        """
        listeners = self.listeners
        groups = {}  # type: Dict[int, PortGroup]
        for listener in listeners:
            # Do not include listeners for https if the certificate is not valid
            if listener.protocol == 'https' and (listener.certificate is None or not listener.certificate.is_valid):
                continue
            if listener.port not in groups:
                groups[listener.port] = PortGroup('lg_' + str(listener.port), port=listener.port,
                                                  protocol=listener.protocol, listeners=[listener])
            else:
                if groups[listener.port].protocol != listener.protocol:
                    logger.error("Listener %s on port %d has protocol %s while existing listener has protocol %s",
                                 listener.identifier, listener.port, listener.protocol,
                                 groups[listener.port].protocol)
                    continue
                groups[listener.port].listeners.append(listener)
        return list(groups.values())

    @property
    def target_groups(self):
        """
        :rtype: List[TargetGroup]
        """
        return list(self.target_groups_map.values())


class Listener(object):
    def __init__(self, identifier: str, port: int = None, rules: list = None, protocol='http',
                 certificate_name: str = None, certificate: "Certificate" = None):
        self.identifier = identifier
        self.port = port
        self.rules = list(rules or [])
        self.protocol = protocol
        if not certificate_name and certificate:
            certificate_name = certificate.identifier
        self.certificate_name = certificate_name
        self.certificate = certificate

    def __eq__(self, other: "Listener"):
        return self.identifier == other.identifier and self.port == other.port and self.rules == other.rules and \
               self.protocol == other.protocol and self.certificate == other.certificate

    def __repr__(self):
        return "Listener({!r},port={!r},rules={!r},protocol={!r},certificate={!r})".format(
            self.identifier, self.port, self.rules, self.protocol, self.certificate)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")

    def iter_target_group_ids(self):
        for rule in self.rules:
            if rule.target_group_id:
                yield rule.target_group_id


class PortGroup(object):
    def __init__(self, identifier: str, port: int = None, listeners: list = None, protocol='http'):
        """
        Groups a set of listener with the same port, only listeners with the same protocol is added.

        :param identifier: Identifier for the group.
        :param port: The port this listener is bound to.
        :param listeners: Listeners which belongs to this group.
        :param protocol: The protocol used for the specified port.
        """
        self.identifier = identifier
        self.port = port
        self.listeners = list(listeners or [])
        self.protocol = protocol

    def __eq__(self, other: "PortGroup"):
        return self.identifier == other.identifier and self.port == other.port and \
               self.listeners == other.listeners and self.protocol == other.protocol

    def __repr__(self):
        return "PortGroup({!r},port={!r},listeners={!r},protocol={!r})".format(
            self.identifier, self.port, self.listeners, self.protocol)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")


class ListenerGroup(object):
    def __init__(self, identifier: str, listeners: list = None, domains: list = None, certificate_name: str = None,
                 use_certbot: bool = False, certbot: "CertBot" = None):
        """
        Groups configuration for a set of listeners and domains.

        :param identifier: Identifier for the group.
        :param listeners: Listeners which belongs to this group.
        :param domains: List of domains registered to this group.
        :param certificate_name: Name of certificate entry which holds the certificate file
        :param use_certbot: If True then certificates are managed by certbot.
        :param certbot: Configuration for certbot or None if unset.
        """
        self.identifier = identifier
        self.listeners = list(listeners or [])
        self.domains = domains
        self.certificate_name = certificate_name
        self.use_certbot = use_certbot
        self.certbot = certbot

    def __eq__(self, other: "ListenerGroup"):
        return self.identifier == other.identifier and self.domains == other.domains and \
               self.listeners == other.listeners and self.certificate_name == other.certificate_name and \
               self.use_certbot == other.use_certbot and self.certbot == other.certbot

    def __repr__(self):
        return "ListenerGroup({!r},domains={!r},listeners={!r},certificate_name={!r},use_certbot={!r}," \
               "certbot={!r})".format(
                self.identifier, self.domains, self.listeners, self.certificate_name, self.use_certbot, self.certbot)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")


class Rule(object):
    def __init__(self, host: str = None, path: str = None, action: str = None, target_group: "Target" = None,
                 pri: int = 0):
        """

        :param host:
        :param path:
        :param action:
        :param target_group:
        :param pri: Priority value, higher values have higher priority and will be run first.
        """
        self.host = host
        self.path = path
        self.action = action
        self.target_group = target_group
        self.target_group_id = None
        if action and action.startswith("tg:"):
            self.action_type = "forward"
            self.target_group_id = action[3:]
        elif action == 'https':
            self.action_type = "https"
        elif action and action.startswith("status:"):
            self.action_type = "status"
            self.status_code = action[7:]
        self.pri = pri

    def __eq__(self, other: "Rule"):
        return self.path == other.path and self.host == other.host and self.action == other.action and \
               self.pri == other.pri

    def __repr__(self):
        return "Rule(host={!r},path={!r},action={!r},pri={!r})".format(self.host, self.path, self.action, self.pri)


class HealthCheck(object):
    protocol = 'http'
    path = '/'
    port = 'traffic'
    healthy = 2
    unhealthy = 10
    timeout = 4
    interval = 5
    success = []

    def __init__(self, protocol: str = None, path: str = None, port: str = None, healthy: int = None,
                 unhealthy: int = None, timeout: int = None, interval: int = None, success: list = None):
        if protocol:
            self.protocol = protocol
        if path:
            self.path = path
        if port:
            self.port = port
        if healthy:
            self.healthy = healthy
        if unhealthy:
            self.unhealthy = unhealthy
        if timeout:
            self.timeout = timeout
        if interval:
            self.interval = interval
        self.success = list(success or [200])

    def __eq__(self, other: "HealthCheck"):
        return self.protocol == other.protocol and self.path == other.path and self.port == other.port and \
               self.healthy == other.healthy and self.unhealthy == other.unhealthy and self.timeout == other.timeout \
               and self.interval == other.interval and self.success == other.success

    def __repr__(self):
        return "services.HealthCheck(protocol={!r},path={!r},port={!r},health={!r},unhealth={!r},timeout={!r}," \
               "interval={!r},success={!r})".format(
                self.protocol, self.path, self.port, self.healthy, self.unhealthy, self.timeout, self.interval,
                self.success
                )


class TargetGroup(object):
    identifier = None
    protocol = 'http'
    health_check = None
    targets = []

    def __init__(self, identifier: str, targets: list = None, protocol: str = None, health_check: HealthCheck = None):
        self.identifier = identifier
        self.targets = targets or []
        self.protocol = protocol
        self.health_check = health_check

    def __eq__(self, other: "TargetGroup"):
        return self.identifier == other.identifier and self.targets == other.targets and \
               self.protocol == other.protocol and self.health_check == other.health_check

    def __repr__(self):
        return "TargetGroup({!r},targets={!r},protocol={!r},health_check={!r})".format(
            self.identifier, self.targets, self.protocol, self.health_check)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")


class Target(object):
    host = None
    port = None

    def __init__(self, host: str = None, port: str = None):
        self.host = host
        self.port = port

    def __eq__(self, other: "Target"):
        return self.port == other.port and self.host == other.host

    def __repr__(self):
        return "Target(host={!r},port={!r})".format(self.host, self.port)

    @property
    def hash(self):
        m = hashlib.md5()
        m.update("{}:{}".format(self.host, self.port).encode('utf8'))
        return m.hexdigest()


class CertBot(object):
    def __init__(self, identifier: str, target_ip: str = None, target_port: int = None, domains: list = None,
                 certificate_name: str = None):
        """
        Configuration for a certbot

        :param identifier: Identifier for the group.
        :param domains: List of domains registered to this group.
        :param certificate_name: Name of certificate entry which holds the certificate file
        :param target_ip: IP for target running certbot
        :param target_port: Port of target running certbot
        """
        self.identifier = identifier
        self.domains = domains
        self.certificate_name = certificate_name
        self.target_ip = target_ip
        self.target_port = target_port

    def __eq__(self, other: "CertBot"):
        return self.identifier == other.identifier and self.domains == other.domains and \
               self.target_ip == other.target_ip and self.target_port == other.target_port and \
               self.certificate_name == other.certificate_name

    def __repr__(self):
        return "CertBot({!r},target_ip={!r},target_port={!r},domains={!r},certificate_name={!r})".format(
            self.identifier, self.target_ip, self.target_port, self.domains, self.certificate_name)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")


class Certificate(object):
    def __init__(self, identifier: str, pem_data: str = None, email: str = None, domains: list = None,
                 modified: datetime = None, is_valid=None):
        """
        Certificate data.

        :param identifier: Identifier/name for the certificate.
        :param domains: List of domains registered to this group.
        :param modified: Last modified datetime for certificate.
        :param pem_data: Data for PEM file.
        :param email: Email address of owner of certificate.
        :param is_valid: Determines if the certificate is valid for usage. If None it is determined from pem data.
        """
        self.identifier = identifier
        self.domains = domains
        self.modified = modified
        self.pem_data = pem_data
        self.email = email
        self.is_valid = bool(pem_data) if is_valid is None else is_valid

    def __eq__(self, other: "Certificate"):
        return self.identifier == other.identifier and self.domains == other.domains and \
               self.pem_data == other.pem_data and self.email == other.email and \
               self.modified == other.modified and self.is_valid == other.is_valid

    def __repr__(self):
        return "Certificate({!r},pem_data={!r},email={!r},domains={!r},modified={!r},is_valid={!r})".format(
            self.identifier, self.pem_data, self.email, self.domains, self.modified, self.is_valid)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")
