#!/usr/bin/env python3
"""Record through the helmet's native services using the same client as the web app."""
import argparse
import os
from pathlib import Path
import signal
import sys
import time
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'web-app'))
from process_manager import ProcessManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topics', type=Path, default=ROOT/'musohu_ws/src/helmet_bringup/config/recording_topics.yaml')
    parser.add_argument('--output', type=Path, default=Path.home()/'helmet_bags', help='Must be inside the running recorder output directory')
    parser.add_argument('--label', default='walk')
    parser.add_argument('--duration', type=float, help='Optional seconds after confirmed startup; otherwise stop with Ctrl-C')
    args = parser.parse_args()
    if args.duration is not None and args.duration <= 0:
        parser.error('--duration must be positive')
    topics = yaml.safe_load(args.topics.read_text())['topics']
    os.environ['MUSOHU_BAG_DIR'] = str(args.output.expanduser().resolve())
    manager = ProcessManager(ROOT/'web-app', {})
    interrupted = False

    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        session = manager.start('record_bag', label=args.label, topics=topics)
        print('Starting:', session['bag_path'], flush=True)
        deadline = None
        ready = False
        while not interrupted:
            state = manager.status()['record_bag']
            if state['status'] == 'recording' and not ready:
                ready = True
                deadline = time.monotonic()+args.duration if args.duration else None
                print('Recording confirmed; Ctrl-C to finalize.', flush=True)
            if state['status'] == 'failed':
                raise RuntimeError(state.get('error'))
            if state['status'] == 'stopped' or deadline and time.monotonic() >= deadline:
                break
            time.sleep(.2)
        final = manager.stop('record_bag')
        if final.get('status') == 'failed':
            raise RuntimeError(final.get('error'))
        print('Finalized:' if final.get('finalized') else 'Cancelled:', final.get('bag_path'), flush=True)
    finally:
        manager.close()


if __name__ == '__main__':
    main()
