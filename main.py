#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import signal

from haproxy.cli import main

signal.signal(signal.SIGCHLD, signal.SIG_IGN)


if __name__ == "__main__":
    main()
