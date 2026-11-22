#!/usr/bin/env bash
# Scope: toolchain overrides used by existing OpenWrt/U-Boot callers; no arbitrary env injection.
# Unknown: historical callers outside indexed repositories; verify before publishing.
# Risk: reject unsafe names, multiline values, and PATH overrides; never print environment values.
# Follow-up: extend the allowlist only for reviewed consumers; test runner env-file propagation.
# Verify: invalid entries write nothing, paths remain inside PATH_build, no elevated mkdir.
set -euo pipefail

fail() { printf 'input-custom: %s\n' "$1" >&2; exit 1; }

load_custom() {
  local raw=${CUSTOM_ENV_TEXT:-} item key value
  local -a parts=() records=()
  local -A seen=()
  [[ -n "$raw" ]] || return 0
  [[ "$raw" != *$'\n'* && "$raw" != *$'\r'* && "$raw" != ';'* && "$raw" != *';' && "$raw" != *';;'* ]] || fail 'Invalid assignment separators'
  IFS=';' read -r -a parts <<< "$raw"
  for item in "${parts[@]}"; do
    [[ "$item" == *=* ]] || fail 'Expected key=value'
    key=${item%%=*}
    value=${item#*=}
    case "$key" in
      gcc_purge|gcc_install|gcc_switch|gcc_aarch64|clang_purge|clang_install|clang_switch|jdk_purge|jdk_install|jdk_switch|docker_install|qemu_install)
        [[ "$value" == true || "$value" == false ]] || fail 'Invalid boolean override' ;;
      gcc_version|clang_version|jdk_version)
        [[ "$value" =~ ^[1-9][0-9]{0,2}$ ]] || fail 'Invalid toolchain version' ;;
      *) fail 'Unsupported override key' ;;
    esac
    [[ ! ${seen[$key]+present} ]] || fail 'Duplicate override key'
    seen[$key]=1
    records+=("$key=$value")
  done
  printf '%s\n' "${records[@]}" >> "${GITHUB_ENV:?GITHUB_ENV required}"
  printf 'Loaded %d validated toolchain override(s).\n' "${#records[@]}"
}

prepare_paths() {
  local base=${PATH_build:-} key path resolved canonical
  local -a paths=()
  # Enumerate variable names, not their values; do not log the environment.
  while IFS= read -r key; do
    path=${!key}
    [[ -n "$path" ]] || continue
    [[ -n "$base" && "$base" == /* && "$base" != / ]] || fail 'PATH_build must designate a dedicated absolute directory'
    canonical=$(realpath -m -- "$base")
    [[ "$canonical" == "$base" ]] || fail 'PATH_build must be canonical and not traverse symlinks'
    resolved=$(realpath -m -- "$path")
    [[ "$path" == "$resolved" && ( "$resolved" == "$base" || "$resolved" == "$base/"* ) ]] || fail 'PATH_* escapes PATH_build or is noncanonical'
    paths+=("$path")
  done < <(compgen -e | grep '^PATH_' || true)
  if ((${#paths[@]})); then
    mkdir -p -- "${paths[@]}"
    printf 'Prepared %d build directory entries.\n' "${#paths[@]}"
  fi
}

case "${CUSTOM_ENV_PHASE:-load}" in
  load) load_custom ;;
  paths) prepare_paths ;;
  both) load_custom; prepare_paths ;;
  *) fail 'Invalid phase' ;;
esac
