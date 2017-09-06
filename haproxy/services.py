# -*- coding: utf-8 -*-
import hashlib


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
        return list(self.listeners_map.values())

    @property
    def target_groups(self):
        return list(self.target_groups_map.values())


class Listener(object):
    def __init__(self, identifier: str, port: int = None, rules: list = None):
        self.identifier = identifier
        self.port = port
        self.rules = list(rules or [])

    def __eq__(self, other):
        return self.identifier == other.identifier and self.port == other.port and self.rules == other.rules

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


class Rule(object):
    def __init__(self, host: str = None, path: str = None, action: str = None, target_group: "Target" = None):
        self.host = host
        self.path = path
        self.action = action
        self.target_group = target_group
        self.target_group_id = None
        if action and action.startswith("tg:"):
            self.target_group_id = action[3:]

    def __eq__(self, other: "Rule"):
        return self.path == other.path and self.host == other.host and self.action == other.action

    def __repr__(self):
        return "Rule(host={!r},path={!r},action={!r})".format(self.host, self.path, self.action)


class TargetGroup(object):
    identifier = None
    targets = []

    def __init__(self, identifier: str, targets: list = None):
        self.identifier = identifier
        self.targets = targets or []

    def __eq__(self, other):
        return self.identifier == other.identifier and self.targets == other.targets

    def __repr__(self):
        return "TargetGroup({!r},targets={!r})".format(
            self.identifier, self.targets)

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
