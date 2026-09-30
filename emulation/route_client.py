"""Independent tenant route choices from packet feedback in one event loop."""
import argparse
import heapq
import json
import math
import random
import selectors
import socket
import time

CHAINS = [['A', 'D'], ['C', 'B'], ['A', 'B']]
IP = {name: f'10.79.{i}.2' for i, name in enumerate(['source', 'A', 'B', 'C', 'D'], 1)}

def next_arrival(when, hazard, rate, step_at, factor):
    """Invert integrated intensity for one piecewise-constant Poisson step."""
    if when >= step_at: return when + hazard / (rate * factor)
    before = (step_at - when) * rate
    if hazard <= before: return when + hazard / rate
    return step_at + (hazard - before) / (rate * factor)

def main(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((IP['source'], 9001))
    sock.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(sock, selectors.EVENT_READ)
    origin = time.monotonic()
    events, tenants, pending = [], [], {}
    for t in range(20):
        rng = random.Random(args.seed * 100 + t)
        phase_draw = rng.random()
        phase = phase_draw if args.phasing == 'staggered' else 0
        tenants.append({'cost': [20., 20., 20.], 'preferred': t % 2,
                        'gateway': 0, 'eligible': 0, 'probe': 0, 'rng': rng,
                        # Splittable mode: route weights and a route RNG separate from the arrival RNG.
                        'weights': [.5, .5, 0.], 'route_rng': random.Random(args.seed * 100 + t + 50_000)})
        heapq.heappush(events, (next_arrival(0, rng.expovariate(1), args.rate / 20, args.step_at, args.step_factor), t, 'data'))
        if args.fixed_route is None:
            heapq.heappush(events, (phase, t, 'update'))
            heapq.heappush(events, (rng.random(), t, 'probe'))
    seq = 0
    with open(args.output, 'w', buffering=1) as out:
        def log(row): out.write(json.dumps(row) + '\n')
        log({'event': 'configuration', **vars(args), 'origin_ns': round(origin * 1e9)})
        while time.monotonic() - origin < args.seconds + 3:
            elapsed = time.monotonic() - origin
            # Expired observations penalize the measured route and remain auditable.
            for ident in list(pending):
                t, route, sent = pending[ident]
                if time.monotonic_ns() - sent > 500_000_000:
                    tenants[t]['cost'][route] = 500.
                    del pending[ident]
                    log({'event': 'timeout', 'id': ident, 'tenant': t, 'route': route})
            budget = 128
            while events and events[0][0] <= elapsed and events[0][0] < args.seconds and budget:
                budget -= 1
                when, t, kind = heapq.heappop(events)
                state = tenants[t]
                eligible = 3 if when >= args.activate and args.cap > 0 else 2
                if kind == 'update' and args.split_step is not None:
                    w, cost = state['weights'], state['cost']
                    old = max(range(3), key=lambda r: (w[r], -r))
                    best = min(range(eligible), key=lambda r: (cost[r], r))
                    for r in range(eligible):
                        if r != best and cost[r] > 1.05 * cost[best]:
                            moved = args.split_step * w[r] * (cost[r] - cost[best]) / cost[r]
                            w[r] -= moved; w[best] += moved
                    if eligible == 3 and w[2] > args.cap:
                        w[min(range(2), key=lambda r: (cost[r], r))] += w[2] - args.cap; w[2] = args.cap
                    state['preferred'] = max(range(3), key=lambda r: (w[r], -r))
                    log({'event': 'update', 'tenant': t, 'seconds': elapsed, 'previous': old,
                         'preferred': state['preferred'], 'weights': list(w), 'cost_ms': list(cost)})
                    heapq.heappush(events, (when + 1, t, 'update'))
                    continue
                if kind == 'update':
                    best = min(range(eligible), key=lambda r: (state['cost'][r], r))
                    old = state['preferred']
                    if state['cost'][best] < .95 * state['cost'][old]: state['preferred'] = best
                    log({'event': 'update', 'tenant': t, 'seconds': elapsed,
                         'previous': old, 'preferred': state['preferred'], 'cost_ms': list(state['cost'])})
                    heapq.heappush(events, (when + 1, t, 'update'))
                    continue
                if kind == 'probe':
                    route = state['probe'] % eligible
                    state['probe'] += 1
                    heapq.heappush(events, (when + 1, t, 'probe'))
                elif args.fixed_route is not None:
                    route = args.fixed_route
                    heapq.heappush(events, (next_arrival(when, state['rng'].expovariate(1), args.rate / 20, args.step_at, args.step_factor), t, 'data'))
                else:
                    if args.split_step is None:
                        route = state['preferred']
                    else:
                        route = state['route_rng'].choices(range(3), weights=state['weights'])[0]
                    if when >= args.activate:
                        state['eligible'] += 1
                        if route == 2 and state['gateway'] + 1 > math.floor(args.cap * state['eligible'] + 1e-9):
                            route = min(range(2), key=lambda r: (state['cost'][r], r))
                        state['gateway'] += route == 2
                    next_when = next_arrival(when, state['rng'].expovariate(1), args.rate / 20, args.step_at, args.step_factor)
                    heapq.heappush(events, (next_when, t, 'data'))
                sent = time.monotonic_ns()
                hops = [[IP[name], 9000] for name in CHAINS[route]]
                packet = {'id': seq, 'sent_ns': sent, 'tenant': t, 'route': route, 'kind': kind,
                          'remaining': hops[1:], 'return_to': [IP['source'], 9001],
                          'trace': [], 'payload': 'x' * 512}
                sock.sendto(json.dumps(packet).encode(), tuple(hops[0]))
                pending[seq] = (t, route, sent)
                log({'event': 'send', 'id': seq, 'tenant': t, 'route': route, 'kind': kind,
                     'sent_ns': sent, 'scheduled_ns': round((origin + when) * 1e9),
                     'gateway_count': state['gateway'], 'eligible_count': state['eligible']})
                seq += 1
            delay = min(.005, max(0, events[0][0] - (time.monotonic() - origin))) if events and events[0][0] < args.seconds else .005
            for key, mask in selector.select(delay):
                for _ in range(512):
                    try: data = sock.recv(65535)
                    except BlockingIOError: break
                    received = time.monotonic_ns()
                    packet = json.loads(data)
                    packet.pop('payload')
                    ident = packet['id']
                    if ident in pending:
                        t, route, sent = pending.pop(ident)
                        estimate = (received - sent) / 1e6
                        tenants[t]['cost'][route] = .7 * tenants[t]['cost'][route] + .3 * estimate
                    log({'event': 'receive', 'received_ns': received, **packet})

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
    p.add_argument('--split-step', type=float, default=None,
                   help='splittable routing: fraction moved per update toward the cheapest chain')
    p.add_argument('--fixed-route', type=int, choices=[0, 1, 2], default=None,
                   help='calibration only: send all data on one chain without probes or adaptation')
    p.add_argument('--output', required=True)
    main(p.parse_args())
