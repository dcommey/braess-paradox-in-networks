"""Verify real namespaces, veth traffic, and kernel rate/delay shaping."""
import json
import platform
import subprocess
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel

setLogLevel('info')
net = Mininet(controller=None, link=TCLink)
try:
    a = net.addHost('a', ip='10.77.0.1/24')
    b = net.addHost('b', ip='10.77.0.2/24')
    net.addLink(a, b, bw=10, delay='5ms', max_queue_size=100)
    net.start()
    loss = net.pingAll(timeout='2')
    shaping = a.cmd('tc -s qdisc show dev a-eth0')
    assert 'netem' in shaping and 'htb' in shaping, shaping
    assert loss == 0, f'Packet loss: {loss}'
    ping = a.cmd('ping -c 10 -i 0.1 10.77.0.2')
    print(json.dumps({'kernel': platform.release(), 'packet_loss_percent': loss,
                      'qdisc': shaping, 'ping': ping,
                      'packages': subprocess.check_output(['dpkg-query', '-W'], text=True)}, indent=2))
finally:
    net.stop()
