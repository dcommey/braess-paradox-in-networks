"""Open-loop Poisson UDP requests; retain scheduled and actual send timestamps."""
import argparse
import json
import random
import selectors
import socket
import time

p = argparse.ArgumentParser()
p.add_argument('--rate', type=float, required=True)
p.add_argument('--seed', type=int, required=True)
p.add_argument('--seconds', type=float, default=8)
p.add_argument('--output', required=True)
args = p.parse_args()
rng = random.Random(args.seed)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('10.78.0.1', 9001))
s.setblocking(False)
sel = selectors.DefaultSelector()
sel.register(s, selectors.EVENT_READ)
start = time.monotonic()
next_send = start + rng.expovariate(args.rate)
seq = 0
with open(args.output, 'w', buffering=1) as out:
    while time.monotonic() < start + args.seconds + 3:
        now = time.monotonic()
        if next_send < start + args.seconds and now >= next_send:
            packet = {'id': seq, 'sent_ns': time.monotonic_ns(), 'remaining': [],
                      'return_to': ['10.78.0.1', 9001], 'trace': [], 'payload': 'x' * 512}
            s.sendto(json.dumps(packet).encode(), ('10.78.0.2', 9000))
            out.write(json.dumps({'event': 'send', 'id': seq, 'sent_ns': packet['sent_ns'],
                                  'scheduled_ns': round(next_send * 1e9)}) + '\n')
            seq += 1
            next_send += rng.expovariate(args.rate)
        wait = max(0, min(0.01, next_send - time.monotonic())) if next_send < start + args.seconds else 0.01
        for key, mask in sel.select(wait):
            while True:
                try: data = s.recv(65535)
                except BlockingIOError: break
                received_ns = time.monotonic_ns()
                packet = json.loads(data)
                packet.pop('payload')
                out.write(json.dumps({'event': 'receive', 'received_ns': received_ns, **packet}) + '\n')
