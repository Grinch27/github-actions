#!/usr/bin/env python3
# Scope: frozen S01 inline functions and C02-07-06; no production mutations.
# Unknowns: hosted runner sudo policy, target image contents, external consumers.
# Risks: sudo secure_path bypasses PATH stubs; never invoke APT via real sudo.
# Follow-up: actual GitHub Job Container matrix and C03 unknown-container policy.
# Verify: exact source extraction, real UID, argument/env/status, full Step stubs.
"""Read-only source regression; all package/service operations are simulated."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap

BASH = shutil.which('bash')
PYTHON = sys.executable
ALLOW = ('DEBIAN_FRONTEND', 'DEBCONF_NONINTERACTIVE_SEEN',
                  'APT_LISTCHANGES_FRONTEND', 'NEEDRESTART_MODE', 'LANG', 'LC_ALL', 'TZ')
FUNCTIONS = ('run_sudo', 'run_sudo_env')
ROOT = Path(__file__).resolve().parents[1]
COUNT = 0


def check(condition, name):
    global COUNT
    if not condition:
        raise AssertionError(name)
    COUNT += 1
    print(f'PASS {name}', flush=True)


def steps(path):
    """Extract inline run blocks and explicitly referenced action-local Bash scripts."""
    source = path.read_text(encoding='utf-8')
    lines = source.splitlines()
    result = []
    for i, line in enumerate(lines):
        external = re.fullmatch(r' +run: bash "\$GITHUB_ACTION_PATH/([A-Za-z0-9_-]+\.sh)"', line)
        if external:
            result.append((path.parent / external[1]).read_text(encoding='utf-8'))
            continue
        match = re.fullmatch(r'( +)run: \|', line)
        if not match:
            continue
        indent = len(match[1])
        block = []
        for item in lines[i + 1:]:
            if item.strip() and len(item) - len(item.lstrip()) <= indent:
                break
            block.append(item)
        result.append(textwrap.dedent('\n'.join(block)) + '\n')
    if not result and re.search(r'^\s+run:', source, re.M):
        raise AssertionError(f'unsupported run syntax: {path}')
    return result


def definition(source, name):
    match = re.search(rf'(?m)^({name}\(\) \{{\n[\s\S]*?^\}}\n)', source)
    if not match:
        raise AssertionError(f'missing {name} definition')
    return match[1]


def run(script, env=None, args=()):
    return subprocess.run([BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail',
                                                  '-c', script, 'test', *args], env=env,
                                                text=True, capture_output=True, timeout=30, check=False)


def make_env(path):
    # Explicit PATH, no inherited Bash functions, BASH_ENV or credentials.
    return {'PATH': str(path), 'HOME': str(path.parent), 'TERM': 'dumb'}


def link(directory, name, target=None):
    target = target or shutil.which(name)
    if not target:
        raise RuntimeError(f'missing test dependency: {name}')
    (directory / name).symlink_to(target)


def executable(path, body):
    path.write_text(body, encoding='utf-8')
    path.chmod(0o755)


def source_checks(root, canonical, partial=False):
    counts = dict.fromkeys(FUNCTIONS, 0)
    for path in sorted((root / '.github/actions').glob('*/action.yml')):
        if path.parent.name == 'run-sudo':
            continue  # Legacy implementation deliberately excluded.
        for number, script in enumerate(steps(path), 1):
            for name in FUNCTIONS:
                if re.search(rf'(?m)^{name}\(\) \{{', script):
                    counts[name] += 1
                    check(definition(script, name) == canonical[name],
                                f'{path.parent.name}/{number}: {name} frozen body')
    print(f'INLINE_COUNTS {counts}')
    if not partial:
        check(counts == {'run_sudo': 34, 'run_sudo_env': 25},
                    'all 59 expected frozen definitions (inline and action-local scripts) present')


def privilege(canonical, mode):
    uid = os.getuid()
    check((uid == 0) == (mode == 'root'), f'{mode}: actual uid={uid}')
    functions = ''.join(canonical.values())
    with tempfile.TemporaryDirectory(prefix='s01-') as temp:
        folder = Path(temp) / 'bin'
        folder.mkdir()
        link(folder, 'id')
        link(folder, 'env')
        if mode in ('sudo', 'denied'):
            link(folder, 'sudo')
        env = make_env(folder)
        check((shutil.which('sudo', path=env['PATH']) is not None) ==
                    (mode in ('sudo', 'denied')), f'{mode}: controlled sudo presence')
        if mode in ('denied', 'no-sudo'):
            result = run(functions + 'run_sudo "$@"\n', env, ('/usr/bin/id', '-u'))
            check(result.returncode != 0 and result.stdout.strip() != '0',
                        f'{mode}: elevation blocked')
            if mode == 'no-sudo':
                check(result.returncode == 1 and 'root privileges required' in result.stderr,
                            'no-sudo: expected diagnostic/status')
            return
        args = ['', 'two words', '*?[x]', '$HOME; command', '--flag', 'line\nbreak', '中文']
        # Actual sudo, harmless absolute executable; never invoke apt/service commands.
        code = 'import json,os,sys; print(json.dumps([os.getuid(),sys.argv[1:]]))'
        res = run(functions + 'run_sudo "$@"\nprintf "STEP_CONTINUED\\n"\n',
                            env, (PYTHON, '-c', code, *args))
        check(res.returncode == 0, f'{mode}: command succeeds ({res.stderr.strip()})')
        lines = res.stdout.splitlines()
        check(json.loads(lines[0]) == [0, args], f'{mode}: argv exact, actual uid 0')
        check(lines[1:] == ['STEP_CONTINUED'], f'{mode}: Step continues')
        for status in (7, 42, 127):
            res = run(functions + 'run_sudo "$@"\n', env,
                                (PYTHON, '-c', f'raise SystemExit({status})'))
            check(res.returncode == status, f'{mode}: exit {status}')
        # Unset, empty and non-exported values; avoid secret data or locale changes.
        code = ('import json,os; print(json.dumps({k:os.environ.get(k) for k in '
                        + repr(ALLOW) + '}))')
        setup = ('DEBIAN_FRONTEND=noninteractive\nDEBCONF_NONINTERACTIVE_SEEN=true\n'
                          'APT_LISTCHANGES_FRONTEND=none\nNEEDRESTART_MODE=l\nLANG=C\n'
                          'LC_ALL=\nTZ=Etc/UTC\n')
        expected = dict(zip(ALLOW, ('noninteractive', 'true', 'none', 'l', 'C', '', 'Etc/UTC')))
        res = run(functions + setup + 'run_sudo_env "$@"\n', env, (PYTHON, '-c', code))
        check(res.returncode == 0 and json.loads(res.stdout) == expected,
                    f'{mode}: seven environment variables, empty and unexported')
        res = run(functions + 'unset NEEDRESTART_MODE\nrun_sudo_env "$@"\n', env,
                            (PYTHON, '-c', code))
        check(res.returncode == 0 and json.loads(res.stdout)['NEEDRESTART_MODE'] is None,
                    f'{mode}: unset remains unset')
        res = run(functions + 'run_sudo_env "$@"\n', env,
                            (PYTHON, '-c', 'raise SystemExit(37)'))
        check(res.returncode == 37, f'{mode}: env wrapper exit 37')
        link(folder, 'bash')
        bridge = ('import subprocess,sys; '
                            "subprocess.run(['bash','-c','run_sudo_env \"$@\"',"
                            "'run_sudo_env',*sys.argv[1:]],check=True)")
        res = run(functions + setup + 'export ' + ' '.join(ALLOW) + '\nexport -f run_sudo run_sudo_env\n"$@"\n',
                            env, (PYTHON, '-c', bridge, PYTHON, '-c', code))
        check(res.returncode == 0 and json.loads(res.stdout) == expected,
                    f'{mode}: real Python -> Bash exported wrappers with harmless payload')
        res = run('! declare -F run_sudo && ! declare -F run_sudo_env\n', env)
        check(res.returncode == 0, f'{mode}: independent Bash Step')


def snap(script, baseline=None, actual=False):
    # Full Step, strict PATH of stubs; no actual bash -c write or rm/apt/snap/systemctl.
    cases = [('docker', True, False, None, False),
                      ('podman', False, True, None, False),
                      ('both', True, True, 2, False),
                      ('detector', False, False, 0, False),
                      ('detector-systemd-visible', False, False, 0, True),
                      ('unknown-no-probe', False, False, None, False),
                      ('unknown-probe-error', False, False, 2, False),
                      ('native', False, False, 1, True),
                      ('native-no-probe', False, False, None, True)]
    if actual:
        cases = [('actual-container', False, False, None, False)]
    stub = '#!/bin/bash\nname=${0##*/}\nprintf "%s %s\\n" "$name" "$*" >> "$LOG"\n'
    stub += '''case "$name" in
  id) echo 0;;
  snap) if [ "$1" = list ]; then printf 'Name Version\\ncore 1\\n'; fi;;
  systemd-detect-virt) exit "$DETECT_RC";;
  bash) [[ "$1" == -c && "$2" == *nosnap.pref* ]] || exit 99;;
  sudo) exit 98;;
esac
exit 0
'''
    for name, docker, podman, detector, manager in cases:
        with tempfile.TemporaryDirectory(prefix='snap-') as temp:
            d = Path(temp)
            b = d / 'bin'
            b.mkdir()
            log = d / 'trace'
            log.touch()
            for cmd in ('id', 'df', 'apt-get', 'dpkg-query', 'snap', 'systemctl', 'rm', 'bash', 'sudo'):
                executable(b / cmd, stub)
            link(b, 'awk')
            link(b, 'env')
            if actual and shutil.which('systemd-detect-virt'):
                link(b, 'systemd-detect-virt')
            elif detector is not None:
                executable(b / 'systemd-detect-virt', stub)
            if docker:
                (d / 'docker').touch()
            if podman:
                (d / 'podman').touch()
            if manager:
                (d / 'manager').mkdir()
            def remap(body):
                return (body.replace('/.dockerenv', str(d / 'docker'))
                                .replace('/run/.containerenv', str(d / 'podman'))
                                .replace('/run/systemd/system', str(d / 'manager')))
            env = make_env(b) | {'LOG': str(log), 'DETECT_RC': str(detector or 0)}
            result = run(script if actual else remap(script), env)
            events = log.read_text().splitlines()
            operations = [x for x in events if not x.startswith('systemd-detect-virt ')]
            detected = actual or docker or podman or detector == 0
            check(result.returncode == 0, f'snap/{name}: exit 0: {result.stderr.strip()}')
            if detected:
                check(operations == [] and 'Skip Snap cleanup inside container' in result.stdout,
                            f'snap/{name}: zero uid/sudo/APT/dpkg/snap/systemctl/rm/write/df')
            else:
                check(any(x.startswith('apt-get ') for x in operations) and
                            any(x.startswith('bash -c ') for x in operations),
                            f'snap/{name}: original cleanup reached (stubs only)')
                service = [x for x in operations if x.startswith('systemctl ')]
                check(service == (['systemctl disable --now snapd.socket',
                                                      'systemctl stop snapd.service'] if manager else []),
                            f'snap/{name}: native service boundary/order')
                if baseline:
                    log.write_text('')
                    old = run(remap(baseline), env)
                    check(old.returncode == result.returncode and log.read_text().splitlines() == operations,
                                f'snap/{name}: baseline side-effect trace identical')


def resolver(script, mode):
    # Execute the actual Python heredoc + exported functions. The sudo stub is
    # intentionally not real: sudo secure_path could resolve real apt-get.
    if mode not in ('root', 'mock-sudo', 'mock-denied'):
        raise ValueError(mode)
    if mode == 'root' and os.getuid() != 0:
        raise AssertionError('resolver root mode requires actual root')
    with tempfile.TemporaryDirectory(prefix='resolver-') as temp:
        d = Path(temp)
        b = d / 'bin'
        b.mkdir()
        log = d / 'apt.log'
        output = d / 'output'
        for cmd in ('bash', 'env'):
            link(b, cmd)
        link(b, 'python3', PYTHON)
        if mode == 'root':
            link(b, 'id')
        else:
            executable(b / 'id', '#!/bin/bash\necho 1000\n')
            executable(b / 'sudo', '#!/bin/bash\n[[ "$1" == -n ]] || exit 99\nshift\n' +
                                  ('exit 57\n' if mode == 'mock-denied' else 'exec "$@"\n'))
        executable(b / 'apt-get', f'#!{PYTHON}\nimport json, os, sys\n'
                              'with open(os.environ["LOG"], "a") as f:\n'
                              ' f.write(json.dumps([sys.argv[1:], os.environ.get("NEEDRESTART_MODE")])+"\\n")\n'
                              'raise SystemExit(int(os.environ["APT_EXIT"]))\n')
        executable(b / 'apt-cache', '#!/bin/bash\ncase "$1:$*" in\n'
                              'search:*gcc*) echo gcc-15;;\nsearch:*clang*) echo clang-21;;\n'
                              'search:*openjdk*) echo openjdk-25-jdk;;\n'
                              'policy:*) echo "  Candidate: 1";;\n*) exit 99;;\nesac\n')
        env = make_env(b) | {'LOG': str(log), 'GITHUB_OUTPUT': str(output),
                                                    'NEEDRESTART_MODE': 'l', 'APT_EXIT': '0'}
        res = run(script, env)
        if mode == 'mock-denied':
            check(res.returncode != 0 and not log.exists() and not output.exists(),
                        'resolver/mock-denied: no apt or output after sudo rejection')
            return
        check(res.returncode == 0, f'resolver/{mode}: Python -> Bash succeeds: {res.stderr.strip()}')
        check(json.loads(log.read_text()) == [['-yqq', 'update'], 'l'],
                    f'resolver/{mode}: exact apt argv and environment')
        check(output.read_text().splitlines() == [
                'gcc_version=15', 'clang_version=21', 'jdk_version=25',
                'custom_env=gcc_version=15;clang_version=21;jdk_version=25'],
                f'resolver/{mode}: all four outputs')
        output.unlink()
        env['APT_EXIT'] = '42'
        res = run(script, env)
        check(res.returncode != 0 and not output.exists() and '42' in res.stderr,
                    f'resolver/{mode}: APT failure reaches Python; no output')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--mode', required=True, choices=('root', 'sudo', 'denied', 'no-sudo', 'simulation', 'detected-container'))
    parser.add_argument('--snap-baseline', type=Path)
    parser.add_argument('--partial-source', action='store_true',
                                            help='Only for a deliberately incomplete local fixture')
    args = parser.parse_args()
    paths = args.repo / '.github/actions'
    resolve_steps = steps(paths / 'resolve-toolchain-version/action.yml')
    assert len(resolve_steps) == 2, 'unexpected resolver steps'
    source = resolve_steps[1]
    canonical = {name: definition(source, name) for name in FUNCTIONS}
    if args.mode == 'simulation':
        source_checks(args.repo, canonical, args.partial_source)
        snap_steps = steps(paths / 'purge-snap/action.yml')
        assert len(snap_steps) == 1, 'unexpected Snap steps'
        baseline = steps(args.snap_baseline)[0] if args.snap_baseline else None
        snap(snap_steps[0], baseline)
        resolver(source, 'mock-sudo')
        resolver(source, 'mock-denied')
    elif args.mode == 'detected-container':
        snap_steps = steps(paths / 'purge-snap/action.yml')
        assert len(snap_steps) == 1, 'unexpected Snap steps'
        snap(snap_steps[0], actual=True)
    else:
        privilege(canonical, args.mode)
        if args.mode == 'root':
            resolver(source, 'root')
    print(f'RESULT {args.mode}: {COUNT} assertions passed')


if __name__ == '__main__':
    main()
