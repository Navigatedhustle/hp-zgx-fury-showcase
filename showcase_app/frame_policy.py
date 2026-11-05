"""Permit the local station chooser without permitting arbitrary framing sites."""
import re


def station_ancestors(hostname):
    if hostname in ('localhost', '127.0.0.1', '::1'):
        return "'self' http://localhost:8080 http://127.0.0.1:8080"
    if hostname and re.fullmatch(r'[a-z0-9-]+\.tail[a-z0-9]+\.ts\.net', hostname):
        return "'self' https://" + hostname
    return "'self'"
