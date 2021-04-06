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

import grp
import os
import pwd
import sys
import subprocess
import signal


def get_var(name):
    if name in os.environ:
        val = os.environ[name]
        if not val:
            sys.stderr.write('"%s" is empty\n' % name)
            sys.exit(1)
        return val

    sys.stderr.write('"%s" is missing from the environment\n' % name)
    sys.exit(1)


def main():
    # Block the SIGTSTP signal. We haven't figured out how to do proper job
    # control inside of the container yet, and if the user accidentally presses
    # CTRL+Z is will freeze the console without actually stopping the build.
    # To prevent this, block SIGTSTP in all child processes. This results in
    # CTRL+Z doing nothing.
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGTSTP])

    # Check TERM
    if "TERM" in os.environ:
        r = subprocess.call(
            ["/usr/bin/infocmp", os.environ["TERM"]],
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
        if r != 0:
            sys.stderr.write(
                '$TERM has an unrecognized value of "%s". The interactive terminal may not behave appropriately\n'
                % os.environ["TERM"]
            )

    uid = int(get_var("PYREX_UID"))
    user = get_var("PYREX_USER")
    groups = []
    for s in get_var("PYREX_GROUPS").split():
        gid, name = s.split(":")
        groups.append((int(gid), name))

    primarygid, primarygroup = groups[0]

    home = get_var("PYREX_HOME")

    check_file = "/var/run/pyrex-%d-%d" % (uid, primarygid)
    if not os.path.exists(check_file):
        with open(check_file, "w") as f:
            f.write("%d %d %s %s\n" % (uid, primarygid, user, primarygroup))

            # Remove all non-root users and groups so that there are no conflicts
            # when the user is added.
            for p in pwd.getpwall():

                if p[2] == 0:
                    continue

                subprocess.check_call(
                    [
                        "userdel",
                        p[0],
                    ],
                )

            for g in grp.getgrall():

                if g[2] == 0:
                    continue

                subprocess.check_call(
                    ["groupdel", g[0]],
                )

            # Create user and groups
            for (gid, group) in groups:
                if gid == 0:
                    continue
                subprocess.check_call(
                    ["groupadd", "--gid", "%d" % gid, group], stdout=f
                )

            subprocess.check_call(
                [
                    "useradd",
                    "--non-unique",
                    "--uid",
                    "%d" % uid,
                    "--gid",
                    "%d" % primarygid,
                    "--groups",
                    ",".join(str(g[0]) for g in groups),
                    "--home",
                    home,
                    "--no-create-home",
                    "--shell",
                    "/bin/sh",
                    user,
                ],
                stdout=f,
            )

        try:
            os.makedirs(home, 0o755)
        except OSError:
            pass

        # Be a little paranoid about this. Only coerce the home directory if
        # it's target mount is is the root directory (which should only be true
        # if it hasn't be bind mounted in the container)
        target = (
            subprocess.check_output(
                ["findmnt", "-f", "-n", "-o", "TARGET", "--target", home]
            )
            .decode("utf-8")
            .strip()
        )

        if target == "/":
            os.chown(home, uid, primarygid)

            try:
                screenrc = os.path.join(home, ".screenrc")

                with open(screenrc, "x") as f:
                    f.write("defbce on\n")

                os.chown(screenrc, uid, primarygid)
            except FileExistsError:
                pass

        # Allow user to execute any commands under sudo (helps with debugging)
        with open("/etc/sudoers", "a") as f:
            f.write("%s ALL=(ALL) NOPASSWD: ALL\n" % user)

    # Setup environment
    os.environ["USER"] = user
    os.environ["GROUP"] = primarygroup
    os.environ["HOME"] = home

    # If a tty is attached, change it over to be owned by the new user. This is
    # required for terminal managers (like screen) to function
    try:
        os.chown(os.ttyname(0), uid, -1)
    except OSError:
        pass

    # Execute any startup executables.
    if os.environ.get("PYREX_SKIP_STARTUP", "0") == "0":
        for exe in os.listdir("/usr/libexec/pyrex/startup.d"):
            path = os.path.join("/usr/libexec/pyrex/startup.d", exe)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                try:
                    subprocess.check_call([path])
                except subprocess.CalledProcessError as e:
                    sys.stderr.write("%s exited with %d\n" % (path, e.returncode))
                    sys.exit(e.returncode)

    # Invoke setpriv to drop root privileges.
    os.execlp(
        "setpriv",
        "setpriv",
        "--inh-caps=-all",  # Drop all root capabilities
        "--reuid",
        "%d" % uid,
        "--regid",
        "%d" % primarygid,
        "--groups",
        ",".join(str(g[0]) for g in groups),
        *sys.argv[1:]
    )

    # If we get here, it is an error
    sys.syderr.write("Unable to exec setpriv\n")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
