# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import sys
import json

from nexus_proxy.manager import get_listeners
from nexus_proxy.services import NoListeners
from nexus_proxy.utils import ConfigurationError


def main(args=None):
    parser = argparse.ArgumentParser(usage=u"Exports configuration to JSON format")
    parser.add_argument("--verbose", "-v", dest="verbosity", action='count', default=0)
    parser.add_argument("--quiet", "-q", dest="verbosity", action='store_const', const=-1)
    args = parser.parse_args(args)
    verbosity = args.verbosity

    try:
        service_config = get_listeners()
        print(json.dumps(service_config, ensure_ascii=False, indent=4))
    except ConfigurationError as e:
        if verbosity >= 0:
            print("Etcd host is not defined: ", e, file=sys.stderr)
        sys.exit(1)
    except NoListeners:
        if verbosity >= 0:
            print("No services", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
