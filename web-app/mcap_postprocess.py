"""Losslessly compress finalized MCAPs, verifying every record before replacement.

Run in the system-Python ROS worker, never in the FastAPI event loop. No shell
commands or user-supplied CLI arguments are evaluated. The original remains at
its recorded path until a verified copy is fsynced and atomically replaces it.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time
from uuid import uuid4

import yaml

from process_manager import atomic_json


def validate_config(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError('ros.mcap_postprocess must be a mapping')
    unknown = set(value) - {'enabled', 'executable', 'timeout_seconds'}
    if unknown:
        raise ValueError('Unknown mcap_postprocess options: ' + ', '.join(sorted(unknown)))
    enabled = value.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('mcap_postprocess.enabled must be true or false')
    executable = value.get('executable', '/usr/local/bin/mcap')
    timeout = value.get('timeout_seconds', 1800)
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        raise ValueError('mcap_postprocess.executable must be an absolute path')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 86400:
        raise ValueError('mcap_postprocess.timeout_seconds must be between 1 and 86400')
    if enabled and not os.access(executable, os.X_OK):
        raise ValueError('MCAP CLI is missing; run musohu_ws/scripts/mcap-cli.sh --install')
    return dict(enabled=enabled, executable=executable, timeout_seconds=float(timeout))


def fingerprint(path, deadline):
    """Hash all stored topics, timestamps and unchanged serialized payload bytes."""
    import rosbag2_py
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    topics = sorted((t.name, t.type, t.serialization_format, t.offered_qos_profiles)
                    for t in reader.get_all_topics_and_types())
    digest = hashlib.sha256()
    counts = {}
    while reader.has_next():
        if time.monotonic() >= deadline:
            raise TimeoutError('MCAP verification timed out; original retained')
        topic, data, stamp = reader.read_next()
        name = topic.encode()
        digest.update(struct.pack('<IQ', len(name), len(data)))
        digest.update(name)
        digest.update(struct.pack('<q', stamp))
        digest.update(data)
        counts[topic] = counts.get(topic, 0) + 1
    del reader
    return dict(sha256=digest.hexdigest(), counts=counts, topics=topics)


def compress_bag(bag, config, progress=lambda **kwargs: None):
    config = validate_config(config)
    bag = Path(bag).resolve()
    metadata = yaml.safe_load((bag/'metadata.yaml').read_text())['rosbag2_bagfile_information']
    if not config['enabled']:
        return dict(status='disabled')
    if (metadata['storage_identifier'] != 'mcap' or
            (metadata.get('compression_mode') or '').lower() not in ('', 'none')):
        return dict(status='skipped', reason='Requires MCAP with no rosbag file/message compression')
    started = time.monotonic()
    deadline = started + config['timeout_seconds']
    executable = config['executable']
    version = subprocess.check_output([executable, '--version'], text=True, timeout=5).strip()
    report = dict(status='compressing', compression='zstd', cli_version=version, files=[])
    expected = {entry['topic_metadata']['name']: entry['message_count']
                for entry in metadata['topics_with_message_count'] if entry['message_count']}
    observed = {}
    # Refuse paths outside this bag, including unexpected symlinks.
    paths = []
    for relative in metadata['relative_file_paths']:
        path = bag/relative
        if path.is_symlink() or path.resolve().parent != bag or path.suffix != '.mcap':
            raise ValueError('Unsafe MCAP path in bag metadata: ' + str(relative))
        paths.append(path)
    for index, original in enumerate(paths, 1):
        temporary = original.with_name('.'+original.stem+'.zstd-'+uuid4().hex+'.mcap')
        source_bytes = original.stat().st_size
        if shutil.disk_usage(bag).free < source_bytes + 16*1024*1024:
            raise OSError('Insufficient temporary space for verified MCAP compression; original retained')
        def remaining():
            return max(.001, deadline-time.monotonic())
        try:
            progress(phase='compressing', file=original.name, file_index=index, file_count=len(paths))
            begin = time.monotonic()
            subprocess.run([executable, 'compress', str(original), '--compression', 'zstd',
                            '--order', 'preserve', '--output', str(temporary)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=remaining())
            compression_seconds = time.monotonic()-begin
            progress(phase='verifying', file=original.name, file_index=index, file_count=len(paths))
            begin = time.monotonic()
            subprocess.run([executable, 'doctor', str(temporary)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=remaining())
            source = fingerprint(original, deadline)
            target = fingerprint(temporary, deadline)
            if source != target:
                raise ValueError('Compressed MCAP records differ; original retained')
            for topic, count in source['counts'].items():
                observed[topic] = observed.get(topic, 0)+count
            # A single-file bag can also be checked against rosbag metadata
            # before replacing anything. Multi-file totals are checked below.
            if len(paths) == 1 and source['counts'] != expected:
                raise ValueError('MCAP counts differ from rosbag metadata; original retained')
            compressed_bytes = temporary.stat().st_size
            verification_seconds = time.monotonic()-begin
            with temporary.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, original)
            directory = os.open(str(bag), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            report['files'].append(dict(path=original.name, original_bytes=source_bytes,
                compressed_bytes=compressed_bytes, compression_seconds=compression_seconds,
                verification_seconds=verification_seconds, records_sha256=source['sha256'],
                message_counts=source['counts'], verified=True))
            atomic_json(bag/'mcap_postprocess.json', report)
        finally:
            temporary.unlink(missing_ok=True)
    if observed != expected:
        raise ValueError('MCAP file totals differ from rosbag metadata; individually verified files remain usable')
    report.update(status='completed', elapsed_seconds=time.monotonic()-started,
        original_bytes=sum(f['original_bytes'] for f in report['files']),
        compressed_bytes=sum(f['compressed_bytes'] for f in report['files']))
    report['saved_bytes'] = report['original_bytes']-report['compressed_bytes']
    atomic_json(bag/'mcap_postprocess.json', report)
    return report
