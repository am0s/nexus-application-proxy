# -*- coding: utf-8 -*-
import hashlib
import logging

logger = logging.getLogger('docker-alb')


class NoListeners(Exception):
    pass


class NoTargetGroups(Exception):
    pass


class LoadBalancerConfig(object):
    def __init__(self, identifier: str, listeners: dict = None, target_groups: dict = None):
        self.identifier = identifier
        self.listeners_map = listeners
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
    def listener_groups(self):
        """
        :rtype: List[ListenerGroup]
        """
        listeners = self.listeners
        groups = {}  # type: Dict[int, ListenerGroup]
        for listener in listeners:
            if listener.port not in groups:
                groups[listener.port] = ListenerGroup('lg_' + str(listener.port), port=listener.port,
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
    def __init__(self, identifier: str, port: int = None, rules: list = None, protocol='http'):
        self.identifier = identifier
        self.port = port
        self.rules = list(rules or [])
        self.protocol = protocol

    def __eq__(self, other: "Listener"):
        return self.identifier == other.identifier and self.port == other.port and self.rules == other.rules and \
               self.protocol == other.protocol

    def __repr__(self):
        return "Listener({!r},port={!r},rules={!r})".format(
            self.identifier, self.port, self.rules)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")

    def iter_target_group_ids(self):
        for rule in self.rules:
            if rule.target_group_id:
                yield rule.target_group_id


class ListenerGroup(object):
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

    def __eq__(self, other: "ListenerGroup"):
        return self.identifier == other.identifier and self.port == other.port and \
               self.listeners == other.listeners and self.protocol == other.protocol

    def __repr__(self):
        return "ListenerGroup({!r},port={!r},listeners={!r},protocol={!r})".format(
            self.identifier, self.port, self.listeners, self.protocol)

    @property
    def slug(self):
        return self.identifier.replace(".", "_").replace("-", "_")


class Rule(object):
    def __init__(self, host: str = None, path: str = None, action: str = None, target_group: "Target" = None):
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

    def __eq__(self, other: "Rule"):
        return self.path == other.path and self.host == other.host and self.action == other.action

    def __repr__(self):
        return "Rule(host={!r},path={!r},action={!r})".format(self.host, self.path, self.action)


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
