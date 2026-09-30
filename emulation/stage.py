"""Single-server emulated processing stage with real PBKDF2 work per datagram.

Synthetic processing workload; no detection-effectiveness claim. Source-routing
metadata permits explicit ordered stage traversal in the isolated experiment.
"""
import argparse
import asyncio
import hashlib
import json
import time

def process(payload, rounds, service_ns=None):
    wall_start, cpu_start = time.monotonic_ns(), time.thread_time_ns()
    if service_ns is None:
        hashlib.pbkdf2_hmac('sha256', payload, b'braess-stage', rounds)
    else:
        # Timed service: the single consumer is occupied for a fixed interval without CPU work.
        remaining = wall_start + service_ns - time.monotonic_ns()
        if remaining > 0: time.sleep(remaining / 1e9)
    return time.monotonic_ns() - wall_start, time.thread_time_ns() - cpu_start

class Stage(asyncio.DatagramProtocol):
    def __init__(self, name, rounds, log, service_ns=None):
        self.name, self.rounds, self.log, self.service_ns = name, rounds, log, service_ns
        self.queue = asyncio.Queue(maxsize=512)

    def connection_made(self, transport):
        self.transport = transport
        asyncio.create_task(self.worker())

    def datagram_received(self, data, address):
        arrived = time.monotonic_ns()
        try:
            packet = json.loads(data)
            self.queue.put_nowait((packet, arrived))
        except asyncio.QueueFull:
            self.log.write(json.dumps({'event': 'drop', 'id': packet['id'], 'ns': arrived}) + '\n')

    async def worker(self):
        loop = asyncio.get_running_loop()
        while True:
            packet, arrived = await self.queue.get()
            start = time.monotonic_ns()
            # One consumer awaits each real computation before serving the next packet.
            compute_wall_ns, compute_cpu_ns = await loop.run_in_executor(
                None, process, packet['payload'].encode(), self.rounds, self.service_ns)
            end = time.monotonic_ns()
            packet['trace'].append([self.name, arrived, start, end])
            next_hop = packet['remaining'].pop(0) if packet['remaining'] else packet['return_to']
            self.transport.sendto(json.dumps(packet).encode(), tuple(next_hop))
            self.log.write(json.dumps({'event': 'service', 'id': packet['id'],
                                      'arrived_ns': arrived, 'start_ns': start, 'end_ns': end,
                                      'compute_wall_ns': compute_wall_ns, 'compute_cpu_ns': compute_cpu_ns,
                                      'queue_depth': self.queue.qsize()}) + '\n')

async def main(args):
    with open(args.log, 'w', buffering=1) as log:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: Stage(args.name, args.rounds, log,
                                                          None if args.service_ms is None else round(args.service_ms * 1e6)),
                                            local_addr=('0.0.0.0', 9000))
        print('READY', flush=True)
        await asyncio.Future()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--name', default='stage')
    p.add_argument('--rounds', type=int, default=5000)
    p.add_argument('--service-ms', type=float, default=None, help='fixed timed service; default is PBKDF2 work')
    p.add_argument('--log', required=True)
    asyncio.run(main(p.parse_args()))
