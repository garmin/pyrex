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

import os
import shutil
import subprocess
import unittest
import threading
import sys

PYREX_ROOT = os.path.join(os.path.dirname(__file__), '..')

class TestPyrex(unittest.TestCase):
    def setUp(self):
        self.build_dir = os.path.abspath(os.path.join(PYREX_ROOT, 'build'))

        def cleanup_build():
            if os.path.isdir(self.build_dir):
                shutil.rmtree(self.build_dir)

        cleanup_build()
        os.makedirs(self.build_dir)
        self.addCleanup(cleanup_build)

        def cleanup_env():
            os.environ = self.old_environ

        # OE requires that "python" be python2, not python3
        bin_dir = os.path.join(self.build_dir, 'bin')
        self.old_environ = os.environ.copy()
        os.makedirs(bin_dir)
        os.symlink('/usr/bin/python2', os.path.join(bin_dir, 'python'))
        os.environ['PATH'] = bin_dir + ':' + os.environ['PATH']
        os.environ['PYREX_DOCKER_BUILD_QUIET'] = '0'
        self.addCleanup(cleanup_env)

        self.thread_dir = os.path.join(self.build_dir, "%d.%d" % (os.getpid(), threading.get_ident()))
        os.makedirs(self.thread_dir)

    def assertSubprocess(self, *args, returncode=0, **kwargs):
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

    def assertPyrexCommand(self, *args, **kwargs):
        cmd_file = os.path.join(self.thread_dir, 'command')
        with open(cmd_file, 'w') as f:
            f.write(' && '.join(['. ./poky/pyrex-init-build-env'] + list(args)))
        return self.assertSubprocess(['/bin/bash', cmd_file], cwd=PYREX_ROOT, **kwargs)

    def test_init(self):
        self.assertPyrexCommand('true')

    def test_bitbake_parse(self):
        self.assertPyrexCommand('bitbake -p')

    def test_pyrex_shell(self):
        self.assertPyrexCommand('pyrex-shell -c "exit 3"', returncode=3)

    def test_pyrex_run(self):
        self.assertPyrexCommand('pyrex-run /bin/false', returncode=1)

    def test_disable_pyrex(self):
        # Capture our cgroups
        with open('/proc/self/cgroup', 'r') as f:
            cgroup = f.read()

        pyrex_cgroup_file = os.path.join(self.thread_dir, 'pyrex_cgroup')

        # Capture cgroups when pyrex is enabled
        self.assertPyrexCommand('pyrex-shell -c "cat /proc/self/cgroup > %s"' % pyrex_cgroup_file)
        with open(pyrex_cgroup_file, 'r') as f:
            pyrex_cgroup = f.read()
        self.assertNotEqual(cgroup, pyrex_cgroup)

        env = os.environ.copy()
        env['PYREX_DOCKER'] = '0'
        self.assertPyrexCommand('pyrex-shell -c "cat /proc/self/cgroup > %s"' % pyrex_cgroup_file, env=env)
        with open(pyrex_cgroup_file, 'r') as f:
            pyrex_cgroup = f.read()
        self.assertEqual(cgroup, pyrex_cgroup)

    def test_quiet_build(self):
        env = os.environ.copy()
        env['PYREX_DOCKER_BUILD_QUIET'] = '1'
        self.assertPyrexCommand('true', env=env)

if __name__ == "__main__":
    unittest.main()
