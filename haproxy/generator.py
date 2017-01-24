# -*- coding: utf-8 -*-
from jinja2 import Environment, PackageLoader

HAPROXY_TEMPLATE = "templates/haproxy/haproxy.cfg"
#env = Environment(loader=PackageLoader('templates'))
env = Environment()


def generate_config(config, template_filename=None):
    template = env.from_string(open(template_filename or HAPROXY_TEMPLATE).read())
    with open("/etc/haproxy.cfg", "w") as f:
        f.write(template.render(config=config))
