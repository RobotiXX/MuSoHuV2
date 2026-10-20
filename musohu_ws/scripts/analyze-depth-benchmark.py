#!/usr/bin/env python3
"""Audit benchmark bags for tracking, depth validity and stereo pairing.

Requires only Humble + musohu_ws overlay (numpy for depth samples). This does
not establish geometric depth accuracy or trajectory drift.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3

import numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; preserve evidence and choose a new file.')
    report=json.loads(args.report.read_text());results={}
    for mode,entry in report['modes'].items():
        if entry['status']!='complete':continue
        counts=Counter();confidence=[];diagnostics={};fractions=[];backward=Counter();previous={}
        stereo = {}
        bag=Path(entry['session']['bag_path'])
        for database in bag.glob('*.db3'):
            with sqlite3.connect(f'file:{database}?mode=ro',uri=True) as db:
                topics={name:(tid,typ) for tid,name,typ in db.execute('SELECT id,name,type FROM topics')}
                for topic in ['/zed2i/zed_node/pose/status','/diagnostics','/zed2i/zed_node/odom','/audio_stamped','/rslidar_points']:
                    if topic not in topics:continue
                    tid,typ=topics[topic];cls=get_message(typ)
                    for (data,) in db.execute('SELECT data FROM messages WHERE topic_id=? ORDER BY timestamp,id',(tid,)):
                        msg=deserialize_message(data,cls)
                        if hasattr(msg,'header'):
                            stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
                            if topic in previous and stamp<previous[topic]:backward[topic]+=1
                            previous[topic]=stamp
                        if topic.endswith('/pose/status'):
                            counts[msg.odometry_status]+=1;confidence.append(msg.pose_confidence)
                        if topic=='/diagnostics':
                            for status in msg.status:
                                level=status.level[0] if isinstance(status.level,bytes) else int(status.level)
                                rec=diagnostics.setdefault(status.name,{'levels':Counter(),'last_message':'','last_values':{}})
                                rec['levels'][level]+=1;rec['last_message']=status.message
                                rec['last_values']={v.key:v.value for v in status.values}
                topic='/zed2i/zed_node/depth/depth_registered'
                if topic in topics:
                    tid,typ=topics[topic];cls=get_message(typ)
                    total=db.execute('SELECT COUNT(*) FROM messages WHERE topic_id=?',(tid,)).fetchone()[0]
                    for index in np.linspace(0,max(0,total-1),min(10,total),dtype=int):
                        data=db.execute('SELECT data FROM messages WHERE topic_id=? ORDER BY timestamp,id LIMIT 1 OFFSET ?',(tid,int(index))).fetchone()[0]
                        msg=deserialize_message(data,cls)
                        if msg.encoding=='32FC1':
                            values=np.ndarray((msg.height,msg.width),dtype='>f4' if msg.is_bigendian else '<f4',buffer=msg.data,strides=(msg.step,4))
                            fractions.append(float(np.isfinite(values).mean()))
                for side in ('left', 'right'):
                    root=f'/zed2i/zed_node/{side}/color/rect/'
                    for suffix in ('image', 'camera_info'):
                        topic=root+suffix
                        if topic not in topics:continue
                        tid,typ=topics[topic];cls=get_message(typ)
                        rec=stereo.setdefault(side+'_'+suffix,{'stamps':[], 'backward_stamps':0,
                                                             'duplicate_stamps':0,'formats':Counter()})
                        for (data,) in db.execute('SELECT data FROM messages WHERE topic_id=? ORDER BY timestamp,id',(tid,)):
                            msg=deserialize_message(data,cls)
                            stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
                            if rec['stamps']:
                                rec['backward_stamps']+=int(stamp<rec['stamps'][-1])
                                rec['duplicate_stamps']+=int(stamp==rec['stamps'][-1])
                            rec['stamps'].append(stamp)
                            if suffix=='image':
                                rec['formats'][f'{msg.width}x{msg.height} {msg.encoding} step={msg.step} bytes={len(msg.data)}']+=1
                            else:
                                rec['last_calibration']={'width':msg.width,'height':msg.height,
                                    'distortion_model':msg.distortion_model,'k':list(msg.k),
                                    'd':list(msg.d),'r':list(msg.r),'p':list(msg.p)}
        pairing={}
        if 'left_image' in stereo and 'right_image' in stereo:
            left=Counter(stereo['left_image']['stamps']);right=Counter(stereo['right_image']['stamps'])
            pairing={'exact_stamp_pairs':sum((left & right).values()),
                     'left_unpaired':sum((left-right).values()),'right_unpaired':sum((right-left).values())}
        for side in ('left','right'):
            image=stereo.get(side+'_image');info=stereo.get(side+'_camera_info')
            if image and info:
                pairing[side+'_image_without_info_stamp']=sum((Counter(image['stamps'])-Counter(info['stamps'])).values())
        for rec in stereo.values():
            rec['messages']=len(rec.pop('stamps'));rec['formats']=dict(rec['formats'])
        results[mode]={'odometry_status_counts':dict(counts),
            'pose_confidence_min':min(confidence) if confidence else None,
            'pose_confidence_mean':float(np.mean(confidence)) if confidence else None,
            'backward_header_stamps':dict(backward),'diagnostics':diagnostics,
            'depth_finite_fraction_samples':fractions,
            'depth_finite_fraction_mean':float(np.mean(fractions)) if fractions else None,
            'stereo_streams':stereo,'stereo_pairing':pairing,
            'bag_bytes':sum(p.stat().st_size for p in bag.glob('*.db3')),
            'limits':'Finite depth fraction is scene-dependent completeness, not calibrated accuracy.'}
    args.output.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({m:{k:v for k,v in r.items() if k not in ['diagnostics','depth_finite_fraction_samples']} for m,r in results.items()},indent=2))


if __name__=='__main__':main()
