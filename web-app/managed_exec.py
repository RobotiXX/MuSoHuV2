"""Exec a sensor launch and interrupt it if its owning API process dies."""
import ctypes
import os
import signal
import sys

parent = os.getppid()
if parent == 1 or ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGINT, 0, 0, 0) != 0:
    raise SystemExit('Unable to register sensor launch ownership')
if os.getppid() != parent:
    raise SystemExit(130)
os.execvp(sys.argv[1], sys.argv[1:])
