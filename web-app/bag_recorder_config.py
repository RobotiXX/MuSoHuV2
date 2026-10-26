"""Read and validate the native recorder client's per-session settings."""
import hashlib
import os
from pathlib import Path
import re

import yaml


DEFAULTS = {
    'storage': 'mcap',
    'serialization_format': '',
    'max_cache_size': 100 * 1024 * 1024,
    'compression_mode': 'none',
    'compression_format': 'zstd',
    'compression_queue_size': 1,
    'compression_threads': 0,
}
IDENTIFIER = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$')


def load_recorder_config(path=None):
    if path is None:
        path = os.environ.get('MUSOHU_BAG_RECORDER_CONFIG',
                              str(Path(__file__).with_suffix('.yml')))
    path = Path(path).expanduser().resolve()
    try:
        contents = path.read_bytes()
        raw = yaml.safe_load(contents)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f'Cannot read bag recorder config {path}: {exc}') from exc
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise ValueError(f'Bag recorder config {path} must be a mapping of settings.')
    unknown = raw.keys() - DEFAULTS.keys()
    if unknown:
        raise ValueError('Unknown bag recorder setting(s): ' + ', '.join(sorted(unknown)))
    settings = dict(DEFAULTS, **raw)
    for key in ('storage', 'serialization_format', 'compression_format'):
        value = settings[key]
        if (not isinstance(value, str) or
                not (IDENTIFIER.fullmatch(value) or value == '' and key != 'storage')):
            raise ValueError(f'Bag recorder {key} must be a plugin/format name'
                             + (' or an empty string.' if key != 'storage' else '.'))
    for key, maximum in [('max_cache_size', 2**64 - 1),
                         ('compression_queue_size', 2**64 - 1),
                         ('compression_threads', 2**64 - 1)]:
        value = settings[key]
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f'Bag recorder {key} must be a nonnegative integer (max {maximum}).')
    if settings['compression_mode'] not in ('none', 'file', 'message'):
        raise ValueError('Bag recorder compression_mode must be none, file, or message.')
    if settings['compression_mode'] != 'none' and not settings['compression_format']:
        raise ValueError('Bag recorder compression_format is required when compression is enabled.')
    if settings['storage'] == 'mcap' and settings['compression_mode'] == 'message':
        raise ValueError('MCAP does not support rosbag2 message compression; use its storage configuration.')
    return {'path': str(path), 'sha256': hashlib.sha256(contents).hexdigest(),
            'settings': settings}


def validate_ros_plugins(settings):
    """Check the selected plugins inside the sourced ROS worker environment."""
    import rosbag2_py
    writers = rosbag2_py.get_registered_writers()
    if settings['storage'] not in writers:
        raise ValueError(f"Bag recorder storage plugin {settings['storage']!r} is not installed. "
                         f"Installed writers: {', '.join(sorted(writers))}")
    serialization = settings['serialization_format']
    if serialization:
        formats = {name.removesuffix('_converter')
                   for name in rosbag2_py.get_registered_serializers()
                   if name.endswith('_converter')}
        if serialization not in formats:
            raise ValueError(f'Bag recorder serialization converter {serialization!r} is not installed. '
                             'Use serialization_format: "" for the native middleware format.')
    if settings['compression_mode'] != 'none':
        compressors = rosbag2_py.get_registered_compressors()
        if settings['compression_format'] not in compressors:
            raise ValueError(f"Bag recorder compressor {settings['compression_format']!r} is not installed. "
                             f"Installed compressors: {', '.join(sorted(compressors))}")

