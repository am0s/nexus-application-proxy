#!/usr/bin/python
from __future__ import print_function

import argparse
import os
import sys
import time
from subprocess import call

from haproxy.generator import generate_config, HAPROXY_TEMPLATE
from haproxy.manager import get_services
from haproxy.services import NoServices
from haproxy.utils import POLL_TIMEOUT, NO_SERVICES_TIMEOUT, ConfigurationError


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)
    args = parser.parse_args(args)
    verbosity = args.verbosity

    current_services = {}
    no_services_timeout = NO_SERVICES_TIMEOUT
    config_mtime = None
    while True:
        try:
            service_config = get_services()

            new_config_mtime = os.path.getmtime(HAPROXY_TEMPLATE)
            if new_config_mtime == config_mtime and (not service_config or service_config == current_services):
                time.sleep(POLL_TIMEOUT)
                continue

            if verbosity >= 0:
                print("config changed. reload haproxy")
            generate_config(service_config)
            config_mtime = os.path.getmtime(HAPROXY_TEMPLATE)
            ret = call(["./reload-haproxy.sh"])
            if ret != 0:
                if verbosity >= 1:
                    print("reloading haproxy returned: ", ret)
                time.sleep(POLL_TIMEOUT)
                continue
            current_services = service_config

        except NoServices:
            if verbosity >= 1:
                print("No services, waiting")
            time.sleep(no_services_timeout)
            pass
        except ConfigurationError as e:
            if verbosity >= 0:
                print("Etcd host is not defined: ", e, file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            if verbosity >= 0:
                print("Error:", e, file=sys.stderr)
            raise

        time.sleep(POLL_TIMEOUT)


if __name__ == "__main__":
    main()
