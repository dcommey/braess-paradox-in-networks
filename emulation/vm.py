#!/usr/bin/env python3
"""Dedicated local ARM guest; all mutable VM state stays in ignored runtime/."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'runtime'
PORT = 22375

def call(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)

def prepare():
    RUN.mkdir(exist_ok=True)
    image = RUN / 'ubuntu.img'
    candidate = image if image.exists() else RUN / 'ubuntu.img.part'
    expected = next(line.split()[0] for line in (RUN / 'SHA256SUMS').read_text().splitlines()
                    if line.split()[-1].lstrip('*') == 'noble-server-cloudimg-arm64.img')
    actual = hashlib.file_digest(candidate.open('rb'), 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError('Ubuntu image checksum mismatch')
    if candidate != image:
        candidate.rename(image)
    if not (RUN / 'id_ed25519').exists():
        call(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'braess-local-guest', '-f', RUN / 'id_ed25519'])
    if not (RUN / 'guest.qcow2').exists():
        call(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', image, RUN / 'guest.qcow2', '16G'])
    seed = RUN / 'seed'
    seed.mkdir(exist_ok=True)
    key = (RUN / 'id_ed25519.pub').read_text().strip()
    (seed / 'meta-data').write_text('instance-id: braess-emulation-001\nlocal-hostname: braess-emulation\n')
    (seed / 'user-data').write_text('''#cloud-config
users:
  - name: researcher
    groups: [sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - ''' + key + '''
ssh_pwauth: false
disable_root: true
package_update: true
packages: [mininet, openvswitch-switch, iperf3, iproute2, python3-numpy, python3-scipy, tcpdump, sysstat]
runcmd:
  - [sh, -c, 'mkdir -p /home/researcher/evidence; uname -a > /home/researcher/evidence/kernel.txt; dpkg-query -W > /home/researcher/evidence/packages.txt']
  - [systemctl, start, openvswitch-switch]
  - [sh, -c, 'timeout 120 mn --switch ovsbr --test pingall > /home/researcher/evidence/mininet-smoke.log 2>&1; echo $? > /home/researcher/evidence/mininet-smoke.exit']
  - [sh, -c, 'chown -R researcher:researcher /home/researcher/evidence']
''')
    if not (RUN / 'seed.iso').exists():
        call(['hdiutil', 'makehybrid', '-iso', '-joliet', '-default-volume-name', 'cidata', '-o', RUN / 'seed.iso', seed])
    if not (RUN / 'vars.fd').exists():
        shutil.copy('/opt/homebrew/share/qemu/edk2-arm-vars.fd', RUN / 'vars.fd')
    (RUN / 'image-sha256.txt').write_text(actual + '\n')

def start():
    pidfile = RUN / 'qemu.pid'
    if pidfile.exists():
        pid = pidfile.read_text().strip()
        proc = subprocess.run(['ps', '-p', pid, '-o', 'command='], capture_output=True, text=True)
        if 'qemu-system-aarch64' in proc.stdout and str(RUN / 'guest.qcow2') in proc.stdout:
            print('Guest already running:', pid)
            return
        pidfile.unlink()
    call(['qemu-system-aarch64', '-name', 'braess-emulation', '-machine', 'virt,accel=hvf',
          '-cpu', 'host', '-smp', '4', '-m', '4096',
          '-drive', 'if=pflash,format=raw,readonly=on,file=/opt/homebrew/share/qemu/edk2-aarch64-code.fd',
          '-drive', f'if=pflash,format=raw,file={RUN / "vars.fd"}',
          '-drive', f'if=virtio,format=qcow2,file={RUN / "guest.qcow2"}',
          '-drive', f'if=virtio,format=raw,readonly=on,file={RUN / "seed.iso"}',
          '-netdev', f'user,id=net0,hostfwd=tcp:127.0.0.1:{PORT}-:22',
          '-device', 'virtio-net-pci,netdev=net0', '-device', 'virtio-rng-pci',
          '-display', 'none', '-serial', f'file:{RUN / "serial.log"}',
          '-monitor', 'none', '-daemonize', '-pidfile', pidfile])

def ssh(command):
    call(['ssh', '-p', str(PORT), '-i', RUN / 'id_ed25519', '-o', 'IdentitiesOnly=yes',
          '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
          '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={RUN / "known_hosts"}',
          'researcher@127.0.0.1', command])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'start', 'status', 'ssh'])
    parser.add_argument('command', nargs='?', default='true')
    args = parser.parse_args()
    if args.action == 'prepare': prepare()
    elif args.action == 'start': start()
    elif args.action == 'status': ssh('cloud-init status --long; cat ~/evidence/mininet-smoke.exit ~/evidence/mininet-smoke.log 2>/dev/null')
    else: ssh(args.command)
