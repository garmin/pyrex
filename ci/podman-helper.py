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
#
#
# A shim helper for podman that implements a poor man's BuildKit. Creates a new
# temporary Dockerfile with all unnecessary build targets removed to speed up
# build times

import argparse
import os
import re
import string
import subprocess
import sys
import tempfile


class D(dict):
    def __getitem__(self, idx):
        return self.get(idx, '')


def forward():
    os.execvp('podman', ['podman'] + sys.argv[1:])
    sys.exit(1)


def process_targets(cur, targets):
    if cur not in targets:
        return set()

    s = set((cur,))
    for c in targets[cur]:
        s.update(process_targets(c, targets))

    return s


def docker_file_lines(lines, build_args):
    current_target = None

    for l in lines:
        if l.lower().startswith('from'):
            expanded = string.Template(l).substitute(build_args)
            m = re.match(r'FROM\s+(?P<parent>\S+)\s+AS\s+(?P<name>\S+)', expanded, re.IGNORECASE)
            if m is not None:
                current_target = m.group('name')
                yield (l, current_target, 'from', m)
                continue

            m = re.match(r'FROM\s+(?P<parent>\S+)', expanded, re.IGNORECASE)
            if m is not None:
                current_target = None

        if l.lower().startswith('copy'):
            expanded = string.Template(l).substitute(build_args)
            m = re.match(r'COPY\s+--from=(?P<from>\S+)', expanded, re.IGNORECASE)
            if m is not None:
                yield (l, current_target, 'copy', m)
                continue

        yield (l, current_target, '', None)


def main():
    if len(sys.argv) < 2 or sys.argv[1] != 'build':
        forward()

    parser = argparse.ArgumentParser(description='Container build helper')
    parser.add_argument('--build-arg', action='append', default=[],
                        help='name and value of a buildarg')
    parser.add_argument('--file', '-f', default='Dockerfile',
                        help='Docker file')
    parser.add_argument('--target', help='set target build stage to build')

    (args, extra) = parser.parse_known_args(sys.argv[2:])

    if not args.target:
        forward()

    build_args = D()
    for b in args.build_arg:
        name, value = b.split('=', 1)
        build_args[name] = value

    with open(args.file, 'r') as f:
        docker_file = [l.rstrip() for l in f.readlines()]

    # Process docker file for build target dependencies
    targets = {}
    for l, current_target, inst, data in docker_file_lines(docker_file, build_args):
        if inst == 'from':
            targets[current_target] = set((data.group('parent'),))
        elif inst == 'copy':
            targets[current_target].add(data.group('from'))

    needed_targets = process_targets(args.target, targets)

    # Create a new docker file that only contains the necessary build
    # dependencies
    new_file = []
    for l, current_target, _, _ in docker_file_lines(docker_file, build_args):
        if current_target is None or current_target in needed_targets:
            new_file.append(l)
        else:
            new_file.append('')

    with tempfile.NamedTemporaryFile() as t:
        t.write('\n'.join(new_file).encode('utf-8'))
        t.flush()
        return subprocess.call(['podman', 'build', '--target', args.target, '-f', t.name] +
                               ['--build-arg=%s' % arg for arg in args.build_arg] + extra)

    return 0


if __name__ == "__main__":
    sys.exit(main())
