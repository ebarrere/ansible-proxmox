# M910q firmware, BIOS & serial console

Reference for the ThinkCentre M910q Tiny PVE nodes (`pve1`–`pve3`, SMBIOS
`10MUS17L00`). Covers BIOS flashing, hidden BIOS settings applied via a UEFI
Setup-variable editor, and the physical serial console wiring.

## LVFS / fwupd status

`fwupdmgr` sees the **System Firmware** (ESRT GUID `de118c7c-f1a9-464d-8656-e5edac6ffd92`)
and it is capsule-*capable*, **but Lenovo does not publish the M910q BIOS to
LVFS** — it shows as *Updatable* yet not *Supported on remote server*. The only
LVFS offerings on this hardware are **Secure Boot KEK / dbx configuration
updates**. There is no Linux-native Lenovo flasher, and `flashrom` internal
writes are blocked by BootGuard / flash-descriptor locks.

Consequence: **the BIOS version cannot be updated from the OS.** Use fwupd only
for the Secure Boot config updates:

```sh
# report only (default, safe)
ansible-playbook playbooks/firmware_update.yml -i inventories/pve/hosts.yml
# actually apply the LVFS (dbx/KEK) updates, one host at a time, reboots
ansible-playbook playbooks/firmware_update.yml -i inventories/pve/hosts.yml -e firmware_apply=true
```

## BIOS version update (M1AKT59A → M1AKT5AA)

Latest is `M1AKT5AA` (WU 1.0.0.90). Only supported paths are the Lenovo **DOS
flasher** or Windows. The DOS flasher is on the Ventoy stick as
`M910q: FLASH BIOS to M1AKT5AA`; it is **legacy/DOS only**, so:

1. BIOS Setup → **Startup** → enable **CSM / Legacy** boot.
2. Boot the USB as a non-`UEFI:` device (F12) → Ventoy → the flash entry.
3. It auto-runs `flash2.exe imagem1a.rom /bb /rsmb` and reboots.
4. Set boot mode **back to UEFI** afterward.

Optional — the version bump (.89→.90) is minor; skipping it is fine.

## Hidden BIOS settings via setup_var (UEFI Setup variable `Setup`)

The Lenovo Setup UI hides most AMI Aptio options. They live in the NVRAM
variable **`Setup`** (GUID `EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9`) and are
written at a UEFI shell with `setup_var.efi` (datasone). Offsets below are from
BIOS `M1AKT5AA`; they also match `59A`. The Ventoy entry
`M910q: CONFIGURE homelab` (a FAT `serial-enable.img` — needed because the
shell can't read Ventoy's exFAT) applies them automatically.

Serial console — **both** SIO UARTs, 115200 8N1, VT-UTF8, no flow control:

| Offset | Setting | Value |
|--------|---------|-------|
| 0xFE4 | Serial Port1 = 3F8/IRQ4 | 0x01 |
| 0xFE5 | Serial Port2 = 2F8/IRQ3 | 0x01 (NOT 0x03 — Port2's value map differs from Port1) |
| 0x1033 / 0x1034 | Console Redirection COM0 / COM1 | 0x01 |
| 0x1029 / 0x102A | Bits per second = 115200 | 0x07 |
| 0x1035 / 0x1036 | Terminal Type = VT-UTF8 | 0x02 |
| 0x102B / 0x102C | Data Bits = 8 | 0x08 |
| 0x102D / 0x102E | Parity = None | 0x01 |
| 0x102F / 0x1030 | Stop Bits = 1 | 0x01 |
| 0x1031 / 0x1032 | Flow Control = None | 0x00 |
| 0x1037 / 0x1038 | VT-UTF8 Combo Key Support | 0x01 (lets terminals send F-keys over serial) |

Homelab hardware settings:

| Offset | Setting | Value |
|--------|---------|-------|
| 0x594 | Intel Virtualization (VT-x) | 0x01 (Enabled) |
| 0x7B0 | VT-d | 0x01 (Enabled) |
| 0xF2F | After Power Loss | 0x00 (Power On) |
| 0xFEB | ICE Performance Mode | 0x01 (Better Thermal) |

To read a value instead of writing it, omit `=`: `setup_var.efi Setup:0x1033`.

## Physical serial wiring

The board has two internal serial headers, **COM1** and **COM2** (keyed). On
these units the DB9 pigtail must go on the **COM2** header — that is the UART
that maps to Serial Port1 (3F8), the enabled COM0 redirection. Both ends are
DTE, so a **null modem** is required between the M910q DB9 and the USB-serial
adapter. Terminal: `screen /dev/ttyUSB0 115200` (8N1, no flow).

## Function keys over serial

With VT-UTF8 Combo Key Support on (0x1037/0x1038), send BIOS hotkeys as `Esc`
combos in your terminal (type Escape, then the char), during POST:

| Key | Send | Key | Send |
|-----|------|-----|------|
| F1 (Setup) | `Esc` `1` | F10 | `Esc` `0` |
| F2..F9 | `Esc` `2`..`9` | F11 | `Esc` `!` |
| | | F12 (boot menu) | `Esc` `@` |

To break a "no boot device" reboot loop: mash `Esc` `@` at the splash to reach
the boot menu, or `Esc` `1` for Setup, then set a real boot path (PXE/network).

