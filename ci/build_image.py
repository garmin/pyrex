#! /usr/bin/env python3
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

import argparse
import subprocess
import sys
import os

THIS_DIR = os.path.dirname(__file__)


def main():
    parser = argparse.ArgumentParser(description='Build container image')
    parser.add_argument('image', help='Pyrex image to build')
    parser.add_argument('--provider', choices=('docker', 'podman'), default='docker',
                        help='Specify which tool should be used to build the images')
    parser.add_argument('--quiet', action='store_true',
                        help='Build quietly')

    args = parser.parse_args()

    (_, _, image_type) = args.image.split('-')

    this_dir = os.path.abspath(os.path.dirname(__file__))
    docker_dir = os.path.join(this_dir, '..', 'docker')
    docker_file = os.path.join(docker_dir, 'Dockerfile')

    helper = os.path.join(THIS_DIR, '%s-helper.py' % args.provider)
    if os.path.exists(helper):
        print("Invoking %s as %s" % (helper, args.provider))
        provider = helper
    else:
        provider = args.provider

    docker_args = [provider, 'build',
                   '-t', 'garminpyrex/%s:ci-test' % args.image,
                   '-f', docker_file,
                   '--network=host',
                   '--build-arg', 'PYREX_BASE=%s' % args.image,
                   docker_dir,
                   '--target', 'pyrex-%s' % image_type
                   ]

    if args.quiet:
        p = subprocess.Popen(docker_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while True:
            try:
                out, err = p.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                sys.stdout.write('.')
                sys.stdout.flush()
        sys.stdout.write('\n')

        if p.returncode:
            sys.stdout.write(out.decode('utf-8'))

        return p.returncode
    else:
        subprocess.check_call(docker_args)


if __name__ == "__main__":
    sys.exit(main())
