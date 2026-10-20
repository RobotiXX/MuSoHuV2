#!/usr/bin/env python3
"""Describe the host UTC reference, including an offline phone-set clock.

A phone reference is valid only in the boot where it was set and while NTP is
explicitly disabled. A subsequent wall-clock step invalidates that reference.
"""
import json
import os
from pathlib import Path
import subprocess
import time


def state_path():
    return Path(os.environ.get('MUSOHU_CLOCK_STATE', str(Path.home()/'.local/state/musohu/clock.json')))


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def output(argv):
    try:
        return subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


def reference_status(path=None, ntp=None, now=None, monotonic=None, boot=None):
    if ntp is None:
        text=output(['timedatectl','show','-p','NTP','-p','NTPSynchronized'])
        ntp=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    now=time.time() if now is None else now
    monotonic=time.monotonic() if monotonic is None else monotonic
    boot=boot_id() if boot is None else boot
    result={'source':'unknown','ready':False,'ntp_enabled':ntp.get('NTP')=='yes',
            'ntp_synchronized':ntp.get('NTPSynchronized')=='yes', 'epoch_ms':round(now*1000)}
    plausible=1577836800 <= now < 4102444800
    if plausible and result['ntp_enabled'] and result['ntp_synchronized']:
        result.update(source='ntp',ready=True)
    else:
        try:
            state=json.loads((Path(path) if path else state_path()).read_text())
            age=monotonic-state['monotonic_s']
            clock_error=now-(state['epoch_s']+age)
            if (plausible and not result['ntp_enabled'] and state['boot_id']==boot
                    and state['source']=='phone' and 0 <= age < 86400 and abs(clock_error)<2):
                result.update(source='phone',ready=True,phone_reference=state,
                              reference_age_s=age,wall_clock_change_s=clock_error)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return result
