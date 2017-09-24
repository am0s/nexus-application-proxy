#!/usr/bin/env python
# -*- coding: utf-8 -*-
import signal

from haproxy.cli import cli_manage

signal.signal(signal.SIGCHLD, signal.SIG_IGN)


if __name__ == "__main__":
    cli_manage()
