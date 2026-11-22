#!/usr/bin/env python3
# Scope: local mock tests only; never run real disk/privilege operations.
# Risks: mock accuracy differs from hosted CI. Real runner and Docker acceptance remains required.
# Unknown: actual GitHub expression evaluation and runtime environment.
# Verify: actual candidate shell files, metadata ordering, failed inputs, no out-of-scope writes.
# Follow-up: independently validate device identity, apt hooks, and capacity on hosted CI.
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / '.github/actions'
INPUT = ACTIONS / 'input-custom/input-custom.sh'
DISK = ACTIONS / 'setup-disk/setup-disk.sh'
DETECT = ACTIONS / 'check-indocker/check-indocker.sh'
MOCK = r'''#!/usr/bin/env bash
set -euo pipefail
name=${0##*/}
{ printf '%s' "$name"; printf '\t%s' "$@"; printf '\n'; } >> "$MOCK_LOG"
case "$name" in
  sudo) [[ "$1" == -n ]]; shift; [[ ${MOCK_DENY_SUDO:-false} != true ]] || exit 57; case "$1" in
    true) exit 0 ;;
    env) shift; while [[ "${1:-}" == *=* ]]; do export "$1"; shift; done; exec "$MOCK_BIN/$1" "${@:2}" ;;
    id|df|stat|losetup|pvcreate|pvremove|pvs|vgcreate|vgremove|vgs|lvcreate|lvremove|lvs|mount|umount|mountpoint|findmnt|truncate|mkfs.xfs|mkfs.ext4|mkdir|chown|rm|mktemp|modprobe|mknod|apt-get) exec "$MOCK_BIN/$1" "${@:2}" ;;
    *) exit 99;; esac ;;
  id) if [[ "$1" == -u ]]; then echo "${MOCK_UID:-0}"; else echo 1000; fi ;;
  mountpoint) [[ ${MOCK_MOUNT_PROBE_ERROR:-false} != true ]] || exit 1; [[ -f "$MOCK_DIR/mounted" ]] || exit 32 ;;
  df) if [[ "$*" == *--output=avail* ]]; then printf 'Avail\n%s\n' "${MOCK_FREE:-12884901888}"; else echo 'mock df'; fi ;;
  stat) if [[ "${*: -1}" == /mnt && ${MOCK_SEPARATE:-false} == true ]]; then echo 2; else echo 1; fi ;;
  losetup)
    if [[ "$1" == -f ]]; then [[ ${MOCK_NO_LOOP:-false} != true ]]; exit; fi
    if [[ "$1" == -d ]]; then [[ ${MOCK_CLEANUP_FAIL:-false} != true ]]; exit; fi
    if [[ "$1" == --associated ]]; then if [[ ${MOCK_ASSOCIATED:-false} == true ]]; then echo "/dev/loop99: still attached"; fi; exit 0; fi
    [[ ${MOCK_FAIL:-} != losetup ]] || { : > "$MOCK_DIR/partial-loop"; exit 1; }
    i=10; [[ ! -f "$MOCK_DIR/index" ]] || read -r i < "$MOCK_DIR/index"; i=$((i+1)); echo "$i" > "$MOCK_DIR/index"; echo "/dev/loop$i" ;;
  mktemp)
    if [[ "$1" == -d ]]; then /usr/bin/mktemp "$@"; else
      [[ "$1" == /github_* || "$1" == /mnt/github_* ]]; echo "${1/XXXXXXXX/testfile}"
    fi ;;
  vgs)
    [[ ${MOCK_VGS_ERROR:-false} != true ]] || exit 1
    if [[ -f "$MOCK_DIR/vg" ]]; then /usr/bin/cat "$MOCK_DIR/vg"; elif [[ ${MOCK_COLLISION:-false} == true ]]; then
      for p in "$MOCK_DIR"/github-disk.*; do printf "github_%s\n" "${p##*.}"; done;
    fi ;;
  lvs) [[ -f "$MOCK_DIR/lv" ]] ;;
  pvs) exit 0 ;;
  vgcreate) printf "%s\n" "$1" > "$MOCK_DIR/vg"; [[ ${MOCK_FAIL:-} != vgcreate ]] ;;
  vgremove) /usr/bin/rm -f -- "$MOCK_DIR/vg" ;;
  lvcreate) : > "$MOCK_DIR/lv"; [[ ${MOCK_FAIL:-} != lvcreate ]] ;;
  lvremove) /usr/bin/rm -f -- "$MOCK_DIR/lv" ;;
  mount) [[ "${*: -1}" == "$path_build" ]]; if [[ ${MOCK_FAIL:-} == mount-partial ]]; then : > "$MOCK_DIR/mounted"; exit 1; fi; [[ ${MOCK_FAIL:-} != mount ]]; : > "$MOCK_DIR/mounted" ;;
  umount) /usr/bin/rm -f -- "$MOCK_DIR/mounted" ;;
  mkdir) [[ "${*: -1}" == "$path_build" && "$path_build" == "$MOCK_DIR/"* ]]; /usr/bin/mkdir -p -- "$path_build" ;;
  chown) [[ "${*: -1}" == "$path_build" && "$*" != *-R* && ${MOCK_FAIL:-} != chown ]] ;;
  mkfs.xfs|mkfs.ext4) [[ "${*: -1}" == /dev/github_* && ${MOCK_FAIL:-} != "$name" ]] ;;
  truncate|rm) [[ "${*: -1}" == /github_* || "${*: -1}" == /mnt/github_* ]]; [[ ${MOCK_FAIL:-} != "$name" ]] ;;
  pvcreate|pvremove) [[ "${*: -1}" == /dev/loop* && ${MOCK_FAIL:-} != "$name" ]] ;;
  findmnt) if [[ ${MOCK_WRONG_MOUNT:-false} == true ]]; then echo 253:1; else echo 253:0; fi ;;
  lsblk) echo 253:0 ;;
  apt-get)
    printf 'apt-env\t%s\t%s\t%s\n' "${DEBIAN_FRONTEND:-}" "${NEEDRESTART_MODE:-}" "${TZ:-}" >> "$MOCK_LOG"
    [[ ${MOCK_FAIL:-} != apt-get ]] || exit 42
    if [[ "$*" == *install* && ! -e "$MOCK_BIN/lvs" ]]; then /usr/bin/ln -s "$MOCK_BIN/mock" "$MOCK_BIN/lvs"; fi ;;
  mknod|modprobe) exit 0 ;;
  *) exit 99 ;;
esac
''' 

class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.envfile=self.base/'env'
        self.env={'PATH':os.environ['PATH'],'GITHUB_ENV':str(self.envfile),'SECRET_VAR':'never-log-test-secret','CUSTOM_ENV_PHASE':'load'}
    def call(self, raw='', **kwargs):
        return subprocess.run(['bash',str(INPUT)],env={**self.env,'CUSTOM_ENV_TEXT':raw,**kwargs},capture_output=True,text=True)
    def test_empty(self):
        self.assertEqual(self.call().returncode,0); self.assertFalse(self.envfile.exists())
    def test_valid(self):
        r=self.call('gcc_install=true;gcc_version=14;gcc_aarch64=false;clang_version=19')
        self.assertEqual(r.returncode,0,r.stderr); self.assertEqual(self.envfile.read_text(),'gcc_install=true\ngcc_version=14\ngcc_aarch64=false\nclang_version=19\n'); self.assertNotIn('never-log-test-secret',r.stdout+r.stderr)
    def test_paths_after_mount(self):
        target=self.base/'builder'/'output'
        r=self.call('gcc_install=true',PATH_build=str(target.parent),PATH_output=str(target)); self.assertEqual(r.returncode,0); self.assertFalse(target.exists())
        r=self.call(CUSTOM_ENV_PHASE='paths',PATH_build=str(target.parent),PATH_output=str(target)); self.assertEqual(r.returncode,0,r.stderr); self.assertTrue(target.is_dir())
    def test_explicit_both(self):
        target=self.base/'builder'/'output'
        r=self.call('gcc_version=14',CUSTOM_ENV_PHASE='both',PATH_build=str(target.parent),PATH_output=str(target)); self.assertEqual(r.returncode,0,r.stderr); self.assertTrue(target.is_dir())
    def test_paths_escape(self):
        base=self.base/'builder'; target=self.base/'outside'; r=self.call(CUSTOM_ENV_PHASE='paths',PATH_build=str(base),PATH_output=str(target)); self.assertNotEqual(r.returncode,0); self.assertFalse(target.exists()); self.assertFalse(base.exists())
    def test_paths_symlink(self):
        base=self.base/'builder'; base.mkdir(); (base/'link').symlink_to(self.base); r=self.call(CUSTOM_ENV_PHASE='paths',PATH_build=str(base),PATH_output=str(base/'link'/'escaped')); self.assertNotEqual(r.returncode,0); self.assertFalse((self.base/'escaped').exists())
    def test_direct_caller_default_defers_paths(self):
        target=self.base/'builder'/'output'
        r=self.call('gcc_version=14',CUSTOM_ENV_PHASE='',PATH_build=str(target.parent),PATH_output=str(target))
        self.assertEqual(r.returncode,0,r.stderr); self.assertFalse(target.parent.exists())
        obj=yaml.safe_load((ACTIONS/'input-custom/action.yml').read_text())
        self.assertEqual(obj['inputs']['phase']['default'],'load')
    def test_invalid_phase(self): self.assertNotEqual(self.call(CUSTOM_ENV_PHASE='invalid').returncode,0)

# Each input is an independent test, including all-or-nothing behavior.
def invalid_test(raw):
    def test(self):
        r=self.call('gcc_install=true;'+raw)
        self.assertNotEqual(r.returncode,0,raw); self.assertFalse(self.envfile.exists()); self.assertNotIn('never-log-test-secret',r.stdout+r.stderr)
        self.assertFalse((self.base/'injected').exists())
    return test
for i,raw in enumerate(['gcc_version=$(id)','gcc_version=14\nGITHUB_TOKEN=x','gcc_version=14\r','BASH_ENV=/tmp/x','PATH=/tmp/x','PATH_build=/tmp','LD_PRELOAD=x','GITHUB_ENV=x','gcc_install=false','gcc_version=0','gcc_version=014','gcc_install=yes','bad','gcc_version=14;',';gcc_version=14','gcc_version=14;\nfoo=x','gcc_version=14;gcc_version=15']):
    setattr(InputTests,f'test_invalid_{i:02d}',invalid_test(raw))

class DiskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.bin=self.base/'bin'; self.bin.mkdir(); self.build=self.base/'builder'; self.state=self.base/'state.json'; self.out=self.base/'out'
        self.script=self.bin/'mock'; self.script.write_text(MOCK); self.script.chmod(0o755)
        self.commands='sudo id df stat losetup pvcreate pvremove pvs vgcreate vgremove vgs lvcreate lvremove lvs mount umount mountpoint findmnt lsblk truncate mkfs.xfs mkfs.ext4 mkdir chown rm mktemp modprobe mknod apt-get'.split()
        for name in self.commands: (self.bin/name).symlink_to(self.script)
        # Fail closed: no unmocked disk, package or privilege command is on PATH.
        for name in ('bash','true','realpath','find','awk','rmdir','env'):
            executable=Path('/usr/bin')/name
            self.assertTrue(executable.exists(),str(executable)); (self.bin/name).symlink_to(executable)
        self.env={'PATH':str(self.bin),'RUNNER_ENVIRONMENT':'github-hosted','DISK_ENVIRONMENT_KIND':'native','RUNNER_TEMP':str(self.base),'GITHUB_OUTPUT':str(self.out),'path_build':str(self.build),'root_num':'4','mnt_num':'1','MOCK_DIR':str(self.base),'MOCK_LOG':str(self.state),'MOCK_BIN':str(self.bin)}
    def call(self, state=None, script=DISK, **env):
        self.state.write_text('')
        settings=state or {}
        if settings.get('mounted'): (self.base/'mounted').touch()
        mockenv={'MOCK_'+k.upper(): str(v).lower() if isinstance(v,bool) else str(v) for k,v in settings.items()}
        r=subprocess.run(['bash',str(script)],env={**self.env,**mockenv,**env},capture_output=True,text=True,timeout=15)
        calls=[line.rstrip('\n').split('\t') for line in self.state.read_text().splitlines()]
        return r,calls
    def assert_mode(self,r,mode): self.assertEqual(r.returncode,0,r.stderr+'\n'+r.stdout); self.assertEqual(self.out.read_text(),f'workspace_mode={mode}\n')
    def test_forced_container_branch(self):
        r,c=self.call(DISK_ENVIRONMENT_KIND='container'); self.assert_mode(r,'lvm'); self.assertTrue(any(x[0]=='modprobe' for x in c))
    def test_native_no_node_mutation(self):
        r,c=self.call(); self.assert_mode(r,'lvm'); self.assertFalse(any(x[0] in ('modprobe','mknod') for x in c))
    def test_unknown(self):
        r,c=self.call(DISK_ENVIRONMENT_KIND='unknown'); self.assertNotEqual(r.returncode,0); self.assertEqual(c,[])
    def test_denied_sudo(self):
        r,c=self.call({'uid':'1000','deny_sudo':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(any(x[0] in ('mount','truncate','mkdir','chown') for x in c))
    def test_no_sudo(self):
        (self.bin/'sudo').unlink(); r,c=self.call({'uid':'1000'}); self.assertNotEqual(r.returncode,0); self.assertIn('root privileges required',r.stderr); self.assertFalse(any(x[0] in ('mount','truncate','mkdir','chown') for x in c))
    def test_root_without_sudo(self):
        (self.bin/'sudo').unlink(); r,c=self.call(); self.assert_mode(r,'lvm'); self.assertFalse(any(x[0]=='sudo' for x in c))
    def test_disk_apt_env_nonroot(self):
        (self.bin/'lvs').unlink(); r,c=self.call({'uid':'1000'},NEEDRESTART_MODE='l',TZ='Etc/UTC'); self.assert_mode(r,'lvm'); self.assertEqual([x for x in c if x[0]=='apt-env'],[['apt-env','noninteractive','l','Etc/UTC']]*2)
    def test_disk_apt_failure(self):
        (self.bin/'lvs').unlink(); r,c=self.call({'fail':'apt-get'},NEEDRESTART_MODE='l'); self.assertNotEqual(r.returncode,0); self.assertFalse(self.out.exists()); self.assertFalse(any(x[0] in ('truncate','mount') for x in c))
    def test_vgs_failure(self):
        r,c=self.call({'vgs_error':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(any(x[0] in ('truncate','vgremove','mount','rm') for x in c))
    def test_mount_probe_failure(self):
        self.build.mkdir(); r,c=self.call({'mount_probe_error':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(any(x[0] in ('truncate','chown','mount') for x in c))
    def test_wrong_mount_identity(self):
        r,c=self.call({'wrong_mount':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(self.out.exists()); self.assertFalse(any(x[0] in ('umount','lvremove','vgremove','rm') for x in c))
    def test_partial_mount_failure(self):
        r,c=self.call({'fail':'mount-partial'}); self.assertNotEqual(r.returncode,0); self.assertFalse(self.out.exists()); self.assertFalse(any(x[0] in ('umount','lvremove','vgremove','rm') for x in c))
    def test_unconfirmed_detach(self):
        r,c=self.call({'fail':'mkfs.xfs','associated':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(self.out.exists()); self.assertFalse(any(x[0]=='rm' for x in c))
    def test_same_fs(self):
        r,c=self.call(); self.assert_mode(r,'lvm'); trunc=[x for x in c if x[0]=='truncate']; self.assertEqual(len(trunc),1); self.assertEqual(trunc[0][2],str(8*1024**3))
    def test_separate_fs(self):
        r,c=self.call({'separate':True}); self.assert_mode(r,'lvm'); trunc=[x for x in c if x[0]=='truncate']; self.assertEqual([x[2] for x in trunc],[str(11*1024**3),str(8*1024**3)])
    def test_nonroot_sudo(self):
        r,c=self.call({'uid':'1000'}); self.assert_mode(r,'lvm'); self.assertTrue(any(x[:2]==['sudo','-n'] for x in c))
    def test_same_fs_max_reserve(self):
        r,c=self.call(root_num='2',mnt_num='5'); self.assert_mode(r,'lvm'); self.assertEqual([x[2] for x in c if x[0]=='truncate'],[str(7*1024**3)])
    def test_no_loop_fallback(self):
        r,c=self.call({'no_loop':True}); self.assert_mode(r,'directory'); self.assertFalse(any(x[0] in ('truncate','mkfs.xfs','vgcreate') for x in c))
    def test_low_space(self):
        r,c=self.call({'free':2*1024**3}); self.assertNotEqual(r.returncode,0); self.assertFalse(any(x[0]=='truncate' for x in c))
    def test_self_hosted(self):
        r,c=self.call(RUNNER_ENVIRONMENT='self-hosted'); self.assertNotEqual(r.returncode,0); self.assertEqual(c,[])
    def test_bad_reserve(self):
        r,c=self.call(root_num='1+1'); self.assertNotEqual(r.returncode,0); self.assertEqual(c,[])
    def test_protected_path(self):
        r,c=self.call(path_build='/etc'); self.assertNotEqual(r.returncode,0); self.assertEqual(c,[])
    def test_nonempty(self):
        self.build.mkdir(); (self.build/'keep').write_text('keep'); r,c=self.call(); self.assertNotEqual(r.returncode,0); self.assertEqual((self.build/'keep').read_text(),'keep'); self.assertFalse(any(x[0] in ('chown','truncate','mount') for x in c))
    def test_existing_mount(self):
        self.build.mkdir(); r,c=self.call({'mounted':True}); self.assert_mode(r,'existing'); self.assertFalse(any(x[0] in ('chown','truncate','mount') for x in c))
    def test_volume_collision(self):
        r,c=self.call({'collision':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(any(x[0] in ('truncate','vgremove','rm') for x in c))
    def test_cleanup_on_failure(self):
        r,c=self.call({'fail':'mkfs.xfs'}); self.assert_mode(r,'directory'); names=[x[0] for x in c]; self.assertIn('lvremove',names); self.assertIn('vgremove',names); self.assertTrue(any(x[:2]==['losetup','-d'] for x in c)); self.assertIn('rm',names)
    def test_cleanup_failure(self):
        r,c=self.call({'fail':'mkfs.xfs','cleanup_fail':True}); self.assertNotEqual(r.returncode,0); self.assertFalse(self.out.exists()); self.assertFalse(any(x[0]=='rm' for x in c))
    def test_mount_failure(self):
        r,c=self.call({'fail':'mount'}); self.assert_mode(r,'directory'); self.assertFalse(any(x[0]=='umount' for x in c)); self.assertTrue(any(x[0]=='vgremove' for x in c))

class DetectionTests(unittest.TestCase):
    def probe(self, expected, *, job='', docker=False, podman=False, detector=None,
              hosted=True, github=True, stale=False):
        # Exercise exact production probe with only marker paths remapped; detector is mocked.
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); bin_dir=base/'bin'; bin_dir.mkdir()
            if docker: (base/'docker').touch()
            if podman: (base/'podman').touch()
            script=base/'detect.sh'
            script.write_text(DETECT.read_text().replace('/.dockerenv',str(base/'docker')).replace('/run/.containerenv',str(base/'podman')))
            if detector is not None:
                path=bin_dir/'systemd-detect-virt'
                path.write_text('#!/bin/bash\nprintf "%s\\n" "$MOCK_DETECT"\nexit "$MOCK_STATUS"\n'); path.chmod(0o755)
            env={'PATH':str(bin_dir),'GHA_JOB_CONTAINER_ID':job,'GITHUB_OUTPUT':str(base/'out'), 'GITHUB_ENV':str(base/'env'),
                 'RUNNER_ENVIRONMENT':'github-hosted' if hosted else 'self-hosted','GITHUB_ACTIONS':'true' if github else 'false',
                 'MOCK_DETECT':detector[0] if detector else '', 'MOCK_STATUS':str(detector[1]) if detector else '127'}
            if stale: env.update(in_container='true',environment_kind='container')
            res=subprocess.run(['/bin/bash',str(script)],env=env,capture_output=True,text=True)
            self.assertEqual(res.returncode,0,res.stderr)
            output=(base/'out').read_text(); self.assertEqual(output,(base/'env').read_text())
            fields=dict(line.split('=',1) for line in output.splitlines())
            self.assertEqual(fields['environment_kind'],expected)
            self.assertEqual(fields['in_container'],{'container':'true','native':'false','unknown':'unknown'}[expected])
            return fields['detection_source']
    def test_job_context(self): self.assertEqual(self.probe('container',job='abc',detector=('none',1)),'job-context')
    def test_docker_marker(self): self.assertEqual(self.probe('container',docker=True),'docker-marker')
    def test_podman_marker(self): self.assertEqual(self.probe('container',podman=True),'container-marker')
    def test_virtualization(self): self.assertEqual(self.probe('container',detector=('container-other',0)),'systemd-detect-virt')
    def test_native(self): self.assertEqual(self.probe('native',detector=('none',1),stale=True),'hosted-no-container')
    def test_missing_detector(self): self.probe('unknown')
    def test_nonzero_error(self): self.probe('unknown',detector=('none',2))
    def test_unexpected_output(self): self.probe('unknown',detector=('unknown-error',1))
    def test_inconsistent_detection(self): self.probe('unknown',detector=('none',0))
    def test_empty_output(self): self.probe('unknown',detector=('',1))
    def test_self_hosted(self): self.probe('unknown',detector=('none',1),hosted=False)
    def test_outside_github(self): self.probe('unknown',detector=('none',1),github=False)


class MetadataTests(unittest.TestCase):
    def test_parse_and_shell(self):
        for n in ('env-indocker','input-custom','setup-disk','check-indocker'):
            obj=yaml.safe_load((ACTIONS/n/'action.yml').read_text()); self.assertEqual(obj['runs']['using'],'composite')
            for step in obj['runs']['steps']:
                if 'run' in step:
                    self.assertEqual(step['shell'],'bash'); subprocess.run(['bash','-n'],input=step['run'],text=True,check=True)
                if 'uses' in step: self.assertTrue(step['uses'].endswith('@main'))
        for script in (INPUT,DISK,ACTIONS/'check-indocker/check-indocker.sh'): subprocess.run(['bash','-n',str(script)],check=True)
    def test_order_defaults(self):
        steps=yaml.safe_load((ACTIONS/'env-indocker/action.yml').read_text())['runs']['steps']; ids=[s['id'] for s in steps]
        self.assertEqual(ids,['detect-environment','require-environment','env-custom','fix-docker','apt-openwrt','env-toolchain','disk','prepare-paths']); self.assertEqual(steps[2]['with']['phase'],'load'); self.assertEqual(steps[-1]['with']['phase'],'paths'); self.assertIn("== 'container'",steps[3]['if']); self.assertEqual(steps[6]['with']['path_build'],'${{ env.PATH_build }}'); self.assertFalse(any('/run-sudo@' in s.get('uses','') or '/setup-docker@' in s.get('uses','') for s in steps))
        for key in ('purge_snap','clean_docker_image','clean_runner'): self.assertEqual(steps[5]['with'][key],'false')
        for key in ('gcc_version','gcc_install','gcc_switch','gcc_purge','gcc_aarch64','clang_version','jdk_version'): self.assertEqual(steps[5]['with'][key],'${{ env.'+key+' }}')

def uncertain_failure_test(command):
    def test(self):
        r,c=self.call({'fail':command}); self.assertNotEqual(r.returncode,0); self.assertFalse(self.out.exists()); self.assertFalse(any(x[0] in ('rm','vgremove','umount') for x in c))
    return test
for command in ('losetup','pvcreate','vgcreate','lvcreate'):
    setattr(DiskTests,'test_partial_'+command,uncertain_failure_test(command))

if __name__=='__main__': unittest.main(verbosity=2)
