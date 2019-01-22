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

import glob
import logging
import os
import re
import signal
import sys
import time

# These Linux process states are considered "already dead" and will not cause
# the script to wait
ALREADY_DEAD_STATES = (
        'Z', # Zombie
        'X', # Dead (from Linux 2.6.0 onward)
        'x', # Dead (Linux 2.6.33 to 3.13 only)
        )

EXIT_WAIT_PHASES = 2

# Number of seconds after which the user will be warned and signals will be
# enabled (unmasked). Enabling the signals allows the user to kill the
# container without having to wait any longer
SIGNAL_ENABLE_WAIT_TIME = 10

# Wait 1 seconds for normal exit and forever for sigterm
WAIT_FOREVER_DEFAULT = [0.5, -1]

# Container shutdown has the following phases:
#  1) Wait for a defined amount of time for processes to exit on their own
#  2) Send all running processes SIGTERM and wait a defined amount of time for
#     them to exit
#  3) Exit the container (which will SIGKILL all processes)
#
# The default wait time can be expressed as:
#  1) A single float value in seconds. The two wait phases of shutdown will
#     be split evenly across this time so that the total time will be
#     approximately as long as specified
#  2) A list of two float values in seconds separated by commas. Each value
#     specifies the amount of time that phase will wait. A negative number for
#     any field means "wait forever"
#  3) A single negative number. This will choose default values for the first
#     wait phase and then wait forever after SIGTERM
#
# Regardless of the wait mode the user will be warned if it waits more than 10
# seconds (SIGNAL_ENABLE_WAIT_TIME) in any phase and the SIGINT, SIGTERM, and
# SIGQUIT signal handlers will be re-enabled. Any of these signals will cause
# script to stop waiting, which will terminate the container.

# By default, wait forever
DEFAULT_WAIT_TIME = '-1'

# Signals which will interrupt cleanup if it is waiting forever
INTERRUPT_SIGNALS = (
    signal.SIGINT,
    signal.SIGQUIT,
    signal.SIGTERM,
    )

def pid_str_list(s):
    return '  ' + '\n  '.join(s[key] for key in sorted(s.keys()))

signals_enabled = False
keep_waiting = True
keep_waiting_notified = False

def stop_process_waiting(signum, frame):
    global keep_waiting
    keep_waiting = False
    # Note: Can't use logging in a signal handler. Uncomment this to debug
    #print("Got signal %d" % signum)

def wait_for_processes(sig, max_wait):
    global keep_waiting
    global keep_waiting_notified
    global signals_enabled

    my_pid = os.getpid()

    start_time = time.monotonic()

    killed_processes = set()

    logging.debug('Waiting %f seconds', max_wait)

    sleep_time = 0.01

    while True:
        still_running = dict()

        stat_files = [s for s in glob.glob("/proc/*/stat") if re.match(r'^/proc/[0-9]+/stat$', s)]

        logging.debug("Found PID stat files: %s", ' '.join(stat_files))

        for p in stat_files:
            try:
                with open(p, "r") as f:
                    data = f.read()

                if not data:
                    continue

                # Strip out the command name (which might contain spaces), then split the rest
                data = re.sub(r'\(.*\)', '', data).split()

                pid = int(data[0])
                state = data[1]

                command = ''
                try:
                    with open('/proc/%d/cmdline' % pid, 'rb') as f:
                        command = f.read()
                    command = command.replace(b'\x00', b' ').decode('utf-8')
                except IOError:
                    pass

                description = "PID %d (%s): %s" % (pid, state, command)

                logging.debug("Found %s", description)

                if not state in ALREADY_DEAD_STATES and pid != my_pid and pid != 1:
                    if not pid in killed_processes and sig is not None:
                        logging.info("Killing %s", description)
                        os.kill(pid, sig)
                        killed_processes.add(pid)

                    still_running[pid] = description
            except IOError:
                pass

        # Check if the process should wait. The check is done here so that the
        # list of running processes is fetched at least once and can be
        # returned
        if not still_running:
            logging.debug('No more processes running')
            return still_running

        if max_wait >= 0 and time.monotonic() > start_time + max_wait:
            logging.debug('Wait timed out')
            return still_running

        if not keep_waiting:
            if not keep_waiting_notified:
                logging.warning('Waiting interrupted')
                keep_waiting_notified = True
            return still_running

        if not signals_enabled and time.monotonic() > start_time + SIGNAL_ENABLE_WAIT_TIME:
            logging.warning('Waiting for %d processes to exit...', len(still_running))

            for s in INTERRUPT_SIGNALS:
                signal.signal(s, stop_process_waiting)

            signal.pthread_sigmask(signal.SIG_UNBLOCK, INTERRUPT_SIGNALS)
            signals_enabled = True

        logging.debug('Waiting for %d processes to exit\n%s', len(still_running), pid_str_list(still_running))

        # If we have been waiting longer than 2 seconds, then throttle down the
        # waits to twice a second
        if time.monotonic() > start_time + 2:
            sleep_time = 0.5

        time.sleep(sleep_time)

def main():
    # Setup logging. The child stdout may need to be parsable, so the logging
    # goes to stderr by default
    log_file = os.environ.get('PYREX_CLEANUP_LOG_FILE', '-')
    log_level = os.environ.get('PYREX_CLEANUP_LOG_LEVEL', 'WARNING')

    fmt = '%(asctime)-15s %(levelname)s: %(message)s'

    if log_file == '-':
        logging.basicConfig(stream=sys.stderr, format=fmt, level=log_level)
    else:
        logging.basicConfig(filename=log_file, format=fmt, level=log_level)

    # Set exit wait times
    exit_wait = os.environ.get('PYREX_CLEANUP_EXIT_WAIT', DEFAULT_WAIT_TIME)

    try:
        exit_wait_times = [float(w) for w in exit_wait.split(',')]
    except ValueError:
        logging.error('Invalid value for PYREX_CLEANUP_EXIT_WAIT: %s', exit_wait)
        return 1

    if len(exit_wait_times) == 1:
        if exit_wait_times[0] < 0:
            exit_wait_times = WAIT_FOREVER_DEFAULT
        else:
            # Divide wait time over all phases
            exit_wait_times = [exit_wait_times[0] / EXIT_WAIT_PHASES] * EXIT_WAIT_PHASES

    if len(exit_wait_times) != EXIT_WAIT_PHASES:
        logging.error('Invalid value for PYREX_CLEANUP_EXIT_WAIT: %s', '', ','.join(exit_wait_times))
        return 1

    logging.debug('Wait times are %s', ','.join(str(w) for w in exit_wait_times))

    # Wait for processes to exit naturally
    logging.info("Waiting for processes to exit")
    still_running = wait_for_processes(None, exit_wait_times[0])

    if still_running:
        logging.info("Sending all processes SIGTERM")
        # Give all processes SIGTERM and wait for them to terminate
        still_running = wait_for_processes(signal.SIGTERM, exit_wait_times[1])

    if still_running:
        logging.warning("%d processes were left running!\n%s", len(still_running), pid_str_list(still_running))

    # Pass the previous child exit code on to tini
    return int(sys.argv[1])

if __name__ == "__main__":
    sys.exit(main())
