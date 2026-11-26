#!/usr/bin/env bash
# Give the installer ISO XORA's own name: the disc label (shown by file managers, used to find the
# installer at boot) and the boot menu titles. bootc-image-builder names it after the base system
# ("Fedora-S-dvd-x86_64-44", "Install XORA OS 44").
#
#   ./iso-relabel.sh output/bootiso/install.iso [xora-os-0.1-x86_64.iso]
#
# Needs: xorriso, mtools (mcopy/mtype), isomd5sum (implantisomd5); squashfs-tools and sudo for the
# installer artwork (skipped without them).
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

SUDO="${SUDO:-sudo}"
w="$(mktemp -d)"; trap '[ -d "$w/root" ] && $SUDO rm -rf "$w/root"; rm -rf "$w"' EXIT
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
  [ "$old" = "$new" ] || ! grep -q "$old" "$1"
}
fix "$w/efi.cfg"; fix "$w/bios.cfg"; fix "$w/efiimg.cfg"
mcopy -o -i "$w/efiboot.img" "$w/efiimg.cfg" ::/EFI/BOOT/grub.cfg

# the installer itself (Anaconda): XORA artwork instead of the Fedora logo, and XORA's version instead
# of the base system's ("Welcome to XORA OS 0.1"). It runs as root so file owners and SELinux labels inside
# the installer image are kept exactly. Skipped (with a note) when squashfs-tools aren't installed.
branding=()
if command -v unsquashfs >/dev/null && command -v mksquashfs >/dev/null && [ -d os/installer-branding ]; then
  echo "installer: XORA artwork and version $ver"
  xorriso -osirrox on -indev "$in" -extract /images/install.img "$w/install.img" >/dev/null 2>&1
  $SUDO unsquashfs -q -d "$w/root" "$w/install.img" >/dev/null
  P="$w/root/usr/share/anaconda/pixmaps"
  for d in "$P" "$P"/*/; do
    for f in sidebar-bg sidebar-logo topbar-bg; do
      [ -f "$d/$f.png" ] && $SUDO cp os/installer-branding/$f.png "$d/$f.png"
    done
  done
  $SUDO cp os/installer-branding/anaconda_header.png "$P/anaconda_header.png"
  $SUDO sed -i "s/@define-color fedora #[0-9a-fA-F]*;/@define-color fedora #0b1020;/" "$P"/*.css
  # Ubuntu-like look: Ubuntu Sans font and XORA's stylesheet, appended to the installer's own
  if [ -f os/installer-branding/xora.css ]; then
    for css in "$P"/fedora.css "$P"/*/fedora-*.css; do
      [ -f "$css" ] && cat os/installer-branding/xora.css | $SUDO tee -a "$css" >/dev/null
    done
  fi
  if ls os/files/usr/share/fonts/xora/UbuntuSans*.ttf >/dev/null 2>&1; then
    $SUDO mkdir -p "$w/root/usr/share/fonts/xora"
    $SUDO cp os/files/usr/share/fonts/xora/UbuntuSans*.ttf "$w/root/usr/share/fonts/xora/"
    $SUDO chroot "$w/root" fc-cache -f /usr/share/fonts/xora >/dev/null 2>&1 || true
  fi
  $SUDO sed -i "s/^version = .*/version = $ver/" "$w/root/.buildstamp"
  grep -q "^version = $ver$" "$w/root/.buildstamp"
  $SUDO mksquashfs "$w/root" "$w/install.new.img" -comp zstd -b 131072 -noappend -quiet >/dev/null
  $SUDO chown "$(id -u):$(id -g)" "$w/install.new.img"
  $SUDO rm -rf "$w/root"
  branding=(-map "$w/install.new.img" /images/install.img)
else
  echo "(installer artwork skipped: install squashfs-tools)"
fi

# the system the installer copies (/container, an OCI image): gzip -> zstd. About the same size, but zstd
# unpacks several times faster, which is most of the "Deployment starting" time on older computers.
recompress=()
if [ "${XORA_ZSTD:-1}" = 1 ]; then
  if command -v skopeo >/dev/null; then SKOPEO=(skopeo)
  else SKOPEO=($SUDO podman run --rm --security-opt label=disable -v "$w:/w" "${SKOPEO_IMAGE:-localhost/xora-os:base}" skopeo); fi
  xorriso -osirrox on -indev "$in" -extract /container "$w/container" >/dev/null 2>&1
  chmod -R u+w "$w/container"
  if find "$w/container/blobs/sha256" -type f -size -1024k -exec grep -l 'tar+gzip' {} + 2>/dev/null | grep -q .; then
    echo "installer image: gzip -> zstd"
    src=/w/container dst=/w/container-zstd; command -v skopeo >/dev/null && { src="$w/container"; dst="$w/container-zstd"; }
    "${SKOPEO[@]}" copy --quiet --dest-compress-format zstd "oci:$src" "oci:$dst"
    $SUDO chown -R "$(id -u):$(id -g)" "$w/container-zstd" 2>/dev/null || true
    recompress=(-rm_r /container -- -map "$w/container-zstd" /container)
  fi
  rm -rf "$w/container"
fi

rm -f "$out"
# -boot_image any replay keeps the original EFI partition appended for USB boot (GPT partition 2),
# which still names the old label: replace it with the fixed efiboot.img, or a USB stick won't boot.
xorriso -indev "$in" -outdev "$out" -boot_image any replay \
  -append_partition 2 0xef "$w/efiboot.img" \
  -volid "$new" "${branding[@]}" "${recompress[@]}" \
  -map "$w/efi.cfg" /EFI/BOOT/grub.cfg \
  -map "$w/bios.cfg" /boot/grub2/grub.cfg \
  -map "$w/efiboot.img" /images/efiboot.img \
  -commit >/dev/null 2>&1

# "Test this media" checks an embedded checksum: write a new one for the changed disc
implantisomd5 --force "$out" >/dev/null

got="$(xorriso -indev "$out" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: //p')"
[ "$got" = "$new" ] || { echo "relabel failed (volume id is $got)" >&2; exit 1; }
# check every place a booting PC reads the label: the disc's menus and the USB EFI partition
p2="$(xorriso -indev "$out" -report_system_area plain 2>/dev/null | awk '/GPT start and size :   2/{print $7, $8}')"
if [ -n "$p2" ]; then
  set -- $p2
  dd if="$out" of="$w/p2.img" bs=512 skip="$1" count="$2" status=none
  mtype -i "$w/p2.img" ::/EFI/BOOT/grub.cfg | grep -q "'$new'" \
    || { echo "relabel failed: the USB EFI partition still has the old label" >&2; exit 1; }
fi
echo "Built: $out"
