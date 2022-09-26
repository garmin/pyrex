#! /usr/bin/env python3
#
# Copyright 2019-2020 Garmin Ltd. or its subsidiaries
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
import pty
import pwd
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import time

PYREX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PYREX_ROOT)
import pyrex  # NOQA

TEST_PREBUILT_TAG_ENV_VAR = "TEST_PREBUILT_TAG"


def skipIfPrebuilt(func):
    def wrapper(self, *args, **kwargs):
        if os.environ.get(TEST_PREBUILT_TAG_ENV_VAR, ""):
            self.skipTest("Test does not apply to prebuilt images")
        return func(self, *args, **kwargs)

    return wrapper


def skipIfOS(os, version):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            (image_os, image_version, _) = self.test_image.split("-")
            if image_os == os and image_version == version:
                self.skipTest("Test does not apply to %s-%s" % (os, version))
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


built_images = set()


class PyrexTest(object):
    @property
    def pokyroot(self):
        major, minor = self.pokyver
        return os.path.join(PYREX_ROOT, "poky", f"{major}.{minor}")

    def setUp(self):
        self.build_dir = os.path.join(PYREX_ROOT, "build", "%d" % os.getpid())

        def cleanup_build():
            if os.path.isdir(self.build_dir):
                shutil.rmtree(self.build_dir)

        self.addCleanup(cleanup_build)
        cleanup_build()
        os.makedirs(self.build_dir)

        self.pyrex_conf = os.path.join(self.build_dir, "pyrex.ini")
        conf = self.get_config()
        conf.write_conf()

        if not os.environ.get(TEST_PREBUILT_TAG_ENV_VAR, ""):
            self.prebuild_image()

        def cleanup_env():
            os.environ.clear()
            os.environ.update(self.old_environ)

        # OE requires that "python" be python2, not python3
        self.bin_dir = os.path.join(self.build_dir, "bin")
        self.old_environ = os.environ.copy()
        os.makedirs(self.bin_dir)
        os.symlink("/usr/bin/python2", os.path.join(self.bin_dir, "python"))
        os.environ["PATH"] = self.bin_dir + ":" + os.environ["PATH"]
        os.environ["PYREX_BUILD_QUIET"] = "0"
        os.environ["PYREX_OEINIT"] = os.path.join(self.pokyroot, "oe-init-build-env")
        os.environ["PYREX_CONFIG_BIND"] = PYREX_ROOT
        for var in (
            "SSH_AUTH_SOCK",
            "BB_ENV_EXTRAWHITE",
            "BB_ENV_PASSTHROUGH_ADDITIONS",
        ):
            if var in os.environ:
                del os.environ[var]

        self.thread_dir = os.path.join(
            self.build_dir, "%d.%d" % (os.getpid(), threading.get_ident())
        )
        os.makedirs(self.thread_dir)

    def prebuild_image(self):
        global built_images
        image = ":".join((self.test_image, self.provider))
        if image not in built_images:
            self.assertSubprocess(
                [
                    os.path.join(PYREX_ROOT, "ci", "build_image.py"),
                    "--provider",
                    self.provider,
                    self.test_image,
                ]
            )
            built_images.add(image)

    def get_config(self, *, defaults=False):
        class Config(configparser.RawConfigParser):
            def write_conf(self):
                write_config_helper(self)

        def write_config_helper(conf):
            with open(self.pyrex_conf, "w") as f:
                conf.write(f)

        config = Config()
        if os.path.exists(self.pyrex_conf) and not defaults:
            config.read(self.pyrex_conf)
        else:
            config.read_string(pyrex.read_default_config(True))

            # Setup the config suitable for testing
            config["config"]["image"] = self.test_image
            config["config"]["engine"] = self.provider
            config["config"]["buildlocal"] = "0"
            tag = os.environ.get(TEST_PREBUILT_TAG_ENV_VAR, "")
            if tag:
                config["config"]["pyrextag"] = tag
            else:
                config["config"]["pyrextag"] = "ci-test"
                config["config"]["registry"] = ""

            config["run"]["bind"] += " " + self.build_dir
            config["imagebuild"]["buildcommand"] = "%s --provider=%s %s" % (
                os.path.join(PYREX_ROOT, "ci", "build_image.py"),
                self.provider,
                self.test_image,
            )

        return config

    def assertSubprocess(
        self, *args, pretty_command=None, capture=False, returncode=0, **kwargs
    ):
        if capture:
            try:
                output = subprocess.check_output(
                    *args, stderr=subprocess.STDOUT, **kwargs
                )
            except subprocess.CalledProcessError as e:
                ret = e.returncode
                output = e.output
            else:
                ret = 0

            self.assertEqual(
                ret,
                returncode,
                msg="%s: %s"
                % (pretty_command or " ".join(*args), output.decode("utf-8")),
            )
            return output.decode("utf-8").rstrip()
        else:
            with subprocess.Popen(
                *args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs
            ) as proc:
                while True:
                    out = proc.stdout.readline().decode("utf-8")
                    if not out and proc.poll() is not None:
                        break

                    if out:
                        sys.stdout.write(out)

                ret = proc.poll()

            self.assertEqual(
                ret, returncode, msg="%s failed" % (pretty_command or " ".join(*args))
            )
            return None

    def _write_host_command(
        self,
        args,
        *,
        quiet_init=False,
        cwd=PYREX_ROOT,
        builddir=None,
        bitbakedir="",
        init_env={},
    ):
        if builddir is None:
            builddir = self.build_dir

        command = ['export %s="%s"\n' % (k, v) for k, v in init_env.items()]

        command.extend(
            [
                "PYREXCONFFILE=%s\n" % self.pyrex_conf,
                ". %s/pyrex-init-build-env%s %s %s && "
                % (
                    self.pokyroot,
                    " > /dev/null 2>&1" if quiet_init else "",
                    builddir,
                    bitbakedir,
                ),
                "(",
                " && ".join(list(args)),
                ")",
            ]
        )

        command = "".join(command)

        cmd_file = os.path.join(self.thread_dir, "command")
        with open(cmd_file, "w") as f:
            f.write(command)
        return cmd_file, command

    def _write_container_command(self, args):
        cmd_file = os.path.join(self.thread_dir, "container_command")
        with open(cmd_file, "w") as f:
            f.write(" && ".join(args))
        return cmd_file

    def assertPyrexHostCommand(
        self,
        *args,
        quiet_init=False,
        cwd=PYREX_ROOT,
        builddir=None,
        bitbakedir="",
        init_env={},
        **kwargs,
    ):
        cmd_file, command = self._write_host_command(
            args,
            quiet_init=quiet_init,
            cwd=cwd,
            builddir=builddir,
            bitbakedir=bitbakedir,
            init_env=init_env,
        )
        return self.assertSubprocess(
            [os.environ.get("SHELL", "/bin/bash"), cmd_file],
            pretty_command=command,
            cwd=cwd,
            **kwargs,
        )

    def assertPyrexContainerShellCommand(self, *args, **kwargs):
        cmd_file = self._write_container_command(args)
        return self.assertPyrexHostCommand("pyrex-shell %s" % cmd_file, **kwargs)

    def assertPyrexContainerCommand(self, cmd, **kwargs):
        return self.assertPyrexHostCommand("pyrex-run %s" % cmd, **kwargs)

    def assertPyrexContainerShellPTY(
        self, *args, returncode=0, env=None, quiet_init=False, bitbakedir=""
    ):
        container_cmd_file = self._write_container_command(args)
        host_cmd_file, _ = self._write_host_command(
            ["pyrex-shell %s" % container_cmd_file],
            quiet_init=quiet_init,
            bitbakedir=bitbakedir,
        )
        stdout = []

        def master_read(fd):
            while True:
                data = os.read(fd, 1024)
                if not data:
                    return data

                stdout.append(data)

        old_env = None
        try:
            if env:
                old_env = os.environ.copy()
                os.environ.clear()
                os.environ.update(env)

            status = pty.spawn(["/bin/bash", host_cmd_file], master_read)
        finally:
            if old_env is not None:
                os.environ.clear()
                os.environ.update(old_env)

        self.assertFalse(
            os.WIFSIGNALED(status),
            msg="%s died from a signal: %s" % (" ".join(args), os.WTERMSIG(status)),
        )
        self.assertTrue(
            os.WIFEXITED(status), msg="%s exited abnormally" % " ".join(args)
        )
        self.assertEqual(
            os.WEXITSTATUS(status), returncode, msg="%s failed" % " ".join(args)
        )
        return (b"".join(stdout)).decode("utf-8").rstrip()


class PyrexImageType_base(PyrexTest):
    """
    Base image tests. All images that derive from a -base image should derive
    from this class
    """

    def test_init(self):
        self.assertPyrexHostCommand("true")

    def test_pyrex_shell(self):
        self.assertPyrexContainerShellCommand("exit 3", returncode=3)

    def test_pyrex_run(self):
        self.assertPyrexContainerCommand("/bin/false", returncode=1)

    def test_in_container(self):
        def capture_pyrex_state(*args, **kwargs):
            capture_file = os.path.join(self.thread_dir, "pyrex_capture")

            if self.provider == "podman":
                self.assertPyrexContainerShellCommand(
                    "cp --no-preserve=all /proc/1/cmdline %s" % capture_file,
                    *args,
                    **kwargs,
                )
                with open(capture_file, "rb") as f:
                    return f.read()
            else:
                self.assertPyrexContainerShellCommand(
                    "cat /proc/self/cgroup > %s" % capture_file, *args, **kwargs
                )
                with open(capture_file, "r") as f:
                    return f.read()

        def capture_local_state():
            if self.provider == "podman":
                with open("/proc/1/cmdline", "rb") as f:
                    return f.read()
            else:
                with open("/proc/self/cgroup", "r") as f:
                    return f.read()

        local_state = capture_local_state()

        pyrex_state = capture_pyrex_state()
        self.assertNotEqual(local_state, pyrex_state)

    def test_quiet_build(self):
        env = os.environ.copy()
        env["PYREX_BUILD_QUIET"] = "1"
        self.assertPyrexHostCommand("true", env=env)

    def test_bad_provider(self):
        # Prevent container build from working
        os.symlink("/bin/false", os.path.join(self.bin_dir, self.provider))

        # Verify that attempting to run build pyrex without a valid container
        # provider shows the installation instructions
        output = self.assertPyrexHostCommand("true", returncode=1, capture=True)
        self.assertIn("Unable to run", output)

    def test_ownership(self):
        # Test that files created in the container are the same UID/GID as the
        # user running outside

        test_file = os.path.join(self.thread_dir, "ownertest")
        if os.path.exists(test_file):
            os.unlink(test_file)

        self.assertPyrexContainerShellCommand(
            'echo "$(id -un):$(id -gn)" > %s' % test_file
        )

        s = os.stat(test_file)

        self.assertEqual(s.st_uid, os.getuid())
        self.assertEqual(s.st_gid, os.getgid())

        with open(test_file, "r") as f:
            (username, groupname) = f.read().rstrip().split(":")

        self.assertEqual(username, pwd.getpwuid(os.getuid()).pw_name)
        self.assertEqual(groupname, grp.getgrgid(os.getgid()).gr_name)

    def test_owner_env(self):
        # This test is primarily designed to ensure that everything is passed
        # correctly through 'pyrex run'

        if self.provider == "podman":
            self.skipTest("Rootless podman cannot change to another user")

        conf = self.get_config()

        # Note: These config variables are intended for testing use only
        conf["run"]["uid"] = "1337"
        conf["run"]["username"] = "theuser"
        conf["run"]["groups"] = "7331:thegroup 7332:othergroup"
        conf["run"]["initcommand"] = ""
        conf.write_conf()

        # Make a fifo that the container can write into. We can't just write a
        # file because it won't be owned by running user and thus can't be
        # cleaned up
        old_umask = os.umask(0)
        self.addCleanup(os.umask, old_umask)

        fifo = os.path.join(self.thread_dir, "fifo")
        os.mkfifo(fifo)
        self.addCleanup(os.remove, fifo)

        os.umask(old_umask)

        output = []

        def read_fifo():
            nonlocal output
            with open(fifo, "r") as f:
                output = f.readline().rstrip().split(":")

        thread = threading.Thread(target=read_fifo)
        thread.start()
        try:
            self.assertPyrexContainerShellCommand(
                'echo "$(id -u):$(id -g):$(id -un):$(id -gn):$USER:$GROUP:$(id -G):$(id -Gn)" > %s'
                % fifo
            )
        finally:
            thread.join()

        self.assertEqual(output[0], "1337")
        self.assertEqual(output[1], "7331")
        self.assertEqual(output[2], "theuser")
        self.assertEqual(output[3], "thegroup")
        self.assertEqual(output[4], "theuser")
        self.assertEqual(output[5], "thegroup")
        self.assertEqual(output[6], "7331 7332")
        self.assertEqual(output[7], "thegroup othergroup")

    def test_rlimit_nofile(self):
        if self.provider != "podman":
            self.skipTest("Only podman needs rlimit changes")

        (soft, hard) = resource.getrlimit(resource.RLIMIT_NOFILE)
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard / 2, hard))
            s = self.assertPyrexContainerShellCommand(
                "ulimit -n && ulimit -Hn", capture=True, quiet_init=True
            )
            self.assertEqual(tuple(int(lim) for lim in s.split()), (hard, hard))
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))

    def test_bind_from_PYREX_BIND(self):
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        temp_file = os.path.join(temp_dir, "data")

        env = os.environ.copy()
        env["PYREX_BIND"] = temp_dir

        self.assertPyrexContainerShellCommand("echo 123 > %s" % temp_file, env=env)

        with open(temp_file, "r") as f:
            self.assertEqual(f.read(), "123\n")

    def test_duplicate_binds(self):
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        conf = self.get_config()
        conf["run"]["bind"] += " %s %s" % (temp_dir, temp_dir)
        conf.write_conf()

        self.assertPyrexContainerShellCommand("true")

    def test_missing_bind(self):
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        missing_bind = os.path.join(temp_dir, "does-not-exist")
        conf = self.get_config()
        conf["run"]["bind"] += " %s" % missing_bind
        conf.write_conf()

        s = self.assertPyrexContainerShellCommand(
            "test -e %s" % missing_bind, capture=True, returncode=1
        )
        self.assertRegex(s, r"Error: bind source path \S+ does not exist")

    def test_optional_bind(self):
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        missing_bind = os.path.join(temp_dir, "does-not-exist")
        conf = self.get_config()
        conf["run"]["bind"] += " %s,optional" % missing_bind
        conf.write_conf()

        self.assertPyrexContainerShellCommand("test ! -e %s" % missing_bind)

    def test_readonly_bind(self):
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        temp_file = "%s/test.txt" % temp_dir
        with open(temp_file, "w") as f:
            f.write("foo\n")

        conf = self.get_config(defaults=True)
        conf["run"]["bind"] += " %s" % temp_dir
        conf.write_conf()

        self.assertPyrexContainerShellCommand("echo bar1 > %s" % temp_file)

        with open(temp_file, "r") as f:
            self.assertEqual(f.read(), "bar1\n", "Temporary file was overwritten")

        conf = self.get_config(defaults=True)
        conf["run"]["bind"] += " %s,readonly" % temp_dir
        conf.write_conf()

        self.assertPyrexContainerShellCommand(
            "echo bar2 > %s" % temp_file, returncode=1
        )

        with open(temp_file, "r") as f:
            self.assertEqual(f.read(), "bar1\n", "Temporary file was overwritten")

    def test_bad_bind_option(self):
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        missing_bind = os.path.join(temp_dir, "does-not-exist")
        conf = self.get_config()
        conf["run"]["bind"] += " %s,bad-option" % missing_bind
        conf.write_conf()

        s = self.assertPyrexContainerShellCommand(
            "test ! -e %s" % missing_bind, capture=True, returncode=1
        )
        self.assertIn("Error: bad option(s) 'bad-option' for bind", s)

    def test_bad_confversion(self):
        # Verify that a bad config is an error
        conf = self.get_config()
        conf["config"]["confversion"] = "0"
        conf.write_conf()

        self.assertPyrexHostCommand("true", returncode=1)

    def test_conftemplate_ignored(self):
        # Write out a template with a bad version in an alternate location. It
        # should be ignored
        temp_dir = tempfile.mkdtemp("-pyrex")
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, "pyrex.ini.sample")

        conf = self.get_config(defaults=True)
        conf["config"]["confversion"] = "0"
        with open(conftemplate, "w") as f:
            conf.write(f)

        self.assertPyrexHostCommand("true")

    @skipIfPrebuilt
    def test_local_build(self):
        conf = self.get_config()
        conf["config"]["buildlocal"] = "1"
        conf.write_conf()
        self.assertPyrexHostCommand("true")

    def test_version(self):
        self.assertRegex(
            pyrex.VERSION,
            pyrex.VERSION_REGEX,
            msg="Version '%s' is invalid" % pyrex.VERSION,
        )

    def test_version_tag(self):
        tag = None
        if os.environ.get("RELEASE_TAG"):
            tag = os.environ["RELEASE_TAG"]
        else:
            try:
                tags = (
                    subprocess.check_output(
                        ["git", "-C", PYREX_ROOT, "tag", "-l", "--points-at", "HEAD"]
                    )
                    .decode("utf-8")
                    .splitlines()
                )
                if tags:
                    tag = tags[0]
            except subprocess.CalledProcessError:
                pass

        if not tag:
            self.skipTest("No tag found")

        self.assertEqual("v%s" % pyrex.VERSION, tag)
        self.assertRegex(tag, pyrex.VERSION_TAG_REGEX, msg="Tag '%s' is invalid" % tag)

    @skipIfPrebuilt
    def test_tag_overwrite(self):
        # Test that trying to build the image with a release-like tag fails
        # (and doesn't build the image)
        conf = self.get_config()
        conf["config"]["pyrextag"] = "v1.2.3-ci-test"
        conf["config"]["buildlocal"] = "1"
        conf.write_conf()

        self.assertPyrexHostCommand("true", returncode=1)

        output = self.assertSubprocess(
            [self.provider, "images", "-q", conf["config"]["tag"]], capture=True
        ).strip()
        self.assertEqual(output, "", msg="Tagged image found!")

    def test_pty(self):
        self.assertPyrexContainerShellPTY("true")
        self.assertPyrexContainerShellPTY("false", returncode=1)

    def test_invalid_term(self):
        # Tests that an invalid terminal is correctly detected.
        bad_term = "this-is-not-a-valid-term"
        env = os.environ.copy()
        env["TERM"] = bad_term
        output = self.assertPyrexContainerShellPTY("true", env=env)
        self.assertIn('$TERM has an unrecognized value of "%s"' % bad_term, output)
        self.assertPyrexContainerShellPTY(
            "/usr/bin/infocmp %s > /dev/null" % bad_term,
            env=env,
            returncode=1,
            quiet_init=True,
        )

    def test_required_terms(self):
        # Tests that a minimum set of terminals are supported
        REQUIRED_TERMS = ("dumb", "vt100", "xterm", "xterm-256color")

        env = os.environ.copy()
        for t in REQUIRED_TERMS:
            with self.subTest(term=t):
                env["TERM"] = t
                output = self.assertPyrexContainerShellPTY(
                    "echo $TERM", env=env, quiet_init=True
                )
                self.assertEqual(output, t, msg="Bad $TERM found in container!")

                output = self.assertPyrexContainerShellPTY(
                    "/usr/bin/infocmp %s > /dev/null" % t, env=env
                )
                self.assertNotIn("$TERM has an unrecognized value", output)

                output = self.assertPyrexContainerShellCommand(
                    "echo $TERM", env=env, quiet_init=True, capture=True
                )
                self.assertEqual(output, t, msg="Bad $TERM found in container!")

    def test_tini(self):
        self.assertPyrexContainerCommand("tini --version")

    def test_guest_image(self):
        # This test makes sure that the image being tested is the image we
        # actually expect to be testing

        # Split out the image name, version, and type
        (image_name, image_version, _) = self.test_image.split("-")

        # Capture the LSB release information.
        dist_id_str = self.assertPyrexContainerCommand(
            "lsb_release -i", quiet_init=True, capture=True
        )
        release_str = self.assertPyrexContainerCommand(
            "lsb_release -r", quiet_init=True, capture=True
        )

        self.assertRegex(
            dist_id_str.lower(), r"^distributor id:\s+" + re.escape(image_name)
        )
        self.assertRegex(
            release_str.lower(), r"^release:\s+" + re.escape(image_version) + r"(\.|$)"
        )

    def test_default_ini_image(self):
        # Tests that the default image specified in pyrex.ini is valid
        config = pyrex.Config()
        config.read_string(pyrex.read_default_config(True))

        self.assertIn(config["config"]["image"], (image for (image, _) in TEST_IMAGES))

    def test_envvars(self):
        conf = self.get_config()
        conf["run"]["envvars"] += " TEST_ENV"
        conf.write_conf()

        test_string = "set_by_test.%d" % threading.get_ident()

        env = os.environ.copy()
        env["TEST_ENV"] = test_string

        s = self.assertPyrexContainerShellCommand(
            "echo $TEST_ENV", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, test_string)

        s = self.assertPyrexContainerShellCommand(
            "echo $TEST_ENV2", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, "")

    def test_custom_startup_script(self):
        conf = self.get_config()
        conf["run"]["envvars"] += " PYREX_TEST_STARTUP_SCRIPT"
        conf.write_conf()

        env = os.environ.copy()
        env["PYREX_TEST_STARTUP_SCRIPT"] = "3"
        self.assertPyrexContainerShellCommand(
            "echo $PYREX_TEST_STARTUP_SCRIPT", env=env, quiet_init=True, returncode=3
        )

        env["PYREX_TEST_STARTUP_SCRIPT"] = "0"
        s = self.assertPyrexContainerShellCommand(
            "echo $PYREX_TEST_STARTUP_SCRIPT", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, "Startup script test\n0")

    def test_users(self):
        users = set(
            self.assertPyrexContainerShellCommand(
                "getent passwd | cut -f1 -d:", quiet_init=True, capture=True
            ).split()
        )
        self.assertEqual(users, {"root", pwd.getpwuid(os.getuid()).pw_name})

    def test_groups(self):
        groups = set(
            self.assertPyrexContainerShellCommand(
                "getent group | cut -f1 -d:", quiet_init=True, capture=True
            ).split()
        )

        my_groups = {"root", grp.getgrgid(os.getgid()).gr_name}
        for gid in os.getgroups():
            my_groups.add(grp.getgrgid(gid).gr_name)

        self.assertEqual(groups, my_groups)

    def test_env_passthrough_var(self):
        env = os.environ.copy()
        if self.pokyver < (4, 0):
            varname = "BB_ENV_EXTRAWHITE"
        else:
            varname = "BB_ENV_PASSTHROUGH_ADDITIONS"
        env[varname] = "TEST_BB_EXTRA"
        env["TEST_BB_EXTRA"] = "Hello"

        s = set(
            self.assertPyrexContainerShellCommand(
                f"echo ${varname}", env=env, quiet_init=True, capture=True
            ).split()
        )
        self.assertIn(env[varname], s)

        s = self.assertPyrexContainerShellCommand(
            "echo $TEST_BB_EXTRA", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, env["TEST_BB_EXTRA"])

    def test_ssh_auth_sock(self):
        with tempfile.NamedTemporaryFile() as auth_file:
            env = os.environ.copy()
            env["SSH_AUTH_SOCK"] = auth_file.name
            auth_file_stat = os.stat(auth_file.name)

            s = self.assertPyrexContainerShellCommand(
                "stat --format='%d %i' $SSH_AUTH_SOCK",
                env=env,
                quiet_init=True,
                capture=True,
            )
            self.assertEqual(
                s, "%d %d" % (auth_file_stat.st_dev, auth_file_stat.st_ino)
            )

        auth_sock_path = os.path.join(self.build_dir, "does-not-exist")
        env = os.environ.copy()
        env["SSH_AUTH_SOCK"] = auth_sock_path

        s = self.assertPyrexContainerShellCommand("true", env=env, capture=True)
        self.assertRegex(s, r"Warning: SSH_AUTH_SOCK \S+ does not exist")

        s = self.assertPyrexContainerShellCommand(
            "echo $SSH_AUTH_SOCK", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, "")

    @skipIfPrebuilt
    def test_rebuild(self):
        self.assertPyrexHostCommand("pyrex-rebuild")

    def test_pyrex_config(self):
        conf = self.get_config()
        conf.add_section("ci")
        conf["ci"]["foo"] = "ABC"
        conf["ci"]["bar"] = "${ci:foo}DEF"
        conf["ci"]["baz"] = "${bar}GHI"
        conf.write_conf()

        s = self.assertPyrexHostCommand(
            "pyrex-config get ci:foo", quiet_init=True, capture=True
        )
        self.assertEqual(s, "ABC")

        s = self.assertPyrexHostCommand(
            "pyrex-config get ci:bar", quiet_init=True, capture=True
        )
        self.assertEqual(s, "ABCDEF")

        s = self.assertPyrexHostCommand(
            "pyrex-config get ci:baz", quiet_init=True, capture=True
        )
        self.assertEqual(s, "ABCDEFGHI")

    def test_pyrex_mkconfig(self):
        out_file = os.path.join(self.build_dir, "temp-pyrex.ini")
        cmd = [os.path.join(PYREX_ROOT, "pyrex.py"), "mkconfig"]

        output = self.assertSubprocess(
            cmd + [out_file], capture=True, cwd=self.build_dir
        )
        self.assertEqual(output, out_file)

        output = self.assertSubprocess(cmd, capture=True)
        self.assertEqual(output, pyrex.read_default_config(False).rstrip())

        with open(out_file, "r") as f:
            self.assertEqual(f.read().rstrip(), output)

        self.assertSubprocess(cmd + [out_file], cwd=self.build_dir, returncode=1)

    def test_user_commands(self):
        conf = self.get_config()
        conf["config"]["commands"] = "/bin/true !/bin/false"
        conf.write_conf()

        self.assertPyrexHostCommand("/bin/true")
        self.assertPyrexHostCommand("/bin/false", returncode=1)

        prefix = []
        if "zsh" in os.environ.get("SHELL", ""):
            prefix = ["disable true false"]

        true_path = self.assertPyrexHostCommand(
            *(prefix + ["which true"]), capture=True, quiet_init=True
        )
        true_link_path = os.readlink(true_path)
        self.assertEqual(os.path.basename(true_link_path), "exec-shim-pyrex")

        false_path = self.assertPyrexHostCommand(
            *(prefix + ["which false"]), capture=True, quiet_init=True
        )
        false_link_path = os.readlink(false_path)
        self.assertEqual(os.path.basename(false_link_path), "false")

    def test_lets_encrypt_root_ca(self):
        # Tests that root Let's Encrypt certficiate still works. The older X3
        # certificate expired in September 2021 and a bug in older versions of
        # OpenSSL prevents clients from seeing the new one
        self.assertPyrexContainerShellCommand("curl https://letsencrypt.org/")


class PyrexImageType_oe(PyrexImageType_base):
    """
    Tests images designed for building OpenEmbedded
    """

    def test_bitbake_parse(self):
        self.assertPyrexHostCommand("bitbake -p")

    def test_bitbake_parse_altpath_arg(self):
        # The new bitbake directory is out of the normally bound tree (passed
        # as an argument)
        with tempfile.TemporaryDirectory() as tmpdir:
            bitbakedir = os.path.join(tmpdir, "bitbake")
            shutil.copytree(os.path.join(self.pokyroot, "bitbake"), bitbakedir)

            # If the bitbake directory is not bound, capture should fail with
            # an error
            d = self.assertPyrexHostCommand(
                "bitbake -p", bitbakedir=bitbakedir, returncode=1, capture=True
            )
            self.assertIn("ERROR: %s not bound in container" % bitbakedir, d)

            # Binding the build directory in the conf file will allow bitbake
            # to be found
            conf = self.get_config()
            conf["run"]["bind"] = bitbakedir
            conf.write_conf()

            d = self.assertPyrexContainerCommand(
                "which bitbake", bitbakedir=bitbakedir, quiet_init=True, capture=True
            )
            self.assertEqual(d, os.path.join(bitbakedir, "bin", "bitbake"))

            self.assertPyrexHostCommand("bitbake -p", bitbakedir=bitbakedir)

    def test_bitbake_parse_altpath_env(self):
        # The new bitbake directory is out of the normally bound tree (passed
        # as an argument)
        with tempfile.TemporaryDirectory() as tmpdir:
            bitbakedir = os.path.join(tmpdir, "bitbake")
            shutil.copytree(os.path.join(self.pokyroot, "bitbake"), bitbakedir)

            env = {"BITBAKEDIR": bitbakedir}

            # If the bitbake directory is not bound, capture should fail with
            # an error
            d = self.assertPyrexHostCommand(
                "bitbake -p", returncode=1, capture=True, init_env=env
            )
            self.assertIn("ERROR: %s not bound in container" % bitbakedir, d)

            # Binding the build directory in the conf file will allow bitbake
            # to be found
            conf = self.get_config()
            conf["run"]["bind"] = bitbakedir
            conf.write_conf()

            d = self.assertPyrexContainerCommand(
                "which bitbake", quiet_init=True, capture=True, init_env=env
            )
            self.assertEqual(d, os.path.join(bitbakedir, "bin", "bitbake"))

            self.assertPyrexHostCommand("bitbake -p", init_env=env)

    def test_builddir_alt_env(self):
        with tempfile.TemporaryDirectory() as builddir:
            # Binding the build directory in the conf file will allow building
            # to continue
            conf = self.get_config()
            conf["run"]["bind"] = builddir
            conf.write_conf()

            env = {"BDIR": builddir}

            self.assertPyrexHostCommand("true", builddir="", init_env=env)

    def test_unbound_builddir(self):
        with tempfile.TemporaryDirectory() as builddir:
            # If the build directory is not bound, capture should fail with an
            # error
            d = self.assertPyrexHostCommand(
                "true", builddir=builddir, returncode=1, capture=True
            )
            self.assertIn("ERROR: %s not bound in container" % builddir, d)

            # Binding the build directory in the conf file will allow building
            # to continue
            conf = self.get_config()
            conf["run"]["bind"] = builddir
            conf.write_conf()

            self.assertPyrexHostCommand("true", builddir=builddir)

    def test_icecc(self):
        self.assertPyrexContainerCommand("icecc --version")

    def test_templateconf_abs(self):
        template_dir = os.path.join(self.thread_dir, "template")
        os.makedirs(template_dir)

        self.assertTrue(os.path.isabs(template_dir))

        shutil.copyfile(
            os.path.join(self.pokyroot, "meta-poky/conf/local.conf.sample"),
            os.path.join(template_dir, "local.conf.sample"),
        )
        shutil.copyfile(
            os.path.join(self.pokyroot, "meta-poky/conf/bblayers.conf.sample"),
            os.path.join(template_dir, "bblayers.conf.sample"),
        )

        test_string = "set_by_test.%d" % threading.get_ident()

        conf = self.get_config()
        conf["run"]["envvars"] += " TEST_ENV"
        conf.write_conf()

        env = os.environ.copy()
        env["TEMPLATECONF"] = template_dir
        env["TEST_ENV"] = test_string

        s = self.assertPyrexContainerShellCommand(
            "echo $TEST_ENV", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, test_string)

    def test_templateconf_rel(self):
        template_dir = os.path.join(self.thread_dir, "template")
        os.makedirs(template_dir)

        self.assertTrue(os.path.isabs(template_dir))

        shutil.copyfile(
            os.path.join(self.pokyroot, "meta-poky/conf/local.conf.sample"),
            os.path.join(template_dir, "local.conf.sample"),
        )
        shutil.copyfile(
            os.path.join(self.pokyroot, "meta-poky/conf/bblayers.conf.sample"),
            os.path.join(template_dir, "bblayers.conf.sample"),
        )

        test_string = "set_by_test.%d" % threading.get_ident()

        conf = self.get_config()
        conf["run"]["envvars"] += " TEST_ENV"
        conf.write_conf()

        env = os.environ.copy()
        env["TEMPLATECONF"] = os.path.relpath(template_dir, self.pokyroot)
        env["TEST_ENV"] = test_string

        s = self.assertPyrexContainerShellCommand(
            "echo $TEST_ENV", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, test_string)

    def test_top_dir(self):
        # Verify that the TOPDIR reported by bitbake in pyrex is the same as
        # the one reported by bitbake outside of pyrex
        cwd = os.path.join(self.build_dir, "oe-build")
        try:
            os.makedirs(cwd)
        except OSError:
            pass

        builddir = os.path.join(cwd, "build")

        oe_topdir = self.assertSubprocess(
            [
                "/bin/bash",
                "-c",
                ". %s/oe-init-build-env > /dev/null && (bitbake -e | grep ^TOPDIR=)"
                % os.path.relpath(self.pokyroot, cwd),
            ],
            capture=True,
            cwd=cwd,
        )

        # Since bitbake is being invoked outside of Pyrex, we need to wait
        # until it exits before trying to cleanup the build directory,
        # otherwise it can race.
        wait_time = 20
        for _ in range(wait_time):
            if not os.path.exists(os.path.join(builddir, "bitbake.lock")):
                break
            time.sleep(1)
        else:
            self.fail(f"bitbake did not exit within {wait_time} seconds")

        shutil.rmtree(builddir)

        pyrex_topdir = self.assertPyrexHostCommand(
            "bitbake -e | grep ^TOPDIR=",
            quiet_init=True,
            capture=True,
            cwd=cwd,
            builddir="build",
        )
        shutil.rmtree(builddir)

        self.assertEqual(oe_topdir, pyrex_topdir)

    def test_env_capture(self):
        if self.pokyver < (4, 0):
            varname = "BB_ENV_EXTRAWHITE"
        else:
            varname = "BB_ENV_PASSTHROUGH_ADDITIONS"

        extra_env = set(
            self.assertPyrexHostCommand(
                f"echo ${varname}", quiet_init=True, capture=True
            ).split()
        )

        # The exact values aren't relevant, only that they are correctly
        # imported from the capture
        self.assertIn("MACHINE", extra_env)
        self.assertIn("DISTRO", extra_env)

        builddir = self.assertPyrexHostCommand(
            "echo $BUILDDIR", quiet_init=True, capture=True
        )
        self.assertEqual(builddir, self.build_dir)

    def test_bb_env_extra_parse(self):
        if self.pokyver < (4, 0):
            varname = "BB_ENV_EXTRAWHITE"
        else:
            varname = "BB_ENV_PASSTHROUGH_ADDITIONS"

        env = os.environ.copy()
        env[varname] = "TEST_BB_EXTRA"
        env["TEST_BB_EXTRA"] = "foo"

        s = self.assertPyrexHostCommand(
            "bitbake -e | grep ^TEST_BB_EXTRA=", env=env, quiet_init=True, capture=True
        )
        self.assertEqual(s, 'TEST_BB_EXTRA="foo"')

    @skipIfOS("ubuntu", "14.04")
    @skipIfOS("ubuntu", "16.04")
    def test_wine(self):
        self.assertPyrexContainerCommand("wine --version")


class PyrexImageType_oegarmin(PyrexImageType_oe):
    """
    Tests images designed for building OpenEmbedded, from inside the Garmin
    corporate LAN.
    """

    pass


class PyrexImageType_oetest(PyrexImageType_oe):
    """
    Tests images designed for building OpenEmbedded Test image
    """

    pass


PROVIDERS = ("docker", "podman")

TEST_IMAGES = (
    ("ubuntu-14.04-base", (2, 6)),
    ("ubuntu-16.04-base", (2, 6)),
    ("ubuntu-18.04-base", (2, 6)),
    ("ubuntu-20.04-base", (3, 1)),
    ("ubuntu-22.04-base", (4, 0)),
    ("ubuntu-14.04-oe", (2, 6)),
    ("ubuntu-16.04-oe", (2, 6)),
    ("ubuntu-18.04-oe", (2, 6)),
    ("ubuntu-20.04-oe", (3, 1)),
    ("ubuntu-22.04-oe", (4, 0)),
    ("ubuntu-14.04-oegarmin", (2, 6)),
    ("ubuntu-16.04-oegarmin", (2, 6)),
    ("ubuntu-18.04-oegarmin", (2, 6)),
    ("ubuntu-20.04-oegarmin", (3, 1)),
    ("ubuntu-22.04-oegarmin", (4, 0)),
    ("ubuntu-18.04-oetest", (2, 6)),
    ("ubuntu-20.04-oetest", (3, 1)),
)


def add_image_tests():
    self = sys.modules[__name__]
    for provider in PROVIDERS:
        for (image, pokyver) in TEST_IMAGES:
            (_, _, image_type) = image.split("-")

            parent = getattr(self, "PyrexImageType_" + image_type)

            name = "PyrexImage_%s_%s" % (provider, re.sub(r"\W", "_", image))
            setattr(
                self,
                name,
                type(
                    name,
                    (parent, unittest.TestCase),
                    {"test_image": image, "provider": provider, "pokyver": pokyver},
                ),
            )


add_image_tests()

if __name__ == "__main__":
    unittest.main()
