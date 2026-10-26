"""Check copied CDR bytes, timestamps and durable/multiple offered QoS profiles."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import rosbag2_py
from rclpy.serialization import serialize_message
from sensor_msgs.msg import Imu
import yaml

spec = importlib.util.spec_from_file_location(
    'dds_converter', Path(__file__).resolve().parents[1] / 'convert-bag-for-dds.py')
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class DdsBagConversionTest(unittest.TestCase):
    def test_copy_preserves_messages_and_all_qos_except_namespace_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source', Path(directory) / 'dds'
            writer = rosbag2_py.SequentialWriter()
            writer.open(rosbag2_py.StorageOptions(uri=str(source), storage_id='mcap'),
                        rosbag2_py.ConverterOptions('', ''))
            profiles = [dict(history=1, depth=10, reliability=1, durability=1,
                             avoid_ros_namespace_conventions=True),
                        dict(history=1, depth=7, reliability=2, durability=2,
                             avoid_ros_namespace_conventions=True)]
            writer.create_topic(rosbag2_py.TopicMetadata(
                name='/imu', type='sensor_msgs/msg/Imu', serialization_format='cdr',
                offered_qos_profiles=yaml.safe_dump(profiles)))
            msg = Imu()
            msg.header.frame_id = 'imu'
            msg.angular_velocity.x = 2.5
            payload = serialize_message(msg)
            start = 1700000000000000000
            for offset in (0, 5000000, 5000000):
                writer.write('/imu', payload, start + offset)
            del writer
            original = {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
            report = converter.convert(source, output)
            self.assertTrue(report['verified'])
            self.assertEqual(report['message_counts'], {'/imu': 3})
            self.assertEqual(original, {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()})
            reader = converter.reader_for(output)
            copied = yaml.safe_load(reader.get_all_topics_and_types()[0].offered_qos_profiles)
            for profile in profiles:
                profile['avoid_ros_namespace_conventions'] = False
            self.assertEqual(copied, profiles)
            for offset in (0, 5000000, 5000000):
                self.assertEqual(reader.read_next(), ('/imu', payload, start + offset))
            del reader
            with self.assertRaises(ValueError):
                converter.convert(source, output)
            with self.assertRaises(ValueError):
                converter.convert(source, source / 'nested')

    def test_empty_and_invalid_qos(self):
        self.assertEqual(converter.dds_qos(''), '')
        with self.assertRaises(ValueError):
            converter.dds_qos('history: 1')


if __name__ == '__main__':
    unittest.main()
