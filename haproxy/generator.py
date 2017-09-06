# -*- coding: utf-8 -*-
import os
from jinja2 import Environment, PackageLoader

from .services import LoadBalancerConfig

HAPROXY_TEMPLATE = "templates/haproxy/haproxy.cfg"
DEFAULT_LOG_SIDECAR_PATH = '/sidecar/log'
env = Environment()


def create_context():
    log_path = None
    log_sidecar = os.environ.get('LOG_SIDECAR')
    if log_sidecar:
        log_path = os.environ.get('LOG_SIDECAR_PATH', DEFAULT_LOG_SIDECAR_PATH)
    stats_enabled = os.environ.get('STATS_ENABLED', '')
    stats_auth_user = os.environ.get('STATS_AUTH_USER')
    stats_auth_passwd = os.environ.get('STATS_AUTH_PASSWORD')
    return {
        'log_sidecar': log_sidecar,
        'log_path': log_path,
        'stats_enabled': stats_enabled,
        'stats_auth_user': stats_auth_user,
        'stats_auth_passwd': stats_auth_passwd,
    }


def write_config(alb_config: LoadBalancerConfig, template_filename=None):
    template = env.from_string(open(template_filename or HAPROXY_TEMPLATE).read())
    with open("/etc/haproxy.cfg", "w") as f:
        context = create_context()
        context.update({
            'listeners': alb_config.listeners,
            'target_groups': alb_config.target_groups,
        })
        f.write(template.render(context))


def generate_config(alb_config: LoadBalancerConfig, template_filename=None):
    template = env.from_string(open(template_filename or HAPROXY_TEMPLATE).read())
    context = create_context()
    context.update({
        'listeners': alb_config.listeners,
        'target_groups': alb_config.target_groups,
    })
    return template.render(context)
