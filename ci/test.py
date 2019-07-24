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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import pty

PYREX_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(PYREX_ROOT)
import pyrex  # NOQA

TEST_PREBUILT_TAG_ENV_VAR = 'TEST_PREBUILT_TAG'


def skipIfPrebuilt(func):
    def wrapper(self, *args, **kwargs):
        if os.environ.get(TEST_PREBUILT_TAG_ENV_VAR, ''):
            self.skipTest('Test does not apply to prebuilt images')
        return func(self, *args, **kwargs)
    return wrapper


class PyrexTest(object):
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
            os.environ.clear()
            os.environ.update(self.old_environ)

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

        # Write out the default test config
        conf = self.get_config()
        conf.write_conf()

    def get_config(self, defaults=False):
        class Config(configparser.RawConfigParser):
            def write_conf(self):
                write_config_helper(self)

        def write_config_helper(conf):
            with open(self.pyrex_conf, 'w') as f:
                conf.write(f)

        config = Config()
        if os.path.exists(self.pyrex_conf) and not defaults:
            config.read(self.pyrex_conf)
        else:
            config.read_string(pyrex.read_default_config(True))

            # Setup the config suitable for testing
            config['config']['dockerimage'] = self.test_image

            prebuilt_tag = os.environ.get(TEST_PREBUILT_TAG_ENV_VAR, '')
            if prebuilt_tag:
                config['config']['pyrextag'] = prebuilt_tag
                config['config']['buildlocal'] = '0'
            else:
                # Always build the latest image locally for testing. Use a tag that
                # isn't present on docker hub so that any attempt to pull it fails
                config['config']['pyrextag'] = 'ci-test'
                config['config']['buildlocal'] = '1'

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

            self.assertEqual(ret, returncode, msg='%s failed' % ' '.join(*args))
            return None

    def _write_host_command(self, args, quiet_init=False):
        cmd_file = os.path.join(self.thread_dir, 'command')
        with open(cmd_file, 'w') as f:
            f.write('. ./poky/pyrex-init-build-env%s && ' % (' > /dev/null 2>&1' if quiet_init else ''))
            f.write(' && '.join(list(args)))
        return cmd_file

    def _write_container_command(self, args):
        cmd_file = os.path.join(self.thread_dir, 'container_command')
        with open(cmd_file, 'w') as f:
            f.write(' && '.join(args))
        return cmd_file

    def assertPyrexHostCommand(self, *args, quiet_init=False, **kwargs):
        cmd_file = self._write_host_command(args, quiet_init)
        return self.assertSubprocess(['/bin/bash', cmd_file], cwd=PYREX_ROOT, **kwargs)

    def assertPyrexContainerShellCommand(self, *args, **kwargs):
        cmd_file = self._write_container_command(args)
        return self.assertPyrexHostCommand('pyrex-shell %s' % cmd_file, **kwargs)

    def assertPyrexContainerCommand(self, cmd, **kwargs):
        return self.assertPyrexHostCommand('pyrex-run %s' % cmd, **kwargs)

    def assertPyrexContainerShellPTY(self, *args, returncode=0, env=None, quiet_init=False):
        container_cmd_file = self._write_container_command(args)
        host_cmd_file = self._write_host_command(['pyrex-shell %s' % container_cmd_file], quiet_init)
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

            status = pty.spawn(['/bin/bash', host_cmd_file], master_read)
        finally:
            if old_env is not None:
                os.environ.clear()
                os.environ.update(old_env)

        self.assertFalse(os.WIFSIGNALED(status), msg='%s died from a signal: %s' %
                         (' '.join(args), os.WTERMSIG(status)))
        self.assertTrue(os.WIFEXITED(status), msg='%s exited abnormally' % ' '.join(args))
        self.assertEqual(os.WEXITSTATUS(status), returncode, msg='%s failed' % ' '.join(args))
        return b''.join(stdout)


class PyrexImageType_base(PyrexTest):
    """
    Base image tests. All images that derive from a -base image should derive
    from this class
    """

    def test_init(self):
        self.assertPyrexHostCommand('true')

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
        output = self.assertPyrexHostCommand('PYREX_DOCKER=1 bitbake', returncode=1,
                                             capture=True, env=env).decode('utf-8')
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

    def test_owner_env(self):
        # This test is primarily designed to ensure that everything is passed
        # correctly through 'pyrex run'

        conf = self.get_config()

        # Note: These config variables are intended for testing use only
        conf['run']['uid'] = '1337'
        conf['run']['gid'] = '7331'
        conf['run']['username'] = 'theuser'
        conf['run']['groupname'] = 'thegroup'
        conf['run']['initcommand'] = ''
        conf.write_conf()

        # Make a fifo that the container can write into. We can't just write a
        # file because it won't be owned by running user and thus can't be
        # cleaned up
        old_umask = os.umask(0)
        self.addCleanup(os.umask, old_umask)

        fifo = os.path.join(self.thread_dir, 'fifo')
        os.mkfifo(fifo)
        self.addCleanup(os.remove, fifo)

        os.umask(old_umask)

        output = []

        def read_fifo():
            nonlocal output
            with open(fifo, 'r') as f:
                output = f.readline().rstrip().split(':')

        thread = threading.Thread(target=read_fifo)
        thread.start()
        try:
            self.assertPyrexContainerShellCommand(
                'echo "$(id -u):$(id -g):$(id -un):$(id -gn):$USER:$GROUP" > %s' % fifo)
        finally:
            thread.join()

        self.assertEqual(output[0], '1337')
        self.assertEqual(output[1], '7331')
        self.assertEqual(output[2], 'theuser')
        self.assertEqual(output[3], 'thegroup')
        self.assertEqual(output[4], 'theuser')
        self.assertEqual(output[5], 'thegroup')

    def test_duplicate_binds(self):
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conf = self.get_config()
        conf['run']['bind'] += ' %s %s' % (temp_dir, temp_dir)
        conf.write_conf()

        self.assertPyrexContainerShellCommand('true')

    def test_bad_confversion(self):
        # Verify that a bad config is an error
        conf = self.get_config()
        conf['config']['confversion'] = '0'
        conf.write_conf()

        self.assertPyrexHostCommand('true', returncode=1)

    def test_conftemplate_ignored(self):
        # Write out a template with a bad version in an alternate location. It
        # should be ignored
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, 'pyrex.ini.sample')

        conf = self.get_config(defaults=True)
        conf['config']['confversion'] = '0'
        with open(conftemplate, 'w') as f:
            conf.write(f)

        self.assertPyrexHostCommand('true')

    def test_conf_upgrade(self):
        conf = self.get_config()
        del conf['config']['confversion']
        conf.write_conf()

        # Write out a template in an alternate location. It will be respected
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, 'pyrex.ini.sample')

        conf = self.get_config(defaults=True)
        with open(conftemplate, 'w') as f:
            conf.write(f)

        env = os.environ.copy()
        env['PYREXCONFTEMPLATE'] = conftemplate

        self.assertPyrexHostCommand('true', env=env)

    def test_bad_conf_upgrade(self):
        # Write out a template in an alternate location, but it also fails to
        # have a confversion
        conf = self.get_config()
        del conf['config']['confversion']
        conf.write_conf()

        # Write out a template in an alternate location. It will be respected
        temp_dir = tempfile.mkdtemp('-pyrex')
        self.addCleanup(shutil.rmtree, temp_dir)

        conftemplate = os.path.join(temp_dir, 'pyrex.ini.sample')

        conf = self.get_config(defaults=True)
        del conf['config']['confversion']
        with open(conftemplate, 'w') as f:
            conf.write(f)

        env = os.environ.copy()
        env['PYREXCONFTEMPLATE'] = conftemplate

        self.assertPyrexHostCommand('true', returncode=1, env=env)

    def test_force_conf(self):
        # Write out a new config file and set the variable to force it to be
        # used
        conf = self.get_config()
        conf['config']['test'] = 'bar'
        force_conf_file = os.path.join(self.thread_dir, 'force.ini')
        with open(force_conf_file, 'w') as f:
            conf.write(f)

        # Set the variable to a different value in the standard config file
        conf = self.get_config()
        conf['config']['test'] = 'foo'
        conf.write_conf()

        output = self.assertPyrexHostCommand('pyrex-config get config:test', quiet_init=True,
                                             capture=True).decode('utf-8').strip()
        self.assertEqual(output, 'foo')

        env = os.environ.copy()
        env['PYREXCONFFILE'] = force_conf_file
        output = self.assertPyrexHostCommand('pyrex-config get config:test', quiet_init=True,
                                             capture=True, env=env).decode('utf-8').strip()
        self.assertEqual(output, 'bar')

    @skipIfPrebuilt
    def test_local_build(self):
        # Run any command to build the images locally
        self.assertPyrexHostCommand('true')

        conf = self.get_config()

        # Trying to build with an invalid registry should fail
        conf['config']['registry'] = 'does.not.exist.invalid'
        conf.write_conf()
        self.assertPyrexHostCommand('true', returncode=1)

        # Disable building locally any try again (from the previously cached build)
        conf['config']['buildlocal'] = '0'
        conf.write_conf()

        self.assertPyrexHostCommand('true')

    def test_version(self):
        self.assertRegex(pyrex.VERSION, pyrex.VERSION_REGEX, msg="Version '%s' is invalid" % pyrex.VERSION)

    def test_version_tag(self):
        tag = None
        if os.environ.get('TRAVIS_TAG'):
            tag = os.environ['TRAVIS_TAG']
        else:
            try:
                tags = subprocess.check_output(['git', '-C', PYREX_ROOT, 'tag', '-l',
                                                '--points-at', 'HEAD']).decode('utf-8').splitlines()
                if tags:
                    tag = tags[0]
            except subprocess.CalledProcessError:
                pass

        if not tag:
            self.skipTest('No tag found')

        self.assertEqual('v%s' % pyrex.VERSION, tag)
        self.assertRegex(tag, pyrex.VERSION_TAG_REGEX, msg="Tag '%s' is invalid" % tag)

    @skipIfPrebuilt
    def test_tag_overwrite(self):
        # Test that trying to build the image with a release-like tag fails
        # (and doesn't build the image)
        conf = self.get_config()
        conf['config']['pyrextag'] = 'v1.2.3-ci-test'
        conf.write_conf()

        self.assertPyrexHostCommand('true', returncode=1)

        output = self.assertSubprocess(['docker', 'images', '-q', conf['config']['tag']],
                                       capture=True).decode('utf-8').strip()
        self.assertEqual(output, "", msg="Tagged image found!")

    def test_pty(self):
        self.assertPyrexContainerShellPTY('true')
        self.assertPyrexContainerShellPTY('false', returncode=1)

    def test_invalid_term(self):
        # Tests that an invalid terminal is correctly detected.
        bad_term = 'this-is-not-a-valid-term'
        env = os.environ.copy()
        env['TERM'] = bad_term
        output = self.assertPyrexContainerShellPTY('true', env=env).decode('utf-8').strip()
        self.assertIn('$TERM has an unrecognized value of "%s"' % bad_term, output)
        self.assertPyrexContainerShellPTY('/usr/bin/infocmp %s > /dev/null' %
                                          bad_term, env=env, returncode=1, quiet_init=True)

    def test_required_terms(self):
        # Tests that a minimum set of terminals are supported
        REQUIRED_TERMS = (
            'dumb',
            'vt100',
            'xterm',
            'xterm-256color'
        )

        env = os.environ.copy()
        for t in REQUIRED_TERMS:
            with self.subTest(term=t):
                env['TERM'] = t
                output = self.assertPyrexContainerShellPTY(
                    'echo $TERM', env=env, quiet_init=True).decode('utf-8').strip()
                self.assertEqual(output, t, msg='Bad $TERM found in container!')

                output = self.assertPyrexContainerShellPTY(
                    '/usr/bin/infocmp %s > /dev/null' % t, env=env).decode('utf-8').strip()
                self.assertNotIn('$TERM has an unrecognized value', output)

    def test_tini(self):
        self.assertPyrexContainerCommand('tini --version')

    def test_guest_image(self):
        # This test makes sure that the image being tested is the image we
        # actually expect to be testing

        # Split out the image name, version, and type
        (image_name, image_version, _) = self.test_image.split('-')

        # Capture the LSB release information.
        dist_id_str = self.assertPyrexContainerCommand(
            'lsb_release -i', quiet_init=True, capture=True).decode('utf-8').rstrip()
        release_str = self.assertPyrexContainerCommand(
            'lsb_release -r', quiet_init=True, capture=True).decode('utf-8').rstrip()

        self.assertRegex(dist_id_str.lower(), r'^distributor id:\s+' + re.escape(image_name))
        self.assertRegex(release_str.lower(), r'^release:\s+' + re.escape(image_version) + r'(\.|$)')

    def test_default_ini_image(self):
        # Tests that the default image specified in pyrex.ini is valid
        config = configparser.RawConfigParser()
        config.read_string(pyrex.read_default_config(True))

        self.assertIn(config['config']['dockerimage'], TEST_IMAGES)

    def test_envvars(self):
        conf = self.get_config()
        conf['run']['envvars'] += ' TEST_ENV'
        conf.write_conf()

        test_string = 'set_by_test.%d' % threading.get_ident()

        env = os.environ.copy()
        env['TEST_ENV'] = test_string

        s = self.assertPyrexContainerShellCommand(
            'echo $TEST_ENV', env=env, quiet_init=True, capture=True).decode('utf-8').rstrip()
        self.assertEqual(s, test_string)

        s = self.assertPyrexContainerShellCommand(
            'echo $TEST_ENV2', env=env, quiet_init=True, capture=True).decode('utf-8').rstrip()
        self.assertEqual(s, '')

    def test_custom_startup_script(self):
        conf = self.get_config()
        conf['run']['envvars'] += ' PYREX_TEST_STARTUP_SCRIPT'
        conf.write_conf()

        env = os.environ.copy()
        env['PYREX_TEST_STARTUP_SCRIPT'] = "3"
        self.assertPyrexContainerShellCommand(
            'echo $PYREX_TEST_STARTUP_SCRIPT', env=env, quiet_init=True, returncode=3)

        env['PYREX_TEST_STARTUP_SCRIPT'] = "0"
        s = self.assertPyrexContainerShellCommand(
            'echo $PYREX_TEST_STARTUP_SCRIPT', env=env, quiet_init=True, capture=True).decode('utf-8').rstrip()
        self.assertEqual(s, "Startup script test\n0")

    def test_users(self):
        users = set(
            self.assertPyrexContainerShellCommand(
                'getent passwd | cut -f1 -d:',
                quiet_init=True,
                capture=True).decode('utf-8').rstrip().split())
        self.assertEqual(users, {'root', pwd.getpwuid(os.getuid()).pw_name})

    def test_groups(self):
        groups = set(
            self.assertPyrexContainerShellCommand(
                'getent group | cut -f1 -d:',
                quiet_init=True,
                capture=True).decode('utf-8').rstrip().split())
        self.assertEqual(groups, {'root', grp.getgrgid(os.getgid()).gr_name})


class PyrexImageType_oe(PyrexImageType_base):
    """
    Tests images designed for building OpenEmbedded
    """

    def test_bitbake_parse(self):
        self.assertPyrexHostCommand('bitbake -p')

    def test_icecc(self):
        self.assertPyrexContainerCommand('icecc --version')

    def test_templateconf_abs(self):
        template_dir = os.path.join(self.thread_dir, 'template')
        os.makedirs(template_dir)

        self.assertTrue(os.path.isabs(template_dir))

        shutil.copyfile(os.path.join(PYREX_ROOT, 'poky/meta-poky/conf/local.conf.sample'),
                        os.path.join(template_dir, 'local.conf.sample'))
        shutil.copyfile(os.path.join(PYREX_ROOT, 'poky/meta-poky/conf/bblayers.conf.sample'),
                        os.path.join(template_dir, 'bblayers.conf.sample'))

        test_string = 'set_by_test.%d' % threading.get_ident()

        # Write out a config template that passes along the TEST_ENV variable.
        # The variable will only have the correct value in the container if
        # the template is used
        conf = self.get_config()
        conf['run']['envvars'] += ' TEST_ENV'
        with open(os.path.join(template_dir, 'pyrex.ini.sample'), 'w') as f:
            conf.write(f)
        # Delete the normal pyrex conf file so a new one will be pulled from
        # TEMPLATECONF
        os.unlink(self.pyrex_conf)

        env = os.environ.copy()
        env['TEMPLATECONF'] = template_dir
        env['TEST_ENV'] = test_string

        s = self.assertPyrexContainerShellCommand(
            'echo $TEST_ENV', env=env, quiet_init=True, capture=True).decode('utf-8').rstrip()
        self.assertEqual(s, test_string)

    def test_templateconf_rel(self):
        template_dir = os.path.join(self.thread_dir, 'template')
        os.makedirs(template_dir)

        self.assertTrue(os.path.isabs(template_dir))

        shutil.copyfile(os.path.join(PYREX_ROOT, 'poky/meta-poky/conf/local.conf.sample'),
                        os.path.join(template_dir, 'local.conf.sample'))
        shutil.copyfile(os.path.join(PYREX_ROOT, 'poky/meta-poky/conf/bblayers.conf.sample'),
                        os.path.join(template_dir, 'bblayers.conf.sample'))

        test_string = 'set_by_test.%d' % threading.get_ident()

        # Write out a config template that passes along the TEST_ENV variable.
        # The variable will only have the correct value in the container if
        # the template is used
        conf = self.get_config()
        conf['run']['envvars'] += ' TEST_ENV'
        with open(os.path.join(template_dir, 'pyrex.ini.sample'), 'w') as f:
            conf.write(f)
        # Delete the normal pyrex conf file so a new one will be pulled from
        # TEMPLATECONF
        os.unlink(self.pyrex_conf)

        env = os.environ.copy()
        env['TEMPLATECONF'] = os.path.relpath(template_dir, os.path.join(PYREX_ROOT, 'poky'))
        env['TEST_ENV'] = test_string

        s = self.assertPyrexContainerShellCommand(
            'echo $TEST_ENV', env=env, quiet_init=True, capture=True).decode('utf-8').rstrip()
        self.assertEqual(s, test_string)


TEST_IMAGES = ('ubuntu-14.04-base', 'ubuntu-16.04-base', 'ubuntu-18.04-base', 'centos-7-base',
               'ubuntu-14.04-oe', 'ubuntu-16.04-oe', 'ubuntu-18.04-oe')


def add_image_tests():
    for image in TEST_IMAGES:
        (_, _, image_type) = image.split('-')
        self = sys.modules[__name__]

        parent = getattr(self, 'PyrexImageType_' + image_type)

        name = 'PyrexImage_' + re.sub(r'\W', '_', image)
        setattr(self, name, type(name, (parent, unittest.TestCase), {'test_image': image}))


add_image_tests()

if __name__ == "__main__":
    unittest.main()
