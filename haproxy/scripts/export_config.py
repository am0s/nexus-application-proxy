# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import sys
import json

from haproxy.manager import get_services
from haproxy.services import NoServices
from haproxy.utils import ConfigurationError


def main(args=None):
    parser = argparse.ArgumentParser(usage=u"Exports configuration to JSON format")
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)
    args = parser.parse_args(args)
    verbosity = args.verbosity

    try:
        service_config = get_services()
        print(json.dumps(service_config, ensure_ascii=False, indent=4))
    except ConfigurationError as e:
        if verbosity >= 0:
            print("Etcd host is not defined: ", e, file=sys.stderr)
        sys.exit(1)
    except NoServices:
        if verbosity >= 0:
            print("No services", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
