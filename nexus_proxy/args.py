# -*- coding: utf-8 -*-
import argparse
import os


def process_verbosity(args):
    verbosity = os.environ.get('VERBOSITY_LEVEL', None)
    if verbosity is not None:
        try:
            verbosity = int(verbosity)
        except ValueError:
            verbosity = None
    if verbosity is None:
        verbosity = args.verbosity
    args.verbosity = verbosity


def setup_common_args(parser: argparse.ArgumentParser):
    parser.set_defaults(verbosity=0, etcd_host=None)
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count',
                        help="increase verbosity level")
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1,
                        help="suppress non-error messages")
    parser.add_argument("--etcd-host", dest="etcd_host", metavar="HOST",
                        help="hostname for etcd server, if unset uses ETCD_HOST env variable")


def setup_listener_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'listener' command, contains sub-commands.
    """
    parser = command_parsers.add_parser(
        'listener', help='Listener management')  # type: argparse.ArgumentParser
    command_parsers = parser.add_subparsers(dest="listener_cmd")
    setup_register_cmd(command_parsers)
    setup_register_vhost_cmd(command_parsers)


def setup_register_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'listener register-docker' command, register configuration written by docker-gen.
    """
    parser = command_parsers.add_parser(
        'register-docker', help='Register listeners from docker-gen configuration')  # type: argparse.ArgumentParser
    setup_common_args(parser)


def setup_register_vhost_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'listener register-vhost' command, register virtual-host listener and optionally targets.
    """
    parser = command_parsers.add_parser(
        'register-vhost', help='Register virtual-host listener')  # type: argparse.ArgumentParser
    setup_common_args(parser)

    parser.add_argument("--reset", default=None,
                        help="Resets any existing configuration before writing the new configuration")
    parser.add_argument("--id", default=None,
                        help="ID of target group and listener group, defaults to first domain")
    parser.add_argument("--port", default='https',
                        help="Which port to use for listener in load-balancer, specify a number "
                             "or use http for HTTP only, https for https only or mixed for http and https. "
                             "defaults to https")
    parser.add_argument("--certificate", default=None,
                        help="Path to certificate file (pem) to upload")
    parser.add_argument("--certbot", action="store_true", default=False,
                        help="Auto creation of certificate using letsencrypt")
    parser.add_argument("--certificate-name", default=None,
                        help="Name of certificate entry to use, default is to use ID of listener group")
    parser.add_argument("virtual_host",
                        help="domains to register")
    parser.add_argument("target",
                        help="The hostname/ip of target, either use <host>:<port> or just <host>. "
                             "Defaults to port 80 if no port is set. Specify multiple targets with "
                             "a comma separated list")


def setup_certificate_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'certificate' command, contains sub-commands.
    """
    parser = command_parsers.add_parser(
        'certificate', help='Certificate management')  # type: argparse.ArgumentParser
    command_parsers = parser.add_subparsers(dest="cert_cmd")
    setup_upload_certificate_cmd(command_parsers)
    setup_renew_certificate_cmd(command_parsers)


def setup_upload_certificate_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'certificate upload' command, uploads certificate files.
    """
    parser = command_parsers.add_parser('upload', help='Upload certificates to store')  # type: argparse.ArgumentParser
    setup_common_args(parser)

    parser.add_argument("certificate-name", default=None,
                        help="Name of certificate entry to use, must match name used in listeners")
    parser.add_argument("--certificate", default=None,
                        help="Path to certificate file (pem) to upload containing full chain and private key")
    parser.add_argument("--full-chain", default=None,
                        help="Path to file containing full chain of certificates")
    parser.add_argument("--private-key", default=None,
                        help="Path to file containing private key")

    parser.add_argument("--email", default=None,
                        help="Email address of owner of certificate")
    parser.add_argument("--domain", dest="domains", metavar="domain", default=[], nargs="*",
                        help="Domain name used in certificate, can be specified multiple times")
    # TODO: See if domains (and email) can be read from certificate using ssl tools


def setup_renew_certificate_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'certificate upload' command, uploads certificate files.
    """
    parser = command_parsers.add_parser(
        'renew', help='Renew certificates that are auto-managed (letsencrypt)')  # type: argparse.ArgumentParser
    setup_common_args(parser)

    parser.add_argument("--host-name", default=None,
                        help="hostname/ip of host where certbot may be reached, if running in a docker container use"
                             "the public ip of the docker host")
    parser.add_argument("--host-port", default=None,
                        help="port where certbot may be reached (on host-ip)")
    parser.add_argument("--alb-identifier", dest="alb_id", default=None,
                        help="Identifier for application load balancer to check for certs, if unset renews all ALBs")
    parser.add_argument("--email", default=None,
                        help="Email address to register certificates to")


def setup_alb_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'alb' command, contains sub-commands.
    """
    parser = command_parsers.add_parser(
        'alb', help='Application Load Balancer management')  # type: argparse.ArgumentParser

    command_parsers = parser.add_subparsers(dest="alb_cmd")
    setup_alb_run_cmd(command_parsers)
    setup_alb_show_cmd(command_parsers)


def setup_alb_run_cmd(command_parsers: argparse._SubParsersAction):
    parser = command_parsers.add_parser(
        'run', help='Start an application load balancer service')  # type: argparse.ArgumentParser
    setup_common_args(parser)

    parser.add_argument("--alb-identifier", dest="alb_id", default='vhost',
                        help="Identifier for application load balancer to setup, defaults to vhost")


def setup_alb_show_cmd(command_parsers: argparse._SubParsersAction):
    parser = command_parsers.add_parser(
        'run', help='Show configuration for an Application Load Balancer')  # type: argparse.ArgumentParser
    setup_common_args(parser)

    parser.add_argument("--alb-identifier", dest="alb_id", default='vhost',
                        help="Identifier for application load balancer to setup, defaults to vhost")
    parser.add_argument("--haproxy", dest="show_haproxy", action='store_true', default=False,
                        help="Show haproxy configuration")
