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
# A shim helper for podman that does actual image builds using docker, then
# imports the files into podman. This is much faster (with BuildKit), more
# accurate for testing (since the docker built images are the ones released),
# and works (since building images with podman on Travis doesn't actually work)

import argparse
import os
import subprocess
import sys


def forward():
    os.execvp("podman", ["podman"] + sys.argv[1:])
    sys.exit(1)


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "build":
        forward()

    parser = argparse.ArgumentParser(description="Container build helper")
    parser.add_argument("-t", "--tag", help="Image tag", required=True)

    (args, extra_args) = parser.parse_known_args(sys.argv[2:])

    try:
        subprocess.check_call(["docker", "build", "-t", args.tag] + extra_args)
        subprocess.check_call(["podman", "pull", "docker-daemon:%s" % args.tag])
    except subprocess.CalledProcessError as e:
        return e.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
