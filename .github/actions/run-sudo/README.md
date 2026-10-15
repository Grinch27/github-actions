# run_sudo

Job-scoped privilege wrapper for Ubuntu runners and Linux `jobs.<job>.container` jobs.

## Install once per job

```yaml
steps:
  - name: Install run_sudo
    uses: Grinch27/github-actions/.github/actions/run-sudo@main
  - name: Install packages
    shell: bash
    run: |
      run_sudo apt-get -yqq update
      run_sudo env DEBIAN_FRONTEND=noninteractive apt-get -yqq install curl git
```

The action creates an executable `run_sudo` under `$RUNNER_TEMP` and adds that directory
to `$GITHUB_PATH`, making the command available to **subsequent steps in the same job**.
No `sudo` package installation or write access to `/usr/local/bin` is required.

- UID 0: `exec` the command directly.
- Non-root with `sudo`: use `sudo -n` (non-interactive).
- Non-root without `sudo`: fail clearly; never silently run a privileged command unprivileged.
- Return the wrapped command's exit code unchanged.

Use `run_sudo` for privileged shell commands in both Ubuntu hosted runners and Ubuntu job
containers after this action. Install separately in each job. Shell redirections are
evaluated before `run_sudo` starts; use `run_sudo tee` or `run_sudo sh -c '...'`
when writing to privileged paths. To pass required environment variables explicitly,
use `run_sudo env KEY=value command`. `systemctl` also requires an active systemd manager;
`run_sudo` cannot provide one inside a conventional container.

This action does not affect commands run inside separate `docker run` containers,
other jobs, or non-Linux shells. Migration of older inline `sudo` and `run_root`
invocations is a separate compatibility change.
