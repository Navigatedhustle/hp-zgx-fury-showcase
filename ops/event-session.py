#!/usr/bin/env python3
"""Presenter actions over the authenticated host shell; never change demo jobs."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from showcase_app.event import Store, presenter_key

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['status', 'reset', 'presenter-code'])
parser.add_argument('--name', default='Conference session')
args = parser.parse_args()
if args.action == 'presenter-code':
    # Print only when explicitly requested in the presenter's own SSH terminal.
    print(presenter_key(create=True))
elif args.action == 'reset':
    session = Store().reset(args.name)
    print('Event counters reset. Jobs and artifacts preserved. Session:', session['name'])
else:
    print(Store().current())
