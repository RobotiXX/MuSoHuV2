"""Own ROS process groups and report recorder-confirmed session state."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import yaml


TOPIC = re.compile(r'^/[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*$')
LABEL = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


class ProcessManager:
    @staticmethod
    def signal_group(pid, sig):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    def reap_group(self, pid):
        self.signal_group(pid, signal.SIGINT)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        self.signal_group(pid, signal.SIGTERM)
        time.sleep(0.1)
        self.signal_group(pid, signal.SIGKILL)

    def __init__(self, base_dir, config):
        self.base = Path(base_dir).resolve()
        ros = config.get('ros', {})
        self.workspace = self.resolve(os.environ.get('MUSOHU_WORKSPACE', ros.get('workspace', '../musohu_ws')))
        self.underlay = Path(ros.get('underlay', '/opt/ros/humble/setup.bash'))
        self.output = self.resolve(os.environ.get('MUSOHU_BAG_DIR', ros.get('bag_directory', '~/helmet_bags')))
        self.manifest = self.resolve(ros.get('topic_manifest', '../musohu_ws/src/helmet_bringup/config/recording_topics.yaml'))
        self.profiles = {name:self.resolve(path) for name,path in ros.get('topic_profiles', {}).items()}
        self.logs = self.resolve(ros.get('process_log_directory', 'logs'))
        self.stop_timeout = float(ros.get('stop_timeout_seconds', 30))
        self.lock = threading.RLock()
        self.processes = {}
        self.sessions = {}
        self.last = {}
        self.stopping = set()
        self.clock_busy = False

    def resolve(self, value):
        path = Path(value).expanduser()
        return (self.base / path).resolve() if not path.is_absolute() else path.resolve()

    def defaults(self):
        topics = yaml.safe_load(self.manifest.read_text()).get('topics', [])
        profiles = {name:self.validate_topics(yaml.safe_load(path.read_text())['topics'])
                    for name,path in self.profiles.items()}
        return {'topics': self.validate_topics(topics), 'profiles': profiles, 'workspace': str(self.workspace),
                'bag_directory': str(self.output)}

    @staticmethod
    def validate_topics(topics):
        if not isinstance(topics, list) or not topics or len(topics) > 256 or any(
                not isinstance(t, str) or len(t) > 255 or not TOPIC.fullmatch(t) for t in topics):
            raise ValueError('Choose a nonempty list of absolute ROS topic names (maximum 256).')
        return list(dict.fromkeys(topics))

    def ros_command(self, arguments):
        overlay = self.workspace / 'install/setup.bash'
        if not self.underlay.is_file() or not overlay.is_file():
            raise ValueError(f'ROS setup is missing. Build workspace: {self.workspace}')
        # Shell text is fixed; every configurable value is a positional argument.
        return ['bash', '--noprofile', '--norc', '-c',
                'source "$1" && source "$2" && shift 2 && exec "$@"',
                'musohu-ros', str(self.underlay), str(overlay), *arguments]

    def _spawn(self, key, arguments):
        self.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.logs / f'{key}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex[:8]}.log'
        with log_path.open('x') as log:
            process = subprocess.Popen(self.ros_command(arguments), cwd=self.workspace,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        self.processes[key] = process
        return process, log_path

    @staticmethod
    def require_clock_reference():
        from clock_sync import reference_status
        if not reference_status()['ready']:
            raise ValueError('Set time from your phone or wait for internet time before starting the hardware session.')

    def start(self, key, label='session', topics=None):
        with self.lock:
            self.status()
            if self.clock_busy:
                raise ValueError('Wait for time synchronization to finish before starting ROS or recording.')
            if key in self.processes or key in self.stopping:
                raise ValueError('Already active; stop the current operation first.')
            if key == 'helmet_nodes':
                self.require_clock_reference()
                from clock_sync import active_sensor_processes
                if active_sensor_processes():
                    raise ValueError('Another sensor launch or recorder is active. Stop it before starting this hardware launch.')
                process, log = self._spawn(key, ['/usr/bin/python3', str(self.base / 'managed_exec.py'),
                                               'ros2', 'launch', 'helmet_bringup', 'helmet_sensors.launch.py'])
                self.last[key] = {'status': 'running', 'pid': process.pid, 'log_path': str(log)}
                return self.last[key]
            if key != 'record_bag':
                raise KeyError(key)
            if not isinstance(label, str) or not LABEL.fullmatch(label):
                raise ValueError('Session label: 1–80 letters, digits, underscores or hyphens.')
            topics = self.validate_topics(self.defaults()['topics'] if topics is None else topics)
            if not all(t.startswith('/musohu_dummy/') for t in topics):
                self.require_clock_reference()
            # Validate ROS before creating a session directory or claiming startup.
            self.ros_command([])
            self.output.mkdir(parents=True, exist_ok=True)
            session_id = f'{label}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex[:8]}'
            bag = self.output / session_id
            state_path = self.output / f'{session_id}.session.json'
            session = {'session_id': session_id, 'label': label, 'status': 'starting',
                       'bag_path': str(bag), 'topics': topics,
                       'requested_at': datetime.now(timezone.utc).isoformat(),
                       'workspace': str(self.workspace), 'error': None}
            atomic_json(state_path, session)
            self.sessions[key] = state_path
            try:
                process, log = self._spawn(key, ['/usr/bin/python3', str(self.base / 'recording_worker.py'),
                                               '--session', str(state_path)])
                # The worker owns session metadata after spawn; don't overwrite
                # its readiness update from this process.
                self.last[key] = dict(session, pid=process.pid, log_path=str(log))
            except Exception as exc:
                session.update(status='failed', error=str(exc))
                atomic_json(state_path, session)
                self.last[key] = session
                raise
            return self.last[key]

    def _read_session(self, key):
        path = self.sessions.get(key)
        if path:
            try:
                session = json.loads(path.read_text())
                self.last[key].update(session)
            except (OSError, ValueError):
                pass

    def status(self):
        with self.lock:
            for key, process in list(self.processes.items()):
                self._read_session(key)
                code = process.poll()
                if code is None:
                    continue
                # A supervisor that failed unexpectedly must not leave its owned
                # recorder group running after the UI reports failure.
                self.reap_group(process.pid)
                self.last[key]['pid'] = None
                self.last[key]['exit_code'] = code
                if key == 'record_bag' and self.last[key].get('status') not in ('stopped', 'failed'):
                    self.last[key].update(status='failed', error='Recorder exited before confirming finalization.')
                    atomic_json(self.sessions[key], self.last[key])
                elif key != 'record_bag':
                    self.last[key]['status'] = 'stopped' if code == 0 else 'failed'
                del self.processes[key]
            result = {}
            for key, description in [('helmet_nodes', 'Helmet sensors'), ('record_bag', 'Recording session')]:
                entry = dict(self.last.get(key, {'status': 'stopped', 'pid': None}))
                entry['description'] = description
                entry['command'] = ''  # Retained for older clients; no editable shell commands.
                result[key] = entry
            return result

    def stop(self, key):
        with self.lock:
            self.status()
            process = self.processes.get(key)
            if process is None:
                return self.last.get(key, {'status': 'stopped', 'pid': None})
            if key in self.stopping:
                return dict(self.last[key], status='stopping')
            self.stopping.add(key)
            was_starting = self.last[key].get('status') == 'starting'
            self.last[key]['status'] = 'stopping'
            self.signal_group(process.pid, signal.SIGINT)
        # Don't hold the lock while rosbag flushes: UI polls must see stopping.
        forced = False
        try:
            process.wait(timeout=self.stop_timeout)
        except subprocess.TimeoutExpired:
            forced = True
            try:
                self.signal_group(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.signal_group(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        with self.lock:
            self.status()
            self.stopping.discard(key)
            if (key == 'record_bag' and was_starting and
                    process.returncode in (-signal.SIGINT, 130, -signal.SIGTERM, 143) and
                    not Path(self.last[key]['bag_path']).exists()):
                self.last[key].update(status='stopped', finalized=False, error=None,
                                      stopped_at=datetime.now(timezone.utc).isoformat(),
                                      message='Cancelled before recording began.')
                atomic_json(self.sessions[key], self.last[key])
            if forced:
                self.last[key].update(status='failed', error='Forced stop; bag finalization is not confirmed.')
                if key in self.sessions:
                    atomic_json(self.sessions[key], self.last[key])
            return dict(self.last[key])

    def close(self):
        for key in ('record_bag', 'helmet_nodes'):
            self.stop(key)
