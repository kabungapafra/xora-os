#!/usr/bin/env bash
# Give the installer ISO XORA's own name: the disc label (shown by file managers, used to find the
# installer at boot) and the boot menu titles. bootc-image-builder names it after the base system
# ("Fedora-S-dvd-x86_64-44", "Install XORA OS 44").
#
#   ./iso-relabel.sh output/bootiso/install.iso [xora-os-0.1-x86_64.iso]
#
# Needs: xorriso, mtools (mcopy/mtype), isomd5sum (implantisomd5). No root.
set -euo pipefail
in="$1"
out="${2:-${in%.iso}-xora.iso}"

ver="${XORA_VERSION:-0.1}"
arch="$(xorriso -indev "$in" -find /EFI/BOOT -name 'BOOT*.EFI' 2>/dev/null | grep -qi aa64 && echo aarch64 || echo x86_64)"
new="XORA-OS-${ver}-${arch}"            # ISO 9660 volume ids: max 32 characters, no spaces

for t in xorriso mcopy mtype implantisomd5; do
  command -v "$t" >/dev/null || { echo "needs $t (apt install xorriso mtools isomd5sum / dnf install xorriso mtools isomd5sum)" >&2; exit 1; }
done

old="$(xorriso -indev "$in" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: //p')"
[ -n "$old" ] || { echo "can't read the volume id of $in" >&2; exit 1; }
echo "disc label: $old -> $new"

w="$(mktemp -d)"; trap 'rm -rf "$w"' EXIT
xorriso -osirrox on -indev "$in" \
  -extract /EFI/BOOT/grub.cfg "$w/efi.cfg" \
  -extract /boot/grub2/grub.cfg "$w/bios.cfg" \
  -extract /images/efiboot.img "$w/efiboot.img" >/dev/null 2>&1
chmod u+w "$w"/*
mtype -i "$w/efiboot.img" ::/EFI/BOOT/grub.cfg > "$w/efiimg.cfg"

fix() {   # the label everywhere, "XORA OS 44" -> "XORA OS 0.1", no Fedora icon class in the menu
  sed -i -e "s/${old}/${new}/g" \
         -e "s/XORA OS [0-9][0-9]*\( \|'\)/XORA OS ${ver}\1/g" \
         -e "s/--class fedora //g" "$1"
  ! grep -q "$old" "$1"
}
fix "$w/efi.cfg"; fix "$w/bios.cfg"; fix "$w/efiimg.cfg"
mcopy -o -i "$w/efiboot.img" "$w/efiimg.cfg" ::/EFI/BOOT/grub.cfg

rm -f "$out"
xorriso -indev "$in" -outdev "$out" -boot_image any replay \
  -volid "$new" \
  -map "$w/efi.cfg" /EFI/BOOT/grub.cfg \
  -map "$w/bios.cfg" /boot/grub2/grub.cfg \
  -map "$w/efiboot.img" /images/efiboot.img \
  -commit >/dev/null 2>&1

# "Test this media" checks an embedded checksum: write a new one for the changed disc
implantisomd5 --force "$out" >/dev/null

got="$(xorriso -indev "$out" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: //p')"
[ "$got" = "$new" ] || { echo "relabel failed (volume id is $got)" >&2; exit 1; }
echo "Built: $out"
