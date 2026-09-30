"""Shared-stage SFC motif; synthetic work and actual kernel propagation delays."""
import argparse
import json
from pathlib import Path
import subprocess
from mininet.net import Mininet
from mininet.link import TCLink

def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    net = Mininet(controller=None, link=TCLink)
    stages = []
    try:
        router = net.addHost('router', ip=None)
        assert router.cmd('sysctl -w net.ipv4.ip_forward=1').strip().endswith('= 1')
        hosts = {}
        for i, name in enumerate(['source', 'A', 'B', 'C', 'D'], 1):
            host = net.addHost(name, ip=f'10.79.{i}.2/24')
            link = net.addLink(host, router, **({'delay': f'{args.replica_delay_ms:g}ms'} if name in ['C', 'D'] else {}))
            router.setIP(f'10.79.{i}.1/24', intf=link.intf2)
            hosts[name] = host
        net.start()
        for i, host in enumerate(hosts.values(), 1):
            error = host.cmd(f'ip route replace default via 10.79.{i}.1')
            assert not error.strip(), error
        (out / 'routes.txt').write_text('\n'.join(name + '\n' + host.cmd('ip address; ip route; tc qdisc show') for name, host in {**hosts, 'router': router}.items()))
        assert net.ping(list(hosts.values()), timeout='2') == 0
        (out / 'configuration.json').write_text(json.dumps(vars(args), indent=2))
        for name in ['A', 'B', 'C', 'D']:
            service = args.shared_service_ms if name in ['A', 'B'] else args.replica_service_ms
            timed = [] if service is None else ['--service-ms', str(service)]
            proc = hosts[name].popen(['python3', '/experiment/stage.py', '--name', name,
                                    '--log', str(out / f'stage-{name}.jsonl')] + timed,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stages.append((name, proc))
            assert proc.stdout.readline().strip() == 'READY'
        before = Path('/sys/fs/cgroup/cpu.stat').read_text()
        proc = hosts['source'].popen(['python3', '/experiment/route_client.py', '--rate', str(args.rate),
            '--seed', str(args.seed), '--cap', str(args.cap), '--seconds', str(args.seconds),
            '--activate', str(args.activate), '--step-at', str(args.step_at), '--step-factor', str(args.step_factor),
            '--phasing', args.phasing, '--output', str(out / 'packets.jsonl')]
            + ([] if args.fixed_route is None else ['--fixed-route', str(args.fixed_route)])
            + ([] if args.split_step is None else ['--split-step', str(args.split_step)]))
        assert proc.wait(timeout=args.seconds + 15) == 0
        (out / 'cpu.json').write_text(json.dumps({'before': before, 'after': Path('/sys/fs/cgroup/cpu.stat').read_text()}))
    finally:
        for name, proc in stages:
            proc.terminate()
            _, err = proc.communicate(timeout=3)
            (out / f'stderr-{name}.txt').write_text(err)
        net.stop()
    (out / 'COMPLETE').write_text('Run completed; packet and quota audit required.\n')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--rate', type=float, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--cap', type=float, required=True)
    p.add_argument('--seconds', type=float, default=30)
    p.add_argument('--activate', type=float, default=10)
    p.add_argument('--step-at', type=float, default=20)
    p.add_argument('--step-factor', type=float, default=1)
    p.add_argument('--phasing', choices=['staggered', 'synchronized'], default='staggered')
    p.add_argument('--shared-service-ms', type=float, default=None)
    p.add_argument('--replica-service-ms', type=float, default=None)
    p.add_argument('--replica-delay-ms', type=float, default=5)
    p.add_argument('--fixed-route', type=int, default=None)
    p.add_argument('--split-step', type=float, default=None)
    p.add_argument('--output', required=True)
    run(p.parse_args())
