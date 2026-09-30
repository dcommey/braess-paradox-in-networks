"""Exploratory kernel-queue calibration; no VNF or policy claims.

Fixed offered UDP load, separate RTT probes, randomized order, three repeats.
All stdout/stderr, tc counters, and CPU counters retained for audit.
"""
import json
from pathlib import Path
import platform
import random
import subprocess
import time
from mininet.net import Mininet
from mininet.link import TCLink

out = Path('/experiment/evidence')
out.mkdir(exist_ok=True)
schedule = [(repeat, rate) for repeat in range(3) for rate in [1, 5, 8, 9, 10, 12]]
random.Random(20260905).shuffle(schedule)
(out / 'protocol.json').write_text(json.dumps({
    'purpose': 'exploratory kernel queue calibration', 'seed': 20260905,
    'offered_udp_mbps': [1, 5, 8, 9, 10, 12], 'schedule': schedule,
    'duration_seconds': 8, 'payload_bytes': 1000,
    'link_mbps': 10, 'one_way_configured_delay_ms': 5, 'queue_packets': 100,
    'kernel': platform.release(), 'probe': 'ICMP RTT every 50 ms, including startup',
    'limitations': 'UDP offered application rate excludes headers; RTT includes both directions; kernel queue only.'
}, indent=2))
for index, (repeat, rate) in enumerate(schedule):
    net = Mininet(controller=None, link=TCLink)
    children = []
    try:
        a = net.addHost('a', ip='10.77.0.1/24')
        b = net.addHost('b', ip='10.77.0.2/24')
        net.addLink(a, b, bw=10, delay='5ms', max_queue_size=100)
        net.start()
        assert net.pingAll(timeout='2') == 0
        server = b.popen(['iperf3', '-s', '-1', '-J'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        children.append(server)
        time.sleep(0.25)
        cpu_before = Path('/sys/fs/cgroup/cpu.stat').read_text()
        probe = a.popen(['ping', '-D', '-i', '0.05', '-w', '8', '10.77.0.2'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        client = a.popen(['iperf3', '-c', '10.77.0.2', '-u', '-b', f'{rate}M', '-l', '1000', '-t', '8', '-J'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        children += [probe, client]
        client_out, client_err = client.communicate(timeout=20)
        probe_out, probe_err = probe.communicate(timeout=12)
        server_out, server_err = server.communicate(timeout=12)
        row = {'index': index, 'repeat': repeat, 'offered_mbps': rate,
               'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'client': json.loads(client_out), 'server': json.loads(server_out),
               'ping': probe_out.decode(), 'stderr': [x.decode() for x in [client_err, server_err, probe_err]],
               'returncodes': [client.returncode, server.returncode, probe.returncode],
               'tc_a': a.cmd('tc -s qdisc show dev a-eth0'),
               'tc_b': b.cmd('tc -s qdisc show dev b-eth0'),
               'cpu_before': cpu_before, 'cpu_after': Path('/sys/fs/cgroup/cpu.stat').read_text()}
        (out / f'run-{index:02d}.json').write_text(json.dumps(row, indent=2))
        if client.returncode or server.returncode or 'error' in row['client'] or 'error' in row['server']:
            raise RuntimeError(f'Traffic run failed: {index}; evidence retained')
        print(f'Completed {index + 1}/{len(schedule)}', flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        net.stop()
(out / 'COMPLETE').write_text('18 calibration runs finished; scientific analysis pending.\n')
