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

PYREX_ROOT = os.path.join(os.path.dirname(__file__), '..')

class TestPyrex(unittest.TestCase):
    def setUp(self):
        build_dir = os.path.join(PYREX_ROOT, 'build')

        def cleanup_build():
            if os.path.isdir(build_dir):
                shutil.rmtree(build_dir)

        cleanup_build()
        os.makedirs(build_dir)
        self.addCleanup(cleanup_build)


        def cleanup_env():
            os.environ = self.old_environ

        bin_dir = os.path.abspath(os.path.join(build_dir, 'bin'))
        self.old_environ = os.environ.copy()
        os.makedirs(bin_dir)
        os.symlink('/usr/bin/python2', os.path.join(bin_dir, 'python'))
        os.environ['PATH'] = bin_dir + ':' + os.environ['PATH']
        self.addCleanup(cleanup_env)

    def assertSubprocess(self, *args, returncode=0, **kwargs):
        try:
            output = subprocess.check_output(*args, stderr=subprocess.STDOUT, **kwargs)
        except subprocess.CalledProcessError as e:
            ret = e.returncode
            output = e.output
        else:
            ret = 0

        self.assertEqual(ret, returncode, msg='%s: %s' % (' '.join(*args), output.decode('utf-8')))

    def test_init(self):
        self.assertSubprocess(['/bin/bash', '-c', '. ../poky/pyrex-init-build-env && true'], cwd=os.path.join(PYREX_ROOT, 'build'))

if __name__ == "__main__":
    unittest.main()
