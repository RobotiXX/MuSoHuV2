#!/usr/bin/env python3
"""Measure module power with the full rig recording; never changes power mode.

Run as a normal user. VDD_IN excludes external sensors/carrier/battery losses.
Each mode gets an independent launch, warmup and finalized full-topic bag.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'web-app'))
from process_manager import ProcessManager


def summary(values):
    values = sorted(values)
    if not values:
        return None
    return {'mean': statistics.mean(values), 'median': statistics.median(values),
            'p95': values[int(.95 * (len(values)-1))], 'max': max(values), 'min': min(values)}


def sample(hwmon):
    rails = {}
    for label in hwmon.glob('in*_label'):
        n = label.stem[2:-6]
        if not (hwmon / f'curr{n}_input').exists():
            continue
        rails[label.read_text().strip()] = float((hwmon / f'in{n}_input').read_text()) * float((hwmon / f'curr{n}_input').read_text()) / 1e6
    temps = {}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            temps[(zone / 'type').read_text().strip()] = float((zone / 'temp').read_text()) / 1000
        except (OSError, TypeError, ValueError):
            pass
    memory = {line.split(':',1)[0]:int(line.split()[1])/1024
              for line in Path('/proc/meminfo').read_text().splitlines()
              if line.startswith(('MemAvailable:','SwapFree:','SwapTotal:'))}
    return {'monotonic_s': time.monotonic(), 'utc_s': time.time(), 'power_w': rails,
            'temperature_c': temps, 'memory_mib': memory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory, never overwritten')
    parser.add_argument('--modes', nargs='+', choices=['NONE','NEURAL_LIGHT','NEURAL','NEURAL_PLUS'], default=['NEURAL_LIGHT','NEURAL','NEURAL_PLUS'])
    parser.add_argument('--params-file', type=Path, help='Base ZED overrides (default: project depth profile)')
    parser.add_argument('--topics', type=Path, help='Topic manifest (default: full RGB/depth recording)')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--warmup', type=int, default=30)
    parser.add_argument('--startup-timeout', type=int, default=900, help='Includes first-use SDK model optimization')
    parser.add_argument('--domain', type=int, default=95)
    args = parser.parse_args()
    if 'NONE' in args.modes and (args.params_file is None or args.topics is None):
        parser.error('NONE requires --params-file and --topics for a depthless capture/recording profile')
    if args.output.exists() or not 10 <= args.seconds <= 600 or not 0 <= args.warmup <= 300:
        parser.error('Use a new directory, recording 10..600s, warmup 0..300s')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True)
    os.environ['ROS_DOMAIN_ID'] = str(args.domain)
    os.environ['MUSOHU_BAG_DIR'] = str(args.output / 'bags')
    manager = ProcessManager(REPO / 'web-app', {'ros':{'process_log_directory':str(args.output / 'logs')}})
    hwmon = next(p for p in Path('/sys/bus/i2c/drivers/ina3221').glob('*/hwmon/hwmon*') if (p/'in1_label').read_text().strip() == 'VDD_IN')
    report = {'measurement_scope':'Jetson total module power (INA3221 VDD_IN); external sensors/carrier and battery losses unmeasured',
              'nvpmodel':subprocess.check_output(['nvpmodel','-q'],text=True).strip(), 'domain':args.domain,
              'record_seconds':args.seconds,'warmup_seconds':args.warmup,'modes':{},
              'sources':subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True)}
    wrapper = REPO/'musohu_ws/src/zed-ros2-wrapper'
    report['zed_wrapper_worktree_diff'] = subprocess.check_output(['git','diff','HEAD','--'],cwd=wrapper,text=True)
    config_dir = REPO/'musohu_ws/src/helmet_bringup/config'
    params_file = (args.params_file or config_dir/'zed_depth_benchmark.yaml').resolve()
    topic_file = (args.topics or config_dir/'recording_rgb_depth.yaml').resolve()
    topics = manager.validate_topics(yaml.safe_load(topic_file.read_text())['topics'])
    report.update(params_file=str(params_file),topic_manifest=str(topic_file),topics=topics)
    launch = None
    entry = None
    def save():
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        baseline = []
        for _ in range(15):
            baseline.append(sample(hwmon));time.sleep(1)
        (args.output/'idle-samples.json').write_text(json.dumps(baseline,indent=2))
        report['idle_vdd_in_w'] = summary([s['power_w']['VDD_IN'] for s in baseline]);save()
        for mode in args.modes:
            print(f'Starting {mode}',flush=True)
            profile = yaml.safe_load(params_file.read_text())
            profile['/**']['ros__parameters']['depth']['depth_mode'] = mode
            config = args.output/f'{mode}.yaml';config.write_text(yaml.safe_dump(profile,sort_keys=False))
            samples=[];entry={'status':'starting','config':str(config)};report['modes'][mode]=entry;save()
            with (args.output/f'{mode}-launch.log').open('x') as log:
                launch=subprocess.Popen(manager.ros_command(['ros2','launch','helmet_bringup','helmet_sensors.launch.py',f'zed_params_file:={config}']),cwd=manager.workspace,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                # Discover all publishers, including image outputs, before warmup.
                preflight_code='''import rclpy,time,sys,json
rclpy.init();n=rclpy.create_node('benchmark_wait');end=time.monotonic()+float(sys.argv[1]);topics=json.loads(sys.argv[2])
while time.monotonic()<end:
 rclpy.spin_once(n,timeout_sec=.2)
 if all(n.get_publishers_info_by_topic(t) for t in topics):break
else:raise SystemExit(2)
n.destroy_node();rclpy.shutdown()
'''
                preflight=subprocess.run(manager.ros_command(['/usr/bin/python3','-c',preflight_code,str(args.startup_timeout),json.dumps(topics)]),timeout=args.startup_timeout+15,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
                if preflight.returncode:
                    raise RuntimeError(f'{mode}: missing publishers/model startup failed; see launch log. {preflight.stderr[-500:]}')
                print(f'{mode}: publishers ready; warming up {args.warmup}s',flush=True)
                time.sleep(args.warmup)
                manager.start('record_bag',label=mode,topics=topics)
                deadline=time.monotonic()+35
                while time.monotonic()<deadline:
                    state=manager.status()['record_bag']
                    if state['status']=='recording':break
                    if state['status']=='failed':raise RuntimeError(state)
                    time.sleep(.2)
                else:raise RuntimeError('Recording did not start')
                entry['status']='recording';save();print(f'{mode}: recording {args.seconds}s',flush=True)
                start=time.monotonic()
                while time.monotonic()-start<args.seconds:
                    if launch.poll() is not None:raise RuntimeError('Sensor launch exited')
                    samples.append(sample(hwmon));time.sleep(1)
                final=manager.stop('record_bag')
                if not final.get('finalized'):raise RuntimeError(final)
                if final.get('topics_without_messages'):
                    raise RuntimeError('Selected topics had no recorded messages: '+str(final['topics_without_messages']))
                entry.update(status='complete',session=final,
                             vdd_in_w=summary([s['power_w']['VDD_IN'] for s in samples]),
                             temperature_c={k:summary([s['temperature_c'][k] for s in samples if k in s['temperature_c']]) for k in samples[-1]['temperature_c']},
                             message_rate_hz={t:c/(final['duration_ns']/1e9) for t,c in final['topic_counts'].items()})
                (args.output/f'{mode}-samples.json').write_text(json.dumps(samples,indent=2));save()
                os.killpg(launch.pid,signal.SIGINT);launch.wait(timeout=35);entry['launch_exit']=launch.returncode;launch=None;save()
                print(json.dumps({'mode':mode,'power_w':entry['vdd_in_w'],'rates':entry['message_rate_hz']}),flush=True)
                time.sleep(5)
    except Exception as exc:
        if entry is not None:
            entry.update(status='failed',error=str(exc))
        report['error']=str(exc);save();raise
    finally:
        manager.close()
        if launch and launch.poll() is None:
            os.killpg(launch.pid,signal.SIGINT)
            try:launch.wait(timeout=35)
            except subprocess.TimeoutExpired:
                os.killpg(launch.pid,signal.SIGTERM);launch.wait(timeout=10)
        save()


if __name__=='__main__':
    main()
