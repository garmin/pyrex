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
import argparse
import os
import shutil
import sys
import subprocess
import re
import pwd
import grp
import shlex
import glob
import textwrap
import stat
import hashlib

VERSION = '0.0.3'

VERSION_REGEX = re.compile(r'^([0-9]+\.){2}[0-9]+(-.*)?$')
VERSION_TAG_REGEX = re.compile(r'^v([0-9]+\.){2}[0-9]+(-.*)?$')

THIS_SCRIPT = os.path.basename(__file__)
PYREX_CONFVERSION = '1'
MINIMUM_DOCKER_VERSION = 17


class Config(configparser.ConfigParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, interpolation=configparser.ExtendedInterpolation(),
                         comment_prefixes=['#'], delimiters=['='], **kwargs)

        # All keys are case-sensitive
        self.optionxform = lambda option: option

    def getrawdict(self):
        """returns a dictionary that doesn't have any interpolation. Useful for
        merging configs together"""
        return {section: values for (section, values) in self.items(raw=True)}


def read_default_config(keep_defaults):
    with open(os.path.join(os.path.dirname(__file__), 'pyrex.ini'), 'r') as f:
        line = f.read().replace('@CONFVERSION@', PYREX_CONFVERSION)
        if keep_defaults:
            line = line.replace('%', '')
        else:
            line = line.replace('%', '#')
        return line


def load_configs(conffile):
    # Load the build time config file
    build_config = Config()
    with open(conffile, 'r') as f:
        build_config.read_file(f)

    # Load the default config, except the version
    user_config = Config()
    user_config.read_string(read_default_config(True))
    del user_config['config']['confversion']

    # Load user config file
    with open(build_config['build']['userconfig'], 'r') as f:
        user_config.read_file(f)

    # Merge build config into user config
    user_config.read_dict(build_config.getrawdict())

    # Load environment variables
    try:
        user_config.add_section('env')
    except configparser.DuplicateSectionError:
        pass

    for env in user_config['config']['envimport'].split():
        if env in os.environ:
            user_config['env'][env] = os.environ[env]

    user_config.add_section('pyrex')
    user_config['pyrex']['version'] = VERSION

    return user_config, build_config


def stop_coverage():
    """
    Helper to stop coverage reporting
    """
    try:
        import coverage
        c = getattr(coverage, 'current_coverage')
        if c is not None:
            c.stop()
            c.save()
    except Exception:
        pass


def get_image_id(config, image):
    docker_args = [config['config']['dockerpath'], 'image', 'inspect', image, '--format={{ .Id }}']
    return subprocess.check_output(docker_args, stderr=subprocess.DEVNULL).decode('utf-8').rstrip()


def use_docker(config):
    return os.environ.get('PYREX_DOCKER', config['run']['enable']) == '1'


def copy_templateconf(conffile):
    template = os.environ['PYREXCONFTEMPLATE']

    if os.path.isfile(template):
        shutil.copyfile(template, conffile)
    else:
        with open(conffile, 'w') as f:
            f.write(read_default_config(False))


def check_confversion(user_config, version_required=False):
    try:
        confversion = user_config['config']['confversion']
        if confversion != PYREX_CONFVERSION:
            sys.stderr.write("Bad pyrex conf version '%s'\n" % user_config['config']['confversion'])
            return False
        return True
    except KeyError:
        if version_required:
            sys.stderr.write("Cannot find pyrex conf version!\n")
            return False
        raise


def get_build_hash(config):
    # Docker doesn't currently have any sort of "dry-run" mechanism that could
    # be used to determine if the dockerfile has changed and needs a rebuild.
    # (See https://github.com/moby/moby/issues/38101).
    #
    # Until one is added, we use a simple hash of the files in the pyrex
    # "docker" folder to determine when it is out of date.

    h = hashlib.sha256()
    for (root, dirs, files) in os.walk(os.path.join(config['build']['pyrexroot'], 'docker')):
        # Process files and directories in alphabetical order so that hashing
        # is consistent
        dirs.sort()
        files.sort()

        for f in files:
            # Skip files that aren't interesting. This way any temporary editor
            # files are ignored
            if not (f.endswith('.py') or f.endswith('.sh') or f.endswith('.patch') or f == 'Dockerfile'):
                continue

            with open(os.path.join(root, f), 'rb') as f:
                b = f.read(4096)
                while b:
                    h.update(b)
                    b = f.read(4096)

    return h.hexdigest()


def main():
    def capture(args):
        builddir = os.environ['BUILDDIR']
        conffile = os.environ.get('PYREXCONFFILE', '')
        oeinit = os.environ['PYREX_OEINIT']

        user_config = Config()

        if not conffile:
            conffile = os.path.abspath(os.path.join(builddir, 'conf', 'pyrex.ini'))

            if not os.path.isfile(conffile):
                copy_templateconf(conffile)

            user_config.read(conffile)

            try:
                if not check_confversion(user_config):
                    return 1
            except KeyError:
                sys.stderr.write("Cannot find pyrex conf version! Restoring from template\n")

                copy_templateconf(conffile)

                user_config = Config()

        user_config.read(conffile)
        if not check_confversion(user_config, True):
            return 1

        # Setup the build configuration
        build_config = Config()

        build_config['build'] = {}
        build_config['build']['builddir'] = builddir
        build_config['build']['oeroot'] = os.environ['PYREX_OEROOT']
        build_config['build']['oeinit'] = oeinit
        build_config['build']['pyrexroot'] = os.environ['PYREX_ROOT']
        build_config['build']['initcommand'] = ' '.join(shlex.quote(a) for a in [oeinit] + args.init)
        build_config['build']['initdir'] = os.environ['PYREX_OEINIT_DIR']
        build_config['build']['userconfig'] = conffile

        # Merge the build config into the user config (so that interpolation works)
        user_config.read_dict(build_config.getrawdict())

        try:
            os.makedirs(user_config['config']['tempdir'])
        except Exception:
            pass

        build_conffile = os.path.join(user_config['config']['tempdir'], 'build.ini')

        with open(build_conffile, 'w') as f:
            build_config.write(f)

        os.write(args.fd, build_conffile.encode('utf-8'))

        return 0

    def build(args):
        config, build_config = load_configs(args.conffile)

        if use_docker(config):
            docker_path = config['config']['dockerpath']

            # Check minimum docker version
            try:
                output = subprocess.check_output([docker_path, '--version']).decode('utf-8')
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(textwrap.fill(("Unable to run '%s' as docker. Please make sure you have it installed." +
                                     "For installation instructions, see the docker website. Commonly, " +
                                     "one of the following is relevant:") % docker_path))
                print()
                print("  https://docs.docker.com/install/linux/docker-ce/ubuntu/")
                print("  https://docs.docker.com/install/linux/docker-ce/fedora/")
                print()
                print(textwrap.fill("After installing docker, give your login account permission to " +
                                    "docker commands by running:"))
                print()
                print("  sudo usermod -aG docker $USER")
                print()
                print(textwrap.fill("After adding your user to the 'docker' group, log out and back in " +
                                    "so that the new group membership takes effect."))
                print()
                print(textwrap.fill("To attempt running the build on your native operating system's set " +
                                    "of packages, use:"))
                print()
                print("  export PYREX_DOCKER=0")
                print("  . init-build-env ...")
                print()
                return 1

            m = re.match(r'.*version +([^\s,]+)', output)
            if m is None:
                sys.stderr.write('Could not get docker version!\n')
                return 1

            version = m.group(1)

            if int(version.split('.')[0]) < MINIMUM_DOCKER_VERSION:
                sys.stderr.write("Docker version is too old (have %s), need >= %d\n" %
                                 (version, MINIMUM_DOCKER_VERSION))
                return 1

            tag = config['config']['tag']

            if config['config']['buildlocal'] == '1':
                if VERSION_TAG_REGEX.match(tag.split(':')[-1]) is not None:
                    sys.stderr.write("Image tag '%s' will overwrite release image tag, which is not what you want\n" %
                                     tag)
                    sys.stderr.write("Try changing 'config:pyrextag' to a different value\n")
                    return 1

                print("Getting Docker image up to date...")

                (_, _, image_type) = config['config']['dockerimage'].split('-')

                docker_args = [docker_path, 'build',
                               '-t', tag,
                               '-f', config['dockerbuild']['dockerfile'],
                               '--network=host',
                               os.path.join(config['build']['pyrexroot'], 'docker'),
                               '--target', 'pyrex-%s' % image_type
                               ]

                if config['config']['registry']:
                    docker_args.extend(['--build-arg', 'MY_REGISTRY=%s/' % config['config']['registry']])

                for e in ('http_proxy', 'https_proxy'):
                    if e in os.environ:
                        docker_args.extend(['--build-arg', '%s=%s' % (e, os.environ[e])])

                if config['dockerbuild'].get('args', ''):
                    docker_args.extend(shlex.split(config['dockerbuild']['args']))

                env = os.environ.copy()
                for e in shlex.split(config['dockerbuild']['env']):
                    name, val = e.split('=', 1)
                    env[name] = val

                try:
                    if os.environ.get('PYREX_DOCKER_BUILD_QUIET',
                                      '1') == '1' and config['dockerbuild'].getboolean('quiet'):
                        docker_args.append('-q')
                        build_config['build']['buildid'] = subprocess.check_output(
                            docker_args, env=env).decode('utf-8').rstrip()
                    else:
                        subprocess.check_call(docker_args, env=env)
                        build_config['build']['buildid'] = get_image_id(config, tag)

                    build_config['build']['runid'] = build_config['build']['buildid']

                except subprocess.CalledProcessError:
                    return 1

                build_config['build']['buildhash'] = get_build_hash(build_config)
            else:
                try:
                    # Try to get the image This will fail if the image doesn't
                    # exist locally
                    build_config['build']['buildid'] = get_image_id(config, tag)
                except subprocess.CalledProcessError:
                    try:
                        docker_args = [docker_path, 'pull', tag]
                        subprocess.check_call(docker_args)

                        build_config['build']['buildid'] = get_image_id(config, tag)
                    except subprocess.CalledProcessError:
                        return 1

                build_config['build']['runid'] = tag
        else:
            print(textwrap.fill("Running outside of Docker. No guarantees are made about your Linux " +
                                "distribution's compatibility with Yocto."))
            print()
            build_config['build']['buildid'] = ''
            build_config['build']['runid'] = ''

        with open(args.conffile, 'w') as f:
            build_config.write(f)

        shimdir = os.path.join(config['config']['tempdir'], 'bin')

        try:
            shutil.rmtree(shimdir)
        except Exception:
            pass
        os.makedirs(shimdir)

        # Write out run convenience command
        runfile = os.path.join(shimdir, 'pyrex-run')
        with open(runfile, 'w') as f:
            f.write(textwrap.dedent('''\
                #! /bin/sh
                exec {pyrexroot}/{this_script} run {conffile} -- "$@"
                '''.format(pyrexroot=config['build']['pyrexroot'], conffile=args.conffile,
                           this_script=THIS_SCRIPT)))
        os.chmod(runfile, stat.S_IRWXU)

        # Write out config convenience command
        configcmd = os.path.join(shimdir, 'pyrex-config')
        with open(configcmd, 'w') as f:
            f.write(textwrap.dedent('''\
                #! /bin/sh
                exec {pyrexroot}/{this_script} config {conffile} "$@"
                '''.format(pyrexroot=config['build']['pyrexroot'], conffile=args.conffile,
                           this_script=THIS_SCRIPT)))
        os.chmod(configcmd, stat.S_IRWXU)

        # Write out the shim file
        shimfile = os.path.join(shimdir, 'exec-shim-pyrex')
        with open(shimfile, 'w') as f:
            f.write(textwrap.dedent('''\
                #! /bin/sh
                exec {runfile} "$(basename $0)" "$@"
                '''.format(runfile=runfile)))
        os.chmod(shimfile, stat.S_IRWXU)

        # Write out the shell convenience command
        shellfile = os.path.join(shimdir, 'pyrex-shell')
        with open(shellfile, 'w') as f:
            f.write(textwrap.dedent('''\
                #! /bin/sh
                exec {runfile} {shell} "$@"
                '''.format(runfile=runfile, shell=config['config']['shell'])))
        os.chmod(shellfile, stat.S_IRWXU)

        # Write out image rebuild command
        rebuildfile = os.path.join(shimdir, 'pyrex-rebuild')
        with open(rebuildfile, 'w') as f:
            f.write(textwrap.dedent('''\
                #! /bin/sh
                exec {pyrexroot}/{this_script} build {conffile}
                '''.format(pyrexroot=config['build']['pyrexroot'], conffile=args.conffile,
                           this_script=THIS_SCRIPT)))
        os.chmod(rebuildfile, stat.S_IRWXU)

        command_globs = [g for g in config['config']['commands'].split() if g]
        nopyrex_globs = [g for g in config['config']['commands_nopyrex'].split() if g]

        commands = set()

        def add_commands(globs, target):
            nonlocal commands

            for g in globs:
                for cmd in glob.iglob(g):
                    norm_cmd = os.path.normpath(cmd)
                    if norm_cmd not in commands and os.path.isfile(cmd) and os.access(cmd, os.X_OK):
                        commands.add(norm_cmd)
                        name = os.path.basename(cmd)

                        os.symlink(target.format(command=cmd), os.path.join(shimdir, name))

        add_commands(nopyrex_globs, '{command}')
        add_commands(command_globs, 'exec-shim-pyrex')
        return 0

    def run(args):
        config, _ = load_configs(args.conffile)

        runid = config['build']['runid']

        if use_docker(config):
            if not runid:
                print("Docker was not enabled when the environment was setup. Cannot use it now!")
                return 1

            docker_path = config['config']['dockerpath']

            try:
                buildid = get_image_id(config, runid)
            except subprocess.CalledProcessError as e:
                print("Cannot verify docker image: %s\n" % e.output)
                return 1

            if buildid != config['build']['buildid']:
                sys.stderr.write("WARNING: buildid for docker image %s has changed\n" % runid)

            if config['config']['buildlocal'] == '1' and config['build']['buildhash'] != get_build_hash(config):
                sys.stderr.write("WARNING: The docker image source has changed and should be rebuilt.\n"
                                 "Try running: 'pyrex-rebuild'\n")

            # These are "hidden" keys in pyrex.ini that aren't publicized, and
            # are primarily used for testing. Use they at your own risk, they
            # may change
            uid = int(config['run'].get('uid', os.getuid()))
            gid = int(config['run'].get('gid', os.getgid()))
            username = config['run'].get('username') or pwd.getpwuid(uid).pw_name
            groupname = config['run'].get('groupname') or grp.getgrgid(gid).gr_name
            init_command = config['run'].get('initcommand', config['build']['initcommand'])
            init_dir = config['run'].get('initdir', config['build']['initdir'])

            command_prefix = config['run'].get('commandprefix', '').splitlines()

            docker_args = [docker_path, 'run',
                           '--rm',
                           '-i',
                           '--net=host',
                           '-e', 'PYREX_USER=%s' % username,
                           '-e', 'PYREX_UID=%d' % uid,
                           '-e', 'PYREX_GROUP=%s' % groupname,
                           '-e', 'PYREX_GID=%d' % gid,
                           '-e', 'PYREX_HOME=%s' % os.environ['HOME'],
                           '-e', 'PYREX_INIT_COMMAND=%s' % init_command,
                           '-e', 'PYREX_INIT_DIR=%s' % init_dir,
                           '-e', 'PYREX_CLEANUP_EXIT_WAIT',
                           '-e', 'PYREX_CLEANUP_LOG_FILE',
                           '-e', 'PYREX_CLEANUP_LOG_LEVEL',
                           '-e', 'PYREX_COMMAND_PREFIX=%s' % ' '.join(command_prefix),
                           '-e', 'TINI_VERBOSITY',
                           '--workdir', os.getcwd(),
                           ]

            # Run the docker image with a TTY if this script was run in a tty
            if os.isatty(1):
                docker_args.extend(['-t', '-e', 'TERM=%s' % os.environ['TERM']])

            # Configure binds
            for b in set(config['run']['bind'].split()):
                if not os.path.exists(b):
                    print('Error: bind source path {b} does not exist'.format(b=b))
                    continue
                docker_args.extend(['--mount', 'type=bind,src={b},dst={b}'.format(b=b)])

            # Pass environment variables
            for e in config['run']['envvars'].split():
                docker_args.extend(['-e', e])

            # Special case: Make the user SSH authentication socket available in Docker
            if 'SSH_AUTH_SOCK' in os.environ:
                socket = os.path.realpath(os.environ['SSH_AUTH_SOCK'])
                if not os.path.exists(socket):
                    print('Warning: SSH_AUTH_SOCK {} does not exist'.format(socket))
                else:
                    docker_args.extend([
                        '--mount', 'type=bind,src=%s,dst=/tmp/%s-ssh-agent-sock' % (socket, username),
                        '-e', 'SSH_AUTH_SOCK=/tmp/%s-ssh-agent-sock' % username,
                    ])

            # Pass along BB_ENV_EXTRAWHITE and anything it has whitelisted
            if 'BB_ENV_EXTRAWHITE' in os.environ:
                docker_args.extend(['-e', 'BB_ENV_EXTRAWHITE'])
                for e in os.environ['BB_ENV_EXTRAWHITE'].split():
                    docker_args.extend(['-e', e])

            docker_args.extend(shlex.split(config['run'].get('args', '')))

            docker_args.append('--')
            docker_args.append(runid)
            docker_args.extend(args.command)

            stop_coverage()

            os.execvp(docker_args[0], docker_args)

            print("Cannot exec docker!")
            sys.exit(1)
        else:
            startup_args = [os.path.join(config['build']['pyrexroot'], 'docker', 'startup.sh')]
            startup_args.extend(args.command)

            env = os.environ.copy()
            env['PYREX_INIT_COMMAND'] = config['build']['initcommand']
            env['PYREX_INIT_DIR'] = config['build']['initdir']

            stop_coverage()

            os.execve(startup_args[0], startup_args, env)

            print("Cannot exec startup script")
            sys.exit(1)

    def env(args):
        config, _ = load_configs(args.conffile)

        def write_cmd(c):
            os.write(args.fd, c.encode('utf-8'))
            os.write(args.fd, '\n'.encode('utf-8'))

        write_cmd('PATH=%s:${PATH}' % os.path.join(config['config']['tempdir'], 'bin'))
        write_cmd('cd "%s"' % config['build']['builddir'])
        return 0

    def config_get(args):
        config, _ = load_configs(args.conffile)

        try:
            (section, name) = args.var.split(':')
        except ValueError:
            sys.stderr.write('"%s" is not of the form SECTION:NAME\n' % args.var)
            return 1

        try:
            val = config[section][name]
        except KeyError:
            return 1

        print(val)
        return 0

    subparser_args = {}
    if sys.version_info >= (3, 7, 0):
        subparser_args['required'] = True

    parser = argparse.ArgumentParser(description='Pyrex Setup Argument Parser')
    subparsers = parser.add_subparsers(title='subcommands', description='Setup subcommands', dest='subcommand',
                                       **subparser_args)

    capture_parser = subparsers.add_parser('capture', help='Capture OE init environment')
    capture_parser.add_argument('fd', help='Output file descriptor', type=int)
    capture_parser.add_argument('init', nargs='*', help='Initialization arguments', default=[])
    capture_parser.set_defaults(func=capture)

    build_parser = subparsers.add_parser('build', help='Build Pyrex image')
    build_parser.add_argument('conffile', help='Pyrex config file')
    build_parser.set_defaults(func=build)

    run_parser = subparsers.add_parser('run', help='Run command in Pyrex')
    run_parser.add_argument('conffile', help='Pyrex config file')
    run_parser.add_argument('command', nargs='*', help='Command to execute', default=[])
    run_parser.set_defaults(func=run)

    env_parser = subparsers.add_parser('env', help='Setup Pyrex environment')
    env_parser.add_argument('conffile', help='Pyrex config file')
    env_parser.add_argument('fd', help='Output file descriptor', type=int)
    env_parser.set_defaults(func=env)

    config_parser = subparsers.add_parser('config', help='Pyrex configuration')
    config_parser.add_argument('conffile', help='Pyrex config file')
    config_subparsers = config_parser.add_subparsers(title='subcommands', description='Config subcommands',
                                                     dest='config_subcommand', **subparser_args)

    config_get_parser = config_subparsers.add_parser('get', help='Get Pyrex config value')
    config_get_parser.add_argument('var', metavar='SECTION:NAME', help='Config variable to get')
    config_get_parser.set_defaults(func=config_get)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
