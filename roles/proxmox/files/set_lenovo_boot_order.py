#!/usr/bin/env python3
# Order the Lenovo boot sequences: internal disk first, network last.
#
# On the M910q the UEFI `BootOrder` variable is DERIVED -- the firmware
# regenerates it at POST from its own varstore (GUID ef7eae21-...), so
# efibootmgr edits do not survive a reboot. The authoritative lists are the
# Setup "Boot Sequence" screens:
#   ExPrimaryBootOrder    normal power-on
#   ExAutomaticBootOrder  wake-on-LAN / automatic power-on  (network first here
#                         is why a WoL wake PXE-boots)
# Each is 12 x 8-byte records: a class header (device id 0xFFFF) followed by the
# concrete devices of that class. Reordering whole class groups is enough.
#   class 0x0041 = HDD, 0x0012 = USB, 0x0020 = network.
# See 02-proxmox/docs/firmware.md.
#
# Idempotent: writes only when the order differs. Prints "changed:"/"unchanged:".
import glob
import subprocess
import sys

VARS = ("ExPrimaryBootOrder", "ExAutomaticBootOrder")
HDD, USB, NET = 0x0041, 0x0012, 0x0020
RANK = {HDD: 0, NET: 2}          # disk first, network last, everything else between
REC = 8


def _cls(rec):
    return rec[0] | (rec[1] << 8)


def groups(body):
    """Consecutive records sharing a class code travel together."""
    out, cur = [], []
    for i in range(0, len(body), REC):
        r = body[i:i + REC]
        if cur and _cls(cur[0]) == _cls(r):
            cur.append(r)
        else:
            if cur:
                out.append(cur)
            cur = [r]
    if cur:
        out.append(cur)
    return out


def reorder(body):
    new = b"".join(r for g in sorted(groups(body), key=lambda g: RANK.get(_cls(g[0]), 1))
                   for r in g)
    # never hand the firmware anything but a permutation of what it gave us
    old_recs = sorted(body[i:i + REC] for i in range(0, len(body), REC))
    new_recs = sorted(new[i:i + REC] for i in range(0, len(new), REC))
    assert old_recs == new_recs and len(new) == len(body), "refusing: not a permutation"
    return new


def main():
    dry = "--dry-run" in sys.argv
    changed = []
    for name in VARS:
        found = glob.glob("/sys/firmware/efi/efivars/%s-*" % name)
        if not found:
            continue                      # not Lenovo firmware; nothing to do
        path = found[0]
        raw = open(path, "rb").read()
        attrs, body = raw[:4], raw[4:]
        if not body or len(body) % REC:
            continue
        new = reorder(body)
        if new == body:
            continue
        changed.append(name)
        if not dry:
            open("/root/efivar-backup-%s.bin" % name, "wb").write(raw)
            subprocess.run(["chattr", "-i", path], check=False)
            with open(path, "wb") as fh:   # efivarfs wants attrs+data in one write
                fh.write(attrs + new)
    print(("changed: %s" % ",".join(changed)) if changed else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
