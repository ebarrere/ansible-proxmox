#!/usr/bin/env python3
# Set the UEFI BootOrder to: internal disk / OS first, then USB, then network last.
# Boot order lives in the EFI BootOrder variable (NOT the AMI Setup varstore), so
# it cannot be set by setup_var.efi in the m910q pre-boot image -- see
# 02-proxmox/docs/firmware.md. efibootmgr manages it on the installed host.
#
# Idempotent: only calls `efibootmgr -o` when the resulting order differs.
# Prints "changed: <old> -> <new>" or "unchanged: <order>" for Ansible changed_when.
#
# Test offline:  ./set_uefi_boot_order.py --stdin --dry-run < sample_efibootmgr_v.txt
import glob
import os
import re
import subprocess
import sys


def _norm(label):
    l = (label or "").lower().strip()
    if l.startswith("uefi:"):
        l = l[5:].strip()
    return l.split(",", 1)[0].strip()


def removable_labels(entries):
    """Labels of devices the firmware ALSO exposes as a UEFI USB entry, plus any
    local USB block device. A CSM/BBS shadow entry for the same stick looks like
    `Boot0010* SanDisk  BBS(HD,,0x0)` -- no USB marker at all -- so without this
    it ranks as an internal disk and can outrank the real OS disk."""
    out = set()
    for _n, label, path in entries:
        if "usb(" in (path or "").lower():
            t = _norm(label)
            if t:
                out.add(t)
    for dev in glob.glob("/sys/block/*/device"):
        blk = dev.rsplit("/", 2)[1]
        try:
            if "/usb" not in os.path.realpath("/sys/block/" + blk):
                continue
            for attr in ("vendor", "model"):
                try:
                    v = open(os.path.join(dev, attr)).read().strip().lower()
                except OSError:
                    continue
                if v:
                    out.add(v)
        except OSError:
            continue
    return out


def _is_removable(label, removable):
    l = _norm(label)
    return bool(l) and any(t in l or l in t for t in removable)


def classify(label, path, removable=frozenset()):
    """0 = internal disk/OS (first), 1 = USB, 2 = network (last)."""
    p = (path or "").lower()
    l = (label or "").lower()
    if ("mac(" in p or "ipv4(" in p or "ipv6(" in p or "uri(" in p
            or "bbs(network" in p
            or any(k in l for k in ("network", "pxe", "iba", "ip4", "ipv4", "ipv6"))):
        return 2
    if "usb(" in p or "usb" in l or "removable" in l:
        return 1
    if "bbs(" in p and _is_removable(label, removable):
        return 1
    return 0


def os_rank(label):
    """Within the internal-disk group, boot the installed OS before stale entries."""
    l = (label or "").lower()
    return 0 if any(k in l for k in ("debian", "proxmox", "uefi os", "grub")) else 1


def parse(out):
    entries, order = [], []
    for line in out.splitlines():
        m = re.match(r'^BootOrder:\s*(.*)$', line)
        if m:
            order = [x for x in m.group(1).replace(' ', '').split(',') if x]
            continue
        m = re.match(r'^Boot([0-9A-Fa-f]{4})\*?\s+(.*)$', line)
        if m:
            rest = m.group(2).split('\t', 1)
            entries.append((m.group(1).upper(), rest[0].strip(),
                            rest[1] if len(rest) > 1 else ''))
    return entries, order


def desired(entries, order):
    by = {n: (l, p) for n, l, p in entries}
    cur = [n for n in order if n in by]          # keep only live entries, in order
    removable = removable_labels(entries)
    return sorted(cur, key=lambda n: (classify(by[n][0], by[n][1], removable),
                                      os_rank(by[n][0]), cur.index(n)))


def main():
    dry = "--dry-run" in sys.argv
    if "--stdin" in sys.argv:
        out = sys.stdin.read()
    else:
        out = subprocess.run(["efibootmgr", "-v"], capture_output=True,
                             text=True, check=True).stdout
    entries, order = parse(out)
    new = desired(entries, order)
    if not new or new == order:
        print("unchanged: %s" % ",".join(order))
        return 0
    print("changed: %s -> %s" % (",".join(order), ",".join(new)))
    if not dry and "--stdin" not in sys.argv:
        subprocess.run(["efibootmgr", "-o", ",".join(new)], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
