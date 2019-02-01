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

class TestPyrex(unittest.TestCase):
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

    def get_config(self):
        class Config(configparser.RawConfigParser):
            def write_conf(self):
                write_config_helper(self)

        def write_config_helper(conf):
            with open(self.pyrex_conf, 'w') as f:
                conf.write(f)

        config = Config()
        if os.path.exists(self.pyrex_conf):
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

    def assertPyrexHostCommand(self, *args, **kwargs):
        cmd_file = os.path.join(self.thread_dir, 'command')
        with open(cmd_file, 'w') as f:
            f.write(' && '.join(['. ./poky/pyrex-init-build-env'] + list(args)))
        return self.assertSubprocess(['/bin/bash', cmd_file], cwd=PYREX_ROOT, **kwargs)

    def assertPyrexContainerShellCommand(self, *args, **kwargs):
        cmd_file = os.path.join(self.thread_dir, 'container_command')
        with open(cmd_file, 'w') as f:
            f.write(' && '.join(args))
        return self.assertPyrexHostCommand('pyrex-shell %s' % cmd_file, **kwargs)

    def assertPyrexContainerCommand(self, cmd, **kwargs):
        return self.assertPyrexHostCommand('pyrex-run %s' % cmd, **kwargs)

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

    def test_home_mangling(self):
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        temp_home = os.path.join(temp_dir, 'home')
        os.makedirs(os.path.join(temp_home, 'test'))

        env = os.environ.copy()
        env['HOME'] = temp_home

        conf = self.get_config()
        orig_bind = conf['docker']['bind']

        # Test binding by special token
        conf['docker']['bind'] = orig_bind + ' ~/test'
        conf.write_conf()

        self.assertPyrexContainerShellCommand('echo "hello" > /home/pyrex/test/test1.txt', env=env)
        self.assertTrue(os.path.exists(os.path.join(temp_home, 'test', 'test1.txt')))

        # Check that $HOME is correct in the container
        home_file = os.path.join(self.thread_dir, 'home.txt')
        output = self.assertPyrexContainerShellCommand('echo $HOME > %s' % home_file, env=env, capture=True)
        with open(home_file, 'r') as f:
            self.assertEqual(f.read().rstrip(), conf['pyrex']['home'])

        # Test that tildas not expanded if they are not at the beginning of the path
        tilda_test_dir = os.path.join(temp_dir, '~')
        os.makedirs(tilda_test_dir)

        conf['docker']['bind'] = orig_bind + ' ' + tilda_test_dir
        conf.write_conf()

        self.assertPyrexContainerShellCommand('echo "hello" > %s/test2.txt' % tilda_test_dir, env=env)
        self.assertTrue(os.path.exists(os.path.join(tilda_test_dir, 'test2.txt')))

if __name__ == "__main__":
    unittest.main()
