#!/usr/bin/env python3
import argparse
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from subprocess import call

import jinja2

from .args import process_verbosity, setup_alb_cmd, setup_certificate_cmd, setup_listener_cmd, setup_common_args
from .generator import write_config, generate_config, HAPROXY_TEMPLATE
from .manager import get_alb, transfer_certificates, mark_certbots_ready
from .register import register_certbot, etcd_client, wait_certbot_ready, unregister_certbot, register_certificate, \
    upload_certificate, register_vhost, auto_register_docker
from .services import NoListeners, NoTargetGroups
from .utils import POLL_TIMEOUT, NO_SERVICES_TIMEOUT, ConfigurationError

logging.basicConfig(style='$')
logger = logging.getLogger('docker-alb')
logger.setLevel(level=logging.DEBUG)
debug_console = logging.StreamHandler(stream=sys.stdout)
debug_console.setLevel(logging.DEBUG)
debug_console.setFormatter(logging.Formatter('${levelname}:${name}:${message}', style='$'))
logger.propagate = False

logger.addHandler(debug_console)


class MissingArgumentError(Exception):
    """
    Error used when arguments are missing, passed string is printed as output
    """


def cli_manage(args=None):
    parser = argparse.ArgumentParser()
    setup_common_args(parser)

    command_parsers = parser.add_subparsers(dest="cmd")
    setup_alb_cmd(command_parsers)
    setup_listener_cmd(command_parsers)
    setup_certificate_cmd(command_parsers)

    args = parser.parse_args(args)
    process_verbosity(args)

    cmd = args.cmd

    try:
        if cmd == "alb":
            alb_cmd = args.alb_cmd
            if alb_cmd == 'run':
                cli_run_alb(args)
            elif alb_cmd == 'show':
                cli_show_config(args)
            else:
                raise MissingArgumentError("Please select sub-commands for 'alb'")
        elif cmd == "listener":
            listener_cmd = args.listener_cmd
            if listener_cmd == 'register-docker':
                auto_register_docker(args)
            elif listener_cmd == 'register-vhost':
                register_vhost(args)
            else:
                raise MissingArgumentError("Please select sub-commands for 'listener'")
        elif cmd == "certificate":
            cert_cmd = args.cert_cmd
            if cert_cmd == 'upload':
                upload_certificate(args)
            elif cert_cmd == 'renew':
                cli_renew_certs(args)
            else:
                raise MissingArgumentError("Please select sub-commands for 'certificate'")
        else:
            sys.exit(1)
    except MissingArgumentError as e:
        if args.verbosity >= 0:
            print(e, file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        if args.verbosity >= 0:
            print("Unknown error:", e, file=sys.stderr)
        sys.exit(1)


def cli_run_alb(args):
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
            alb_config = get_alb(alb_id, with_listener_group=True)

            new_config_mtime = int(os.path.getmtime(HAPROXY_TEMPLATE))
            if verbosity >= 3:
                logger.debug("Config new mtime: %s, old mtime: %s", new_config_mtime, config_mtime)
            if new_config_mtime == config_mtime and alb_config.listeners_map == current_listeners_map:
                time.sleep(POLL_TIMEOUT)
                continue

            if verbosity >= 1:
                logger.debug("Config changed. Transferring certificates")
            transfer_certificates(alb_config)

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
                logger.info("Reloading haproxy")
            ret = call("./reload-haproxy.sh", shell=True)
            if ret != 0:
                logger.error("Reloading haproxy returned non-zero value: %s", ret)
                time.sleep(POLL_TIMEOUT)
                continue
            current_listeners_map = alb_config.listeners_map.copy()
            mark_certbots_ready(alb_config)

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


def cli_show_config(args):
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


def cli_renew_certs(args):
    verbosity = args.verbosity
    alb_id = args.alb_id or os.environ.get('ALB_ID')
    host_name = args.host_name or os.environ.get('HOST_NAME')
    host_port = args.host_port or os.environ.get('HOST_PORT')
    if not host_name:
        logger.error("No host IP set, use --host-ip option or set HOST_NAME environment variable")
        sys.exit(1)
    if not host_port:
        logger.error("No host port set, use --host-port option or set HOST_PORT environment variable")
        sys.exit(1)
    email = args.email or os.environ.get("EMAIL")
    if not email:
        logger.error("No email address set, use --email or set EMAIL environment variable")
        sys.exit(1)

    host_ip = socket.gethostbyname(host_name)

    client = etcd_client(args.etcd_host)

    def scan_alb(alb_identifier):
        alb_config = get_alb(alb_identifier, with_listener_group=True)
        for listener_group in alb_config.listener_groups:  # type: ListenerGroup
            logger.debug(listener_group)
            if not listener_group.use_certbot or not listener_group.domains:
                continue
            # certbot = listener_group.certbot  # type: CertBot
            try:
                register_certbot(client, alb=alb_identifier, listener_id=listener_group.identifier,
                                 domains=listener_group.domains, target=[host_ip, host_port],
                                 certificate_name=listener_group.certificate_name)
                logger.debug("Waiting for certbot %s in ALB %s to be setup", listener_group.identifier, alb_identifier)
                if not wait_certbot_ready(client, alb=alb_identifier, listener_id=listener_group.identifier):
                    logger.error("Failed to wait for ALB '{}' to setup up certbot config for id={}, domains={}".format(
                        alb_identifier, listener_group.identifier, listener_group.domains))
                    unregister_certbot(client, alb=alb_identifier, listener_id=listener_group.identifier)
                    continue

                register_certificate(client, certificate_name=listener_group.identifier, domains=listener_group.domains,
                                     email=email, modified=datetime.now())
                domain_args = sum([["-d", domain] for domain in listener_group.domains], [])
                certbot_args = ["certbot", "certonly", "--verbose", "--noninteractive", "--standalone",
                                "--preferred-challenges", "http", "--agree-tos", "--email", email,
                                "--cert-name", listener_group.identifier] + domain_args
                logger.debug("certbot command: %s", " ".join(certbot_args))
                input("Press enter")
                call(certbot_args)
                input("Press enter")
            finally:
                # Certbot done or failed, unregister from listener
                unregister_certbot(client, alb=alb_identifier, listener_id=listener_group.identifier)

    try:
        scan_alb(alb_id)
    except (NoListeners, NoTargetGroups):
        if verbosity >= 1:
            print("No configuration found")
    except ConfigurationError as e:
        if verbosity >= 0:
            print("Etcd host is not defined: ", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli_manage()
