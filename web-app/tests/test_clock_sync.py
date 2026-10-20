"""Clock-reference and workflow checks without changing host time or networking."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import clock_sync
from clock_sync import ClockSync
from clock_reference import reference_status
from process_manager import ProcessManager


class ClockReferenceTest(unittest.TestCase):
    def test_offline_phone_reference_boot_and_step_checks(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'clock.json'
            state={'source':'phone','boot_id':'current','epoch_s':1800000000,'monotonic_s':10}
            path.write_text(json.dumps(state))
            options={'path':path,'ntp':{'NTP':'no','NTPSynchronized':'no'},
                     'now':1800000010,'monotonic':20,'boot':'current'}
            self.assertEqual(reference_status(**options)['source'],'phone')
            self.assertFalse(reference_status(**dict(options,boot='next-boot'))['ready'])
            self.assertFalse(reference_status(**dict(options,now=1800000020))['ready'])
            self.assertFalse(reference_status(**dict(options,monotonic=86420))['ready'])

    def test_ntp_flag_alone_does_not_make_an_offline_clock_ready(self):
        self.assertFalse(reference_status(ntp={'NTP':'no','NTPSynchronized':'yes'},
                         now=1800000000,path='/not-present')['ready'])
        self.assertFalse(reference_status(ntp={'NTP':'yes','NTPSynchronized':'yes'},now=100)['ready'])
        self.assertEqual(reference_status(ntp={'NTP':'yes','NTPSynchronized':'yes'},now=1800000000)['source'],'ntp')


class ClockWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.manager=SimpleNamespace(lock=threading.RLock(),status=lambda:None,
            processes={},stopping=set(),clock_busy=False,workspace=Path('/test/workspace'))
        self.clock=ClockSync(self.manager)

    def test_rejects_bad_phone_time_and_active_sensors_before_privilege(self):
        with patch.object(self.clock,'run') as run:
            for epoch in [None,True,0,float('nan'),'2026-10-15']:
                with self.assertRaises(ValueError):self.clock.change(epoch_ms=epoch)
            with patch('clock_sync.active_sensor_processes',return_value=['42']):
                with self.assertRaisesRegex(ValueError,'Stop recording'):
                    self.clock.change(epoch_ms=time.time()*1000)
            self.manager.processes={'record_bag':object()}
            with self.assertRaises(ValueError):self.clock.change(epoch_ms=time.time()*1000)
            run.assert_not_called()

    def test_phone_success_disables_ntp_checks_lidar_and_saves_reference(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'clock.json'
            def output(argv):return 'no' if argv[0]=='timedatectl' else 'active'
            with patch('clock_sync.active_sensor_processes',return_value=[]), \
                 patch('clock_sync.reference_status',return_value={'ntp_enabled':False}), \
                 patch('clock_sync.output',side_effect=output), \
                 patch('clock_sync.state_path',return_value=state), \
                 patch.object(self.clock,'run') as run, \
                 patch('clock_sync.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='Locked; epoch valid')):
                result=self.clock.change(epoch_ms=time.time()*1000)
                self.assertTrue(result['last_result']['lidar_ready'])
                self.assertEqual(run.call_args_list[0].args[0],['/usr/bin/timedatectl','set-ntp','false'])
                self.assertEqual(run.call_args_list[1].args[0][:3],['/usr/bin/date','-u','-s'])
                self.assertEqual(json.loads(state.read_text())['source'],'phone')
                self.assertFalse(self.manager.clock_busy)

    def test_failed_date_restores_prior_ntp_and_releases_start_guard(self):
        with patch('clock_sync.active_sensor_processes',return_value=[]), \
             patch('clock_sync.reference_status',return_value={'ntp_enabled':True}), \
             patch('clock_sync.output',return_value='no'), \
             patch.object(self.clock,'run',side_effect=[None,RuntimeError('permission'),None]) as run:
            with self.assertRaisesRegex(RuntimeError,'permission'):
                self.clock.change(epoch_ms=time.time()*1000)
            self.assertEqual(run.call_args_list[-1].args[0],['/usr/bin/timedatectl','set-ntp','true'])
            self.assertFalse(self.manager.clock_busy)

    def test_unknown_reference_blocks_hardware_but_not_dummy_development(self):
        with patch('clock_sync.reference_status',return_value={'ready':False}):
            with self.assertRaisesRegex(ValueError,'Set time'):
                ProcessManager.require_clock_reference()
        manager=ProcessManager(Path(__file__).resolve().parents[1],{})
        manager.clock_busy=True
        with self.assertRaisesRegex(ValueError,'synchronization'):
            manager.start('helmet_nodes')

    def test_external_sensor_owner_blocks_duplicate_hardware_launch(self):
        manager=ProcessManager(Path(__file__).resolve().parents[1],{})
        with patch.object(manager,'require_clock_reference'), \
             patch('clock_sync.active_sensor_processes',return_value=['42']), \
             patch.object(manager,'_spawn') as spawn:
            with self.assertRaisesRegex(ValueError,'Another sensor launch'):
                manager.start('helmet_nodes')
            spawn.assert_not_called()


if __name__=='__main__':unittest.main()
