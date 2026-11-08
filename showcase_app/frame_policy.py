"""Permit the local station chooser without permitting arbitrary framing sites."""
import re


def station_ancestors(hostname):
    if hostname in ('localhost', '127.0.0.1', '::1'):
        return "'self' http://localhost:8080 http://127.0.0.1:8080"
    from showcase_app.security import configured_hosts, LOOPBACK
    if hostname in configured_hosts() - LOOPBACK:
        return "'self' https://" + hostname
    return "'self'"
