#!/usr/bin/env python3
"""Copy a finalized ROS bag to MCAP with DDS-compatible topic-name QoS.

Source /opt/ros/humble/setup.bash and musohu_ws/install/setup.bash, then run:
  python3 musohu_ws/scripts/convert-bag-for-dds.py SOURCE_BAG NEW_BAG

Zenoh and DDS use the same ROS CDR payloads. Only recorded offered QoS
avoid_ros_namespace_conventions flags change. Message bytes, receipt times,
topic types and other QoS settings are preserved and verified. Output chunks
are uncompressed; the source and any existing destination are never replaced.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

import rosbag2_py
import yaml


def metadata(path):
    return yaml.safe_load((path / 'metadata.yaml').read_text())['rosbag2_bagfile_information']


def reader_for(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id=metadata(path)['storage_identifier']),
                rosbag2_py.ConverterOptions('', ''))
    return reader


def dds_qos(text):
    profiles = yaml.safe_load(text) if text else []
    if profiles is None:
        profiles = []
    if not isinstance(profiles, list) or any(not isinstance(p, dict) for p in profiles):
        raise ValueError('Recorded offered QoS must be a list of profiles')
    for profile in profiles:
        profile['avoid_ros_namespace_conventions'] = False
    return yaml.safe_dump(profiles, sort_keys=False) if profiles else ''


def update(digest, stamp, data):
    digest.update(struct.pack('<qQ', stamp, len(data)))
    digest.update(data)


def convert(source, output):
    source, output = Path(source).expanduser().resolve(), Path(output).expanduser()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new destination outside the source bag')
    output = output.resolve()
    if source == output or source in output.parents:
        raise ValueError('Choose a new destination outside the source bag')
    before = metadata(source)
    reader = reader_for(source)
    topics = reader.get_all_topics_and_types()
    if any(t.serialization_format != 'cdr' for t in topics):
        raise ValueError('Only native CDR bags are supported')
    expected_topics = {t.name: (t.type, t.serialization_format, dds_qos(t.offered_qos_profiles))
                       for t in topics}
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(output), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    counts, digests = Counter(), defaultdict(hashlib.sha256)
    try:
        for name, (kind, serialization, qos) in expected_topics.items():
            writer.create_topic(rosbag2_py.TopicMetadata(name=name, type=kind,
                                                        serialization_format=serialization,
                                                        offered_qos_profiles=qos))
        while reader.has_next():
            name, data, stamp = reader.read_next()
            writer.write(name, data, stamp)
            counts[name] += 1
            update(digests[name], stamp, data)
            if sum(counts.values()) % 20000 == 0:
                print(f'Copied {sum(counts.values())} messages', flush=True)
    finally:
        del writer
        del reader
    expected_counts = {t['topic_metadata']['name']: t['message_count']
                       for t in before['topics_with_message_count'] if t['message_count']}
    if dict(counts) != expected_counts:
        raise RuntimeError('Source counts changed or differ from finalized metadata')
    print('Verifying the saved copy...', flush=True)
    saved_counts, saved_digests = Counter(), defaultdict(hashlib.sha256)
    saved = reader_for(output)
    actual_topics = {t.name: (t.type, t.serialization_format, t.offered_qos_profiles)
                     for t in saved.get_all_topics_and_types()}
    while saved.has_next():
        name, data, stamp = saved.read_next()
        saved_counts[name] += 1
        update(saved_digests[name], stamp, data)
    del saved
    after = metadata(output)
    if (actual_topics != expected_topics or saved_counts != counts or
            any(saved_digests[name].digest() != digest.digest() for name, digest in digests.items()) or
            any(before[field] != after[field] for field in ('starting_time', 'duration', 'message_count'))):
        raise RuntimeError('Saved copy failed message/timestamp/type/QoS verification')
    report = dict(source=str(source), output=str(output), verified=True,
                  transformation='offered QoS avoid_ros_namespace_conventions=false',
                  storage='mcap', chunk_compression='none', message_counts=dict(counts),
                  records_sha256={name: digest.hexdigest() for name, digest in digests.items()})
    (output / 'dds_conversion.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Verified {sum(counts.values())} messages in {output}', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        convert(args.source, args.output)
    except (Exception, KeyboardInterrupt) as error:
        parser.exit(1, f'Conversion failed: {error}\n'
                       'The source is unchanged. Any incomplete output is kept for inspection.\n')


if __name__ == '__main__':
    main()
