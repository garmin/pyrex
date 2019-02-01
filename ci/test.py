#! /usr/bin/env python3
#
# Copyright 2019 Garmin Ltd. or its subsidiaries
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import configparser
import grp
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

PYREX_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(PYREX_ROOT)
import pyrex

TEST_IMAGE_ENV_VAR = 'TEST_IMAGE'

class PyrexTest(unittest.TestCase):
    def setUp(self):
        self.build_dir = os.path.abspath(os.path.join(PYREX_ROOT, 'build'))

        def cleanup_build():
            if os.path.isdir(self.build_dir):
                shutil.rmtree(self.build_dir)

        cleanup_build()
        os.makedirs(self.build_dir)
        self.addCleanup(cleanup_build)

        conf_dir = os.path.join(self.build_dir, 'conf')
        os.makedirs(conf_dir)

        self.pyrex_conf = os.path.join(conf_dir, 'pyrex.ini')

        def cleanup_env():
            os.environ = self.old_environ

        # OE requires that "python" be python2, not python3
        self.bin_dir = os.path.join(self.build_dir, 'bin')
        self.old_environ = os.environ.copy()
        os.makedirs(self.bin_dir)
        os.symlink('/usr/bin/python2', os.path.join(self.bin_dir, 'python'))
        os.environ['PATH'] = self.bin_dir + ':' + os.environ['PATH']
        os.environ['PYREX_DOCKER_BUILD_QUIET'] = '0'
        self.addCleanup(cleanup_env)

        self.thread_dir = os.path.join(self.build_dir, "%d.%d" % (os.getpid(), threading.get_ident()))
        os.makedirs(self.thread_dir)

        self.test_image = os.environ.get(TEST_IMAGE_ENV_VAR)
        if self.test_image:
            conf = self.get_config()
            conf['config']['dockerimage'] = self.test_image
            conf.write_conf()

    def get_config(self, defaults=False):
        class Config(configparser.RawConfigParser):
            def write_conf(self):
                write_config_helper(self)

        def write_config_helper(conf):
            with open(self.pyrex_conf, 'w') as f:
                conf.write(f)

        config = Config()
        if os.path.exists(self.pyrex_conf) and not defaults:
            config.read(self.pyrex_conf)
        else:
            config.read_string(pyrex.read_default_config(True))
        return config

    def assertSubprocess(self, *args, capture=False, returncode=0, **kwargs):
        if capture:
            try:
                output = subprocess.check_output(*args, stderr=subprocess.STDOUT, **kwargs)
            except subprocess.CalledProcessError as e:
                ret = e.returncode
                output = e.output
            else:
                ret = 0

            self.assertEqual(ret, returncode, msg='%s: %s' % (' '.join(*args), output.decode('utf-8')))
            return output
        else:
            with subprocess.Popen(*args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs) as proc:
                while True:
                    out = proc.stdout.readline().decode('utf-8')
                    if not out and proc.poll() is not None:
                        break

                    if out:
                        sys.stdout.write(out)

                ret = proc.poll()

            self.assertEqual(ret, returncode, msg='%s failed')
            return None

    def assertPyrexHostCommand(self, *args, quiet_init=False, **kwargs):
        cmd_file = os.path.join(self.thread_dir, 'command')
        commands = []
        commands.append('. ./poky/pyrex-init-build-env%s' % ('', ' > /dev/null')[quiet_init])
        commands.extend(list(args))
        with open(cmd_file, 'w') as f:
            f.write(' && '.join(commands))
        return self.assertSubprocess(['/bin/bash', cmd_file], cwd=PYREX_ROOT, **kwargs)

    def assertPyrexContainerShellCommand(self, *args, **kwargs):
        cmd_file = os.path.join(self.thread_dir, 'container_command')
        with open(cmd_file, 'w') as f:
            f.write(' && '.join(args))
        return self.assertPyrexHostCommand('pyrex-shell %s' % cmd_file, **kwargs)

    def assertPyrexContainerCommand(self, cmd, **kwargs):
        return self.assertPyrexHostCommand('pyrex-run %s' % cmd, **kwargs)

class PyrexCore(PyrexTest):
    def test_init(self):
        self.assertPyrexHostCommand('true')

    def test_bitbake_parse(self):
        self.assertPyrexHostCommand('bitbake -p')

    def test_pyrex_shell(self):
        self.assertPyrexContainerShellCommand('exit 3', returncode=3)

    def test_pyrex_run(self):
        self.assertPyrexContainerCommand('/bin/false', returncode=1)

    def test_disable_pyrex(self):
        # Capture our cgroups
        with open('/proc/self/cgroup', 'r') as f:
            cgroup = f.read()

        pyrex_cgroup_file = os.path.join(self.thread_dir, 'pyrex_cgroup')

        # Capture cgroups when pyrex is enabled
        self.assertPyrexContainerShellCommand('cat /proc/self/cgroup > %s' % pyrex_cgroup_file)
        with open(pyrex_cgroup_file, 'r') as f:
            pyrex_cgroup = f.read()
        self.assertNotEqual(cgroup, pyrex_cgroup)

        env = os.environ.copy()
        env['PYREX_DOCKER'] = '0'
        self.assertPyrexContainerShellCommand('cat /proc/self/cgroup > %s' % pyrex_cgroup_file, env=env)
        with open(pyrex_cgroup_file, 'r') as f:
            pyrex_cgroup = f.read()
        self.assertEqual(cgroup, pyrex_cgroup)

    def test_quiet_build(self):
        env = os.environ.copy()
        env['PYREX_DOCKER_BUILD_QUIET'] = '1'
        self.assertPyrexHostCommand('true', env=env)

    def test_no_docker_build(self):
        # Prevent docker from working
        os.symlink('/bin/false', os.path.join(self.bin_dir, 'docker'))

        # Docker will fail if invoked here
        env = os.environ.copy()
        env['PYREX_DOCKER'] = '0'
        self.assertPyrexHostCommand('true', env=env)

        # Verify that pyrex won't allow you to try and use docker later
        output = self.assertPyrexHostCommand('PYREX_DOCKER=1 bitbake', returncode=1, capture=True, env=env).decode('utf-8')
        self.assertIn('Docker was not enabled when the environment was setup', output)

    def test_bad_docker(self):
        # Prevent docker from working
        os.symlink('/bin/false', os.path.join(self.bin_dir, 'docker'))

        # Verify that attempting to run build pyrex without docker shows the
        # installation instructions
        output = self.assertPyrexHostCommand('true', returncode=1, capture=True).decode('utf-8')
        self.assertIn('Unable to run', output)

    def test_ownership(self):
        # Test that files created in docker are the same UID/GID as the user
        # running outside

        test_file = os.path.join(self.thread_dir, 'ownertest')
        if os.path.exists(test_file):
            os.unlink(test_file)

        self.assertPyrexContainerShellCommand('echo "$(id -un):$(id -gn)" > %s' % test_file)

        s = os.stat(test_file)

        self.assertEqual(s.st_uid, os.getuid())
        self.assertEqual(s.st_gid, os.getgid())

        with open(test_file, 'r') as f:
            (username, groupname) = f.read().rstrip().split(':')

        self.assertEqual(username, pwd.getpwuid(os.getuid()).pw_name)
        self.assertEqual(groupname, grp.getgrgid(os.getgid()).gr_name)

    def test_owner_env(self):
        # This test is primarily designed to ensure that everything is passed
        # correctly through 'pyrex run'

        conf = self.get_config()

        # Note: These config variables are intended for testing use only
        conf['run']['uid'] = '1337'
        conf['run']['gid'] = '7331'
        conf['run']['username'] = 'theuser'
        conf['run']['groupname'] = 'thegroup'
        conf['run']['initcommand'] = ''
        conf.write_conf()

        # Make a fifo that the container can write into. We can't just write a
        # file because it won't be owned by running user and thus can't be
        # cleaned up
        old_umask = os.umask(0)
        self.addCleanup(os.umask, old_umask)

        fifo = os.path.join(self.thread_dir, 'fifo')
        os.mkfifo(fifo)
        self.addCleanup(os.remove, fifo)

        os.umask(old_umask)

        output = []

        def read_fifo():
            nonlocal output
            with open(fifo, 'r') as f:
                output = f.readline().rstrip().split(':')

        thread = threading.Thread(target=read_fifo)
        thread.start()
        try:
            self.assertPyrexContainerShellCommand('echo "$(id -u):$(id -g):$(id -un):$(id -gn):$USER:$GROUP" > %s' % fifo)
        finally:
            thread.join()

        self.assertEqual(output[0], '1337')
        self.assertEqual(output[1], '7331')
        self.assertEqual(output[2], 'theuser')
        self.assertEqual(output[3], 'thegroup')
        self.assertEqual(output[4], 'theuser')
        self.assertEqual(output[5], 'thegroup')

    def test_duplicate_binds(self):
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conf = self.get_config()
        conf['run']['bind'] += ' %s %s' % (temp_dir, temp_dir)
        conf.write_conf()

        self.assertPyrexContainerShellCommand('true')

    def test_bad_confversion(self):
        # Verify that a bad config is an error
        conf = self.get_config()
        conf['config']['confversion'] = '0'
        conf.write_conf()

        self.assertPyrexHostCommand('true', returncode=1)

    def test_conftemplate_ignored(self):
        # Write out a template with a bad version in an alternate location. It
        # should be ignored
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, 'pyrex.ini.sample')

        conf = self.get_config(defaults=True)
        conf['config']['confversion'] = '0'
        with open(conftemplate, 'w') as f:
            conf.write(f)

        self.assertPyrexHostCommand('true')

    def test_conf_upgrade(self):
        conf = self.get_config()
        del conf['config']['confversion']
        conf.write_conf()

        # Write out a template in an alternate location. It will be respected
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, 'pyrex.ini.sample')

        conf = self.get_config(defaults=True)
        if self.test_image:
            conf['config']['pyreximage'] = self.test_image
        with open(conftemplate, 'w') as f:
            conf.write(f)

        env = os.environ.copy()
        env['PYREXCONFTEMPLATE'] = conftemplate

        self.assertPyrexHostCommand('true', env=env)

    def test_bad_conf_upgrade(self):
        # Write out a template in an alternate location, but it also fails to
        # have a confversion
        conf = self.get_config()
        del conf['config']['confversion']
        conf.write_conf()

        # Write out a template in an alternate location. It will be respected
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, 'pyrex.ini.sample')

        conf = self.get_config(defaults=True)
        if self.test_image:
            conf['config']['pyreximage'] = self.test_image
        del conf['config']['confversion']
        with open(conftemplate, 'w') as f:
            conf.write(f)

        env = os.environ.copy()
        env['PYREXCONFTEMPLATE'] = conftemplate

        self.assertPyrexHostCommand('true', returncode=1, env=env)

    def test_local_build(self):
        # Run any command to build the images locally
        self.assertPyrexHostCommand('true')

        conf = self.get_config()

        # Trying to build with an invalid registry should fail
        conf['config']['registry'] = 'does.not.exist.invalid'
        conf.write_conf()
        self.assertPyrexHostCommand('true', returncode=1)

        # Disable building locally any try again (from the previously cached build)
        conf['config']['buildlocal'] = '0'
        conf.write_conf()

        self.assertPyrexHostCommand('true')


class TestImage(PyrexTest):
    def test_tini(self):
        self.assertPyrexContainerCommand('tini --version')

    def test_icecc(self):
        self.assertPyrexContainerCommand('icecc --version')

    def test_guest_image(self):
        # This test makes sure that the image being tested is the image we
        # actually expect to be testing
        if not self.test_image:
            self.skipTest("%s not defined" % TEST_IMAGE_ENV_VAR)

        dist_id_str = self.assertPyrexContainerCommand('lsb_release -i', quiet_init=True, capture=True).decode('utf-8').rstrip()
        release_str = self.assertPyrexContainerCommand('lsb_release -r', quiet_init=True, capture=True).decode('utf-8').rstrip()

        self.assertRegex(dist_id_str.lower(), r'^distributor id:\s+' + re.escape(self.test_image.split('-', 1)[0]))
        self.assertRegex(release_str.lower(), r'^release:\s+' + re.escape(self.test_image.split('-', 1)[1]))

if __name__ == "__main__":
    unittest.main()
