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


def setup_certificate_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'certificate' command, contains sub-commands.
    """
    parser = command_parsers.add_parser('certificate', help='a help')  # type: argparse.ArgumentParser
    command_parsers = parser.add_subparsers(dest="cert_cmd")
    setup_upload_certificate_cmd(command_parsers)
    setup_renew_certificate_cmd(command_parsers)


def setup_upload_certificate_cmd(command_parsers: argparse._SubParsersAction):
    """
    Setup 'certificate upload' command, uploads certificate files.
    """
    parser = command_parsers.add_parser('upload', help='Upload certificates to store')  # type: argparse.ArgumentParser

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

    parser.add_argument("--alb-identifier", dest="alb_id", default='vhost',
                        help="Identifier for application load balancer to setup, defaults to vhost")


def setup_alb_show_cmd(command_parsers: argparse._SubParsersAction):
    parser = command_parsers.add_parser(
        'run', help='Show configuration for an Application Load Balancer')  # type: argparse.ArgumentParser

    parser.add_argument("--alb-identifier", dest="alb_id", default='vhost',
                        help="Identifier for application load balancer to setup, defaults to vhost")
    parser.add_argument("--haproxy", dest="show_haproxy", action='store_true', default=False,
                        help="Show haproxy configuration")
