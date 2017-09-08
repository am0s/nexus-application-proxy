#!/usr/bin/env python3
import argparse
import logging
import os
import subprocess
import sys
import time
from subprocess import call

import jinja2

from .generator import write_config, generate_config, HAPROXY_TEMPLATE
from .services import NoListeners, NoTargetGroups
from .utils import POLL_TIMEOUT, NO_SERVICES_TIMEOUT, ConfigurationError
from .manager import get_alb

logger = logging.getLogger('docker-alb')


def cli_run_alb(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)
    parser.add_argument("--alb-identifier", dest="alb_id", default='vhost',
                        help="Identifier for application load balancer to setup, defaults to vhost")
    args = parser.parse_args(args)
    verbosity = os.environ.get('VERBOSITY_LEVEL', None)
    if verbosity is not None:
        try:
            verbosity = int(verbosity)
        except ValueError:
            verbosity = None
    if verbosity is None:
        verbosity = args.verbosity
    alb_id = os.environ.get('ALB_ID', args.alb_id)
    if verbosity >= 1:
        logger.info("Initializing ALB with identifier: %s", alb_id)

    current_listeners_map = {}
    no_services_timeout = NO_SERVICES_TIMEOUT
    config_mtime = None
    if verbosity >= 0:
        logger.info("Polling configuration from etcd")
    while True:
        try:
            alb_config = get_alb(alb_id)

            new_config_mtime = int(os.path.getmtime(HAPROXY_TEMPLATE))
            if verbosity >= 3:
                logger.debug("Config new mtime: %s, old mtime: %s", new_config_mtime, config_mtime)
            if new_config_mtime == config_mtime and alb_config.listeners_map == current_listeners_map:
                time.sleep(POLL_TIMEOUT)
                continue

            if verbosity >= 1:
                logger.debug("Config changed. reload haproxy")
            # Write to a new config file and verify it
            write_config(alb_config, filename="/etc/haproxy.new.cfg")
            config_mtime = int(os.path.getmtime(HAPROXY_TEMPLATE))
            ret = call("./configtest-haproxy.sh /etc/haproxy.new.cfg", shell=True, stdout=subprocess.DEVNULL)
            if ret != 0:
                logger.error(
                    "haproxy configuration is not valid, keeping old config, see /etc/haproxy.new.cfg for details")
                time.sleep(POLL_TIMEOUT)
                continue

            if verbosity >= 2:
                logger.error("Reloading haproxy")
            ret = call("./reload-haproxy.sh", shell=True)
            if ret != 0:
                logger.error("Reloading haproxy returned non-zero value: %s", ret)
                time.sleep(POLL_TIMEOUT)
                continue
            current_listeners_map = alb_config.listeners_map.copy()

        except NoListeners:
            if verbosity >= 1:
                logger.info("No services, waiting")
            time.sleep(no_services_timeout)
            pass
        except ConfigurationError as e:
            if verbosity >= 0:
                logger.error("Etcd host is not defined: %s", e)
            sys.exit(1)
        except jinja2.exceptions.TemplateError as e:
            if verbosity >= 0:
                logger.error("Error while rendering jinja2 template: %s", e)
            time.sleep(no_services_timeout)
            pass
        except Exception as e:
            if verbosity >= 0:
                logger.exception("Unknown error")
            raise

        time.sleep(POLL_TIMEOUT)


def cli_show_config(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=1)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)
    parser.add_argument("--alb-identifier", dest="alb_id", default='vhost',
                        help="Identifier for application load balancer to setup, defaults to vhost")
    parser.add_argument("--haproxy", dest="show_haproxy", action='store_true', default=False,
                        help="Show haproxy configuration")
    args = parser.parse_args(args)
    verbosity = os.environ.get('VERBOSITY_LEVEL', None)
    if verbosity is not None:
        try:
            verbosity = int(verbosity)
        except ValueError:
            verbosity = None
    if verbosity is None:
        verbosity = args.verbosity
    alb_id = os.environ.get('ALB_ID', args.alb_id)

    try:
        alb_config = get_alb(alb_id, with_listener_group=True)

        if args.show_haproxy:
            print(generate_config(alb_config))
        else:
            print("ALB: {}".format(alb_config.identifier))
            print("Listeners:")
            for listener in alb_config.listeners:
                print("`- {}".format(listener.identifier))
                print("   port: {}".format(listener.port))
                print("   rules:")
                for rule in listener.rules:
                    print("   `- host: {}, path: {}, action: {}".format(rule.host or '-', rule.path or '-',
                                                                        rule.action))
            print("Listener groups:")
            for listener_group in alb_config.listener_groups:
                print("`- {}".format(listener_group.identifier))
                print("   domains: {}".format(listener_group.domains))
                print("   listeners: {}".format(listener_group.listeners))
                print("   certificate name: {}".format(listener_group.certificate_name))
                print("   use certbot: {}".format(listener_group.use_certbot))
            print("Target Groups:")
            for target_group in alb_config.target_groups:
                print("`- {}".format(target_group.identifier))
                if target_group.health_check:
                    health = target_group.health_check
                    print("  `- Health check: ")
                    print("    `- protocol: {}".format(health.protocol))
                    print("    `- path: {}".format(health.path))
                    print("    `- port: {}".format(health.port))
                    print("    `- healthy: {}".format(health.healthy))
                    print("    `- unhealthy: {}".format(health.unhealthy))
                    print("    `- timeout: {}".format(health.timeout))
                    print("    `- interval: {}".format(health.interval))
                    print("    `- success: {}".format(health.success))
                else:
                    print("  `- No health check")
                for target in target_group.targets:
                    print("   `- {}:{}".format(target.host, target.port))

    except (NoListeners, NoTargetGroups):
        if verbosity >= 1:
            print("No configuration found")
    except ConfigurationError as e:
        if verbosity >= 0:
            print("Etcd host is not defined: ", e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if verbosity >= 0:
            print("Unknown error:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli_run_alb()
