#!/usr/bin/env bash
# Scope: classify the current Linux Job; no systemd install or service mutation.
# Assumption: GitHub-hosted native VM reports none/1 from systemd-detect-virt.
# Unknown: absent detector or unknown/error responses; never assume native in these cases.
# Risk: container detection does not grant host resource ownership or capabilities.
# Verify: positive evidence takes priority, unknown is explicit, both files agree.
set -euo pipefail
: "${GITHUB_OUTPUT:?}" "${GITHUB_ENV:?}"

kind=unknown
source=insufficient-evidence
if [[ -n ${GHA_JOB_CONTAINER_ID:-} ]]; then
  kind=container
  source=job-context
elif [[ -f /.dockerenv ]]; then
  kind=container
  source=docker-marker
elif [[ -f /run/.containerenv ]]; then
  kind=container
  source=container-marker
elif command -v systemd-detect-virt >/dev/null 2>&1; then
  status=0
  detected=$(systemd-detect-virt --container 2>/dev/null) || status=$?
  if [[ $status == 0 && -n $detected && $detected != none ]]; then
    kind=container
    source=systemd-detect-virt
  elif [[ $status == 1 && $detected == none && ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]]; then
    kind=native
    source=hosted-no-container
  fi
fi
case "$kind" in
  container) in_container=true ;;
  native) in_container=false ;;
  *) in_container=unknown ;;
esac
for destination in "$GITHUB_OUTPUT" "$GITHUB_ENV"; do
  printf 'in_container=%s\nenvironment_kind=%s\ndetection_source=%s\n' "$in_container" "$kind" "$source" >> "$destination"
done
printf 'Execution environment: %s (%s)\n' "$kind" "$source"
