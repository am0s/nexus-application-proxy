# -*- coding: utf-8 -*-
import os
from jinja2 import Environment, PackageLoader

from .services import LoadBalancerConfig

HAPROXY_TEMPLATE = "templates/haproxy/nexus_proxy.cfg"
DEFAULT_LOG_SIDECAR_PATH = '/sidecar/log'
env = Environment()


def create_context():
    log_path = None
    log_sidecar = os.environ.get('LOG_SIDECAR')
    if log_sidecar:
        log_path = os.environ.get('LOG_SIDECAR_PATH', DEFAULT_LOG_SIDECAR_PATH)
    stats = None
    stats_enabled = os.environ.get('STATS_ENABLED', '')
    if stats_enabled in ('yes', 'true', '1'):
        stats = {
            'auth_user': os.environ.get('STATS_AUTH_USER'),
            'auth_passwd': os.environ.get('STATS_AUTH_PASSWORD'),
            'path': os.environ.get('STATS_PATH', '/_hastats'),
        }
    return {
        'log_sidecar': log_sidecar,
        'log_path': log_path,
        'stats': stats,
    }


def write_config(alb_config: LoadBalancerConfig, template_filename=None, filename=None):
    """
    Writes load balancer configuration to a haproxy config file.

    :param alb_config: Load balancer configuration object
    :param template_filename: Filename to load template from or None to use default.
    :param filename: Filename to write to or None to use default haproxy config
    """
    template = env.from_string(open(template_filename or HAPROXY_TEMPLATE).read())
    with open(filename or "/etc/haproxy.cfg", "w") as f:
        context = create_context()
        context.update({
            'port_groups': alb_config.port_groups,
            'target_groups': alb_config.target_groups,
        })
        f.write(template.render(context))


def generate_config(alb_config: LoadBalancerConfig, template_filename=None) -> str:
    """
    Generates haproxy config from load balancer configuration and returns it.

    :param alb_config: Load balancer configuration object
    :param template_filename: Filename to load template from or None to use default.
    :return: The haproxy config as a string
    """
    template = env.from_string(open(template_filename or HAPROXY_TEMPLATE).read())
    context = create_context()
    context.update({
        'port_groups': alb_config.port_groups,
        'target_groups': alb_config.target_groups,
    })
    return template.render(context)
