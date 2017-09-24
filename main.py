#!/usr/bin/env python
# -*- coding: utf-8 -*-
import signal

from nexus_proxy.cli import cli_run_alb

signal.signal(signal.SIGCHLD, signal.SIG_IGN)


if __name__ == "__main__":
    cli_run_alb()
