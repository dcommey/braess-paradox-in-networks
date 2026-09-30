"""Independent measured service/queue calibration before route-policy testing."""
import json
from pathlib import Path
import random
import subprocess
from mininet.net import Mininet
from mininet.link import TCLink

out = Path('/experiment/processing-evidence')
out.mkdir(exist_ok=True)
schedule = [(rep, rate) for rep in range(3) for rate in [100, 200, 400, 800, 1200]]
random.Random(20260906).shuffle(schedule)
(out / 'protocol.json').write_text(json.dumps({'schedule': schedule, 'seed': 20260906,
    'rounds': 5000, 'queue_packets': 512, 'duration_seconds': 8,
    'drain_seconds': 3, 'arrival_process': 'Poisson', 'payload_bytes': 512,
    'workload': 'single-consumer PBKDF2-SHA256, synthetic processing stage'}, indent=2))
for i, (rep, rate) in enumerate(schedule):
    net = Mininet(controller=None, link=TCLink)
    stage = None
    try:
        a = net.addHost('a', ip='10.78.0.1/24')
        b = net.addHost('b', ip='10.78.0.2/24')
        net.addLink(a, b)
        net.start()
        assert net.pingAll(timeout='2') == 0
        stage = b.popen(['python3', '/experiment/stage.py', '--log', str(out / f'stage-{i:02d}.jsonl')],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert stage.stdout.readline().strip() == 'READY'
        before = Path('/sys/fs/cgroup/cpu.stat').read_text()
        probe = a.popen(['python3', '/experiment/processing_probe.py', '--rate', str(rate),
                        '--seed', str(20260906 + rep), '--output', str(out / f'probe-{i:02d}.jsonl')])
        assert probe.wait(timeout=20) == 0
        (out / f'meta-{i:02d}.json').write_text(json.dumps({'rate': rate, 'repeat': rep,
            'cpu_before': before, 'cpu_after': Path('/sys/fs/cgroup/cpu.stat').read_text()}, indent=2))
    finally:
        if stage is not None:
            stage.terminate()
            _, err = stage.communicate(timeout=3)
            (out / f'stderr-{i:02d}.txt').write_text(err)
        net.stop()
    print(f'Completed processing calibration {i + 1}/{len(schedule)}', flush=True)
(out / 'COMPLETE').write_text('15 independent stage trials completed; audit pending.\n')
