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
import signal
import sys

if __name__ == "__main__":
    # Block the SIGTSTP signal. We haven't figured out how to do proper job
    # control inside of docker yet, and if the user accidentally presses CTRL+Z
    # is will freeze the console without actually stopping the build.  To
    # prevent this, block SIGTSTP in all child processes. This results in
    # CTRL+Z doing nothing.
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGTSTP])

    os.execvp(sys.argv[1], sys.argv[1:])
    sys.exit(1)

