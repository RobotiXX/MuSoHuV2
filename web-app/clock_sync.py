"""Offline browser → host → LiDAR synchronization, serialized against ROS starts."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

SCRIPTS=Path(__file__).resolve().parents[1]/'musohu_ws/src/helmet_bringup/scripts'
sys.path.insert(0,str(SCRIPTS))
from clock_reference import reference_status, state_path, boot_id, output
from process_manager import atomic_json


def active_sensor_processes():
    found=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            argv=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (OSError, ProcessLookupError):
            continue
        names={Path(a).name for a in argv[:3]}
        if (names & {'witmotion_ros_node','rslidar_sdk_node','respeaker_node','recording_worker.py'}
                or 'component_container_isolated' in names and any('zed' in a for a in argv)
                or len(argv)>3 and Path(argv[1]).name=='ros2' and (argv[2:4]==['bag','record']
                    or argv[2]=='launch' and argv[3] in {'helmet_bringup','zed_wrapper','rslidar_sdk','respeaker_ros','witmotion_ros'})):
            found.append(proc.name)
    return found


class ClockSync:
    def __init__(self, manager):
        self.manager=manager
        self.busy=False
        self.last_result=None

    def status(self):
        state=reference_status()
        state.update(busy=self.busy,ptp_service=output(['systemctl','is-active','musohu-ptp']),
                     last_result=self.last_result)
        return state

    def change(self, epoch_ms=None, internet=False):
        if not internet and (isinstance(epoch_ms,bool) or not isinstance(epoch_ms,(int,float))
                or not math.isfinite(epoch_ms) or not 1577836800000 <= epoch_ms < 4102444800000):
            raise ValueError('Phone time must be a valid UTC epoch in milliseconds (2020–2099).')
        manager=self.manager
        with manager.lock:
            manager.status()
            if self.busy or manager.processes or manager.stopping or active_sensor_processes():
                raise ValueError('Stop recording and all sensor launches before changing system time.')
            self.busy=True
            manager.clock_busy=True
        previous_ntp=reference_status()['ntp_enabled']
        changed=False
        try:
            if internet:
                self.run(['/usr/bin/timedatectl','set-ntp','true'])
                self.last_result={'host_synced':False,'lidar_ready':False,
                                  'message':'Internet time enabled; waiting for NTP before starting sensors.'}
                return self.status()
            # Do not let an internet service step the clock later in an offline bag.
            self.run(['/usr/bin/timedatectl','set-ntp','false'])
            if output(['timedatectl','show','-p','NTP','--value'])!='no':
                raise RuntimeError('Unable to disable NTP; host clock was not changed.')
            sent=time.monotonic()
            self.run(['/usr/bin/date','-u','-s',f'@{epoch_ms/1000:.3f}'])
            changed=True
            now=time.time();mono=time.monotonic()
            if abs(now-epoch_ms/1000) > 2+(mono-sent):
                raise RuntimeError('Host clock did not match the requested phone time.')
            state={'source':'phone','boot_id':boot_id(),'epoch_s':now,'monotonic_s':mono,
                   'phone_epoch_ms':epoch_ms,'set_at_utc':datetime.now(timezone.utc).isoformat(),
                   'method':'browser send time; local HTTP/command latency is uncalibrated',
                   'command_elapsed_s':mono-sent}
            path=state_path();path.parent.mkdir(parents=True,exist_ok=True);atomic_json(path,state)
            # ptp4l in free-running software-source mode reads CLOCK_REALTIME:
            # no Ethernet PHC exists and no separate clock-setting command is needed.
            deadline=time.monotonic()+35
            error='PTP source is not active'
            while time.monotonic()<deadline:
                if output(['systemctl','is-active','musohu-ptp'])=='active':
                    try:
                        check=subprocess.run(['/usr/bin/python3',str(SCRIPTS/'check_lidar_clock.py'),
                            '--config',str(manager.workspace/'src/helmet_bringup/config/lidar_params.yaml')],
                            text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=6)
                    except subprocess.TimeoutExpired:
                        error='LiDAR clock check timed out'
                        continue
                    if check.returncode==0:
                        self.last_result={'host_synced':True,'lidar_ready':True,
                            'message':'Phone time applied; LiDAR PTP lock and packet epoch verified.',
                            'lidar_check':check.stdout.strip()}
                        return self.status()
                    error=check.stdout.strip()
                time.sleep(.5)
            self.last_result={'host_synced':True,'lidar_ready':False,
                'message':'Phone time applied; LiDAR is not ready. Wait for PTP lock before starting sensors.',
                'error':error}
            return self.status()
        except Exception:
            if not changed and previous_ntp:
                try:self.run(['/usr/bin/timedatectl','set-ntp','true'])
                except RuntimeError:pass
            raise
        finally:
            with manager.lock:
                self.busy=False
                manager.clock_busy=False

    @staticmethod
    def run(argv):
        result=subprocess.run(['sudo','-n',*argv],text=True,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,timeout=8)
        if result.returncode:
            raise RuntimeError('Clock permissions unavailable: '+result.stderr.strip()+
                               ' Run scripts/setup/setup_time_sync_permissions.sh in a terminal.')
