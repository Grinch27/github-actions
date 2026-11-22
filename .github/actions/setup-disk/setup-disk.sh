#!/usr/bin/env bash
# Scope: disposable GitHub-hosted Ubuntu runners/job containers; one LVM route.
# Assumptions: dedicated empty mountpoint, usable loop/LVM tools and hosted VM disposal.
# Unknown: overlay/bind storage may share physical capacity; sparse allocation is not a guarantee.
# Risk: loop/LVM/mkfs affect host-visible devices; unknown ownership must stop, never guess.
# Follow-up: real native/container capacity, actual LVM activation and cleanup behavior.
# Verify: exact S01 wrappers, nonempty path refusal, resource identity, partial failures.
set -euo pipefail

fail() { printf 'setup-disk: %s\n' "$1" >&2; exit 1; }
run_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -n "$@"
  else
    printf 'run_sudo: root privileges required\n' >&2
    return 1
  fi
}

run_sudo_env() {
  local name
  local -a env_args=()
  for name in DEBIAN_FRONTEND DEBCONF_NONINTERACTIVE_SEEN APT_LISTCHANGES_FRONTEND NEEDRESTART_MODE LANG LC_ALL TZ; do
    if [[ -v "$name" ]]; then
      env_args+=("${name}=${!name}")
    fi
  done
  run_sudo env "${env_args[@]}" "$@"
}

report() {
  df -hT -- "$path_build"
  printf 'workspace_mode=%s\n' "$1" >> "${GITHUB_OUTPUT:?}"
}

[[ ${RUNNER_ENVIRONMENT:-} == github-hosted ]] || fail 'Only disposable GitHub-hosted runners are supported'
case "${DISK_ENVIRONMENT_KIND:-unknown}" in
  native|container) ;;
  *) fail 'Unknown execution environment';;
esac
: "${path_build:?path_build required}" "${root_num:?root_num required}" "${mnt_num:?mnt_num required}" "${GITHUB_OUTPUT:?}"
[[ "$path_build" == /* && "$path_build" != / && "$path_build" == "$(realpath -m -- "$path_build")" ]] || fail 'Mount path must be an absolute canonical directory'
case "$path_build" in
  /bin|/bin/*|/sbin|/sbin/*|/lib*|/usr|/usr/*|/etc|/etc/*|/dev|/dev/*|/proc|/proc/*|/sys|/sys/*|/run|/run/*|/boot|/boot/*|/var|/var/*|/root|/root/*|/home|/mnt|/tmp|/github|/github/*) fail 'Protected mount path' ;;
esac
# A new mount must not hide the runner's working or temporary directory.
for protected in "${GITHUB_WORKSPACE:-}" "${RUNNER_TEMP:-}" "${HOME:-}"; do
  [[ -n "$protected" ]] || continue
  protected=$(realpath -m -- "$protected")
  [[ "$protected" != "$path_build" && "$protected" != "$path_build/"* ]] || fail 'Mount path would hide a runner directory'
done
[[ "$root_num" =~ ^(0|[1-9][0-9]{0,5})$ && "$mnt_num" =~ ^(0|[1-9][0-9]{0,5})$ ]] || fail 'Reserve must be a nonnegative integer GiB value'
command -v mountpoint >/dev/null || fail 'mountpoint unavailable'
run_sudo true

# mountpoint(1): 0 = mountpoint, 32 = not a mountpoint, other = probe error.
mount_status() {
  local rc=0
  mountpoint -q -- "$path_build" || rc=$?
  case "$rc" in
    0) printf 'mounted\n';;
    32) printf 'unmounted\n';;
    *) return 1;;
  esac
}
current_mount=unmounted
if [[ -e "$path_build" ]]; then
  current_mount=$(mount_status) || fail 'Cannot inspect workspace mount state'
fi
if [[ "$current_mount" == mounted ]]; then
  [[ -d "$path_build" && -w "$path_build" ]] || fail 'Existing mount is not writable'
  report existing
  exit 0
fi
# Never hide existing files under a new mount. Do not suppress find failures.
if [[ -e "$path_build" ]]; then
  [[ -d "$path_build" && -r "$path_build" && -x "$path_build" ]] || fail 'Existing workspace is not an accessible directory'
  first_entry=$(find "$path_build" -mindepth 1 -maxdepth 1 -print -quit) || fail 'Cannot inspect workspace contents'
  [[ -z "$first_entry" ]] || fail 'Refuse to mount over a nonempty directory'
else
  run_sudo mkdir -p -- "$path_build"
fi
run_sudo chown "$(id -u):$(id -g)" -- "$path_build"
[[ -w "$path_build" ]] || fail 'Workspace directory is not writable'

ensure_tools() {
  local cmd
  local -a required=(losetup pvcreate pvremove pvs vgcreate vgremove vgs lvcreate lvremove lvs mount umount mountpoint findmnt lsblk truncate)
  local missing=false
  for cmd in "${required[@]}"; do command -v "$cmd" >/dev/null || missing=true; done
  command -v mkfs.xfs >/dev/null || command -v mkfs.ext4 >/dev/null || missing=true
  if [[ $missing == true ]]; then
    export DEBIAN_FRONTEND=noninteractive
    run_sudo_env apt-get -yqq update || return 1
    run_sudo_env apt-get -yqq install lvm2 util-linux e2fsprogs xfsprogs || return 1
  fi
  for cmd in "${required[@]}"; do command -v "$cmd" >/dev/null || return 1; done
  command -v mkfs.xfs >/dev/null || command -v mkfs.ext4 >/dev/null
}
ensure_tools || fail 'Required disk tools unavailable'

# Container-only node preparation; the existing privileged mount design is retained.
# No replacement of an existing device node or kernel/service policy change.
if [[ $DISK_ENVIRONMENT_KIND == container ]]; then
  if command -v modprobe >/dev/null; then run_sudo modprobe loop >/dev/null 2>&1 || true; fi
  if command -v mknod >/dev/null; then
    [[ -e /dev/loop-control || -L /dev/loop-control ]] || run_sudo mknod -m 660 /dev/loop-control c 10 237 || true
    for i in {0..7}; do
      [[ -e /dev/loop$i || -L /dev/loop$i ]] || run_sudo mknod -m 660 "/dev/loop$i" b 7 "$i" || true
    done
  fi
fi

min_bytes=$((1024 ** 3))
free_bytes() { df -B1 --output=avail -- "$1" | awk 'END {print $1}'; }
fallback() {
  local free state
  free=$(free_bytes "$path_build") || fail 'Cannot determine fallback capacity'
  state=$(mount_status) || fail 'Cannot inspect fallback mount state'
  [[ "$state" == unmounted && "$free" =~ ^[0-9]+$ && "$free" -ge "$min_bytes" && -w "$path_build" ]] || fail 'Directory fallback unsafe or insufficient space'
  echo '::warning::LVM unavailable; using directory workspace (1 GiB minimum is not a firmware capacity guarantee).'
  report directory
}
if ! run_sudo losetup -f >/dev/null 2>&1; then fallback; exit 0; fi

root_dev=$(stat -c %d -- /)
mnt_dev=''
[[ ! -d /mnt ]] || mnt_dev=$(stat -c %d -- /mnt)
backing_dirs=()
backing_sizes=()
add_backing() {
  local dir=$1 reserve=$2 available usable
  available=$(free_bytes "$dir") || fail 'Cannot read available space'
  [[ "$available" =~ ^[0-9]+$ ]] || fail 'Invalid available space'
  usable=$((available - reserve * min_bytes))
  if ((usable >= min_bytes)); then
    backing_dirs+=("$dir")
    backing_sizes+=("$usable")
  fi
}
if [[ -n "$mnt_dev" && "$mnt_dev" == "$root_dev" ]]; then
  ((root_num >= mnt_num)) || root_num=$mnt_num
elif [[ -n "$mnt_dev" ]]; then
  add_backing /mnt "$mnt_num"
fi
add_backing / "$root_num"
if ((${#backing_dirs[@]} == 0)); then fail 'Insufficient space after reserves'; fi

nonce_dir=$(mktemp -d "${RUNNER_TEMP:?}/github-disk.XXXXXXXX")
vg_name="github_${nonce_dir##*.}"
lv_path="/dev/$vg_name/runner"
files=()
loops=()
pvs_created=()
vg_created=false
lv_created=false
mounted=false
uncertain=false

vg_absent() {
  local names
  names=$(run_sudo vgs --noheadings -o vg_name) || return 1
  awk -v name="$vg_name" '$1 == name {found=1} END {exit found ? 1 : 0}' <<< "$names"
}
vg_absent || fail 'Volume group collision or unable to enumerate groups'

# Detect exact LV backing device instead of trusting mountpoint alone.
verify_owned_mount() {
  local actual expected
  actual=$(findmnt --mountpoint "$path_build" --noheadings --output MAJ:MIN | awk 'NF {print $1}') || return 1
  expected=$(lsblk --nodeps --noheadings --output MAJ:MIN -- "$lv_path" | awk 'NF {print $1}') || return 1
  [[ -n "$expected" && "$actual" == "$expected" ]]
}
cleanup() {
  local loop file state attached
  [[ $uncertain == false ]] || return 1
  state=$(mount_status) || return 1
  if [[ $mounted == true ]]; then
    [[ "$state" == mounted ]] && verify_owned_mount || return 1
    run_sudo umount -- "$path_build" || return 1
    state=$(mount_status) || return 1
    [[ "$state" == unmounted ]] || return 1
    mounted=false
  else
    [[ "$state" == unmounted ]] || return 1
  fi
  if [[ $lv_created == true ]]; then
    run_sudo lvremove -fy -- "$lv_path" || return 1
    lv_created=false
  fi
  if [[ $vg_created == true ]]; then
    run_sudo vgremove -fy -- "$vg_name" || return 1
    vg_created=false
  fi
  vg_absent || return 1
  for loop in "${pvs_created[@]}"; do
    run_sudo pvremove -y -- "$loop" || return 1
  done
  for loop in "${loops[@]}"; do
    run_sudo losetup -d -- "$loop" || return 1
  done
  for file in "${files[@]}"; do
    attached=$(run_sudo losetup --associated "$file") || return 1
    [[ -z "$attached" ]] || return 1
  done
  for file in "${files[@]}"; do run_sudo rm -f -- "$file" || return 1; done
  rmdir -- "$nonce_dir" || return 1
}

allocate() {
  local idx file loop state entry
  for idx in "${!backing_dirs[@]}"; do
    # Failure of resource-creating command may mean partial success. Do not guess.
    file=$(run_sudo mktemp "${backing_dirs[$idx]%/}/${vg_name}.XXXXXXXX.img") || { uncertain=true; return 1; }
    files+=("$file")
    run_sudo truncate -s "${backing_sizes[$idx]}" -- "$file" || return 1
    loop=$(run_sudo losetup --find --show -- "$file") || { uncertain=true; return 1; }
    [[ "$loop" =~ ^/dev/loop[0-9]+$ ]] || { uncertain=true; return 1; }
    loops+=("$loop")
    run_sudo pvcreate -y -- "$loop" || { uncertain=true; return 1; }
    pvs_created+=("$loop")
  done
  run_sudo vgcreate "$vg_name" "${loops[@]}" || { uncertain=true; return 1; }
  vg_created=true
  run_sudo lvcreate -n runner -l 100%FREE "$vg_name" || { uncertain=true; return 1; }
  lv_created=true
  if command -v mkfs.xfs >/dev/null; then
    run_sudo mkfs.xfs -f "$lv_path" || return 1
  else
    run_sudo mkfs.ext4 -F "$lv_path" || return 1
  fi
  state=$(mount_status) || { uncertain=true; return 1; }
  [[ "$state" == unmounted ]] || { uncertain=true; return 1; }
  entry=$(find "$path_build" -mindepth 1 -maxdepth 1 -print -quit) || { uncertain=true; return 1; }
  [[ -z "$entry" ]] || { uncertain=true; return 1; }
  run_sudo mount -- "$lv_path" "$path_build" || return 1
  mounted=true
  verify_owned_mount || { uncertain=true; return 1; }
  run_sudo chown "$(id -u):$(id -g)" -- "$path_build" || return 1
  [[ -w "$path_build" ]] || return 1
}

# Explicit propagation in conditional functions; errexit is suppressed there.
if allocate; then
  rmdir -- "$nonce_dir"
  report lvm
else
  cleanup || fail 'Allocation failed and resource cleanup cannot be proven; stop, no directory fallback'
  fallback
fi
