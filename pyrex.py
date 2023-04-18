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

import argparse
import configparser
import contextlib
import glob
import grp
import hashlib
import json
import os
import pwd
import re
import resource
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import types

VERSION = "1.8.1"

VERSION_REGEX = re.compile(r"^([0-9]+\.){2}[0-9]+(-.*)?$")
VERSION_TAG_REGEX = re.compile(r"^v([0-9]+\.){2}[0-9]+(-.*)?$")

THIS_SCRIPT = os.path.abspath(__file__)
PYREX_ROOT = os.path.dirname(THIS_SCRIPT)
PYREX_CONFVERSION = "2"
MINIMUM_DOCKER_VERSION = 17


class Config(configparser.ConfigParser):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            interpolation=configparser.ExtendedInterpolation(),
            comment_prefixes=["#"],
            delimiters=["="],
            **kwargs,
        )

        # All keys are case-sensitive
        self.optionxform = lambda option: option


def read_default_config(keep_defaults):
    with open(os.path.join(PYREX_ROOT, "pyrex.ini"), "r") as f:
        line = f.read().replace("@CONFVERSION@", PYREX_CONFVERSION)
        if keep_defaults:
            line = line.replace("%", "")
        else:
            line = line.replace("%", "#")
        return line


def load_config():
    conffile = os.environ.get("PYREXCONFFILE", "")
    if not conffile:
        sys.stderr.write("Pyrex user config file must be defined in $PYREXCONFFILE!\n")
        sys.exit(1)

    # Load the default config, except the version
    user_config = Config()
    user_config.read_string(read_default_config(True))
    del user_config["config"]["confversion"]

    # Load user config file
    with open(conffile, "r") as f:
        user_config.read_file(f)

    # Load environment variables
    try:
        user_config.add_section("env")
    except configparser.DuplicateSectionError:
        pass

    for env in user_config["config"]["envimport"].split():
        if env in os.environ:
            user_config["env"][env] = os.environ[env]

    user_config.add_section("pyrex")
    user_config["pyrex"]["version"] = VERSION
    user_config["pyrex"]["pyrexroot"] = PYREX_ROOT

    try:
        confversion = user_config["config"]["confversion"]
        if confversion != PYREX_CONFVERSION:
            sys.stderr.write(
                "Bad pyrex conf version '%s' in %s\n"
                % (user_config["config"]["confversion"], conffile)
            )
            sys.exit(1)
    except KeyError:
        sys.stderr.write("Cannot find pyrex conf version in %s!\n" % conffile)
        sys.exit(1)

    return user_config


def stop_coverage():
    """
    Helper to stop coverage reporting
    """
    try:
        import coverage

        c = getattr(coverage, "current_coverage")
        if c is not None:
            c.stop()
            c.save()
    except Exception:
        pass


def get_image_id(config, image):
    engine_args = [
        config["config"]["engine"],
        "image",
        "inspect",
        image,
        "--format={{.Id}}",
    ]
    return (
        subprocess.check_output(engine_args, stderr=subprocess.DEVNULL)
        .decode("utf-8")
        .rstrip()
    )


def build_image(config, build_config):
    build_config.setdefault("build", {})

    engine = config["config"]["engine"]

    try:
        (provider, version) = get_engine_info(config)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            textwrap.fill(
                (
                    "Unable to run '%s'. Please make sure you have it installed."
                    + "For installation instructions, see the docker website. Commonly, "
                    + "one of the following is relevant:"
                )
                % engine
            )
        )
        print()
        print("  https://docs.docker.com/install/linux/docker-ce/ubuntu/")
        print("  https://docs.docker.com/install/linux/docker-ce/fedora/")
        print()
        print(
            textwrap.fill(
                "After installing docker, give your login account permission to "
                + "docker commands by running:"
            )
        )
        print()
        print("  sudo usermod -aG docker $USER")
        print()
        print(
            textwrap.fill(
                "After adding your user to the 'docker' group, log out and back in "
                + "so that the new group membership takes effect."
            )
        )
        print()
        print(
            textwrap.fill(
                "To attempt running the build on your native operating system's set "
                + "of packages, use:"
            )
        )
        print()
        print("  export PYREX_USE_CONTAINER=0")
        print("  . init-build-env ...")
        print()
        return None

    if provider is None:
        sys.stderr.write("Could not get container engine version!\n")
        return None

    if provider == "docker" and int(version.split(".")[0]) < MINIMUM_DOCKER_VERSION:
        sys.stderr.write(
            "Docker version is too old (have %s), need >= %d\n"
            % (version, MINIMUM_DOCKER_VERSION)
        )
        return None

    build_config["provider"] = provider

    tag = config["config"]["tag"]

    if config["config"]["buildlocal"] == "1":
        if VERSION_TAG_REGEX.match(tag.split(":")[-1]) is not None:
            sys.stderr.write(
                "Image tag '%s' will overwrite release image tag, which is not what you want\n"
                % tag
            )
            sys.stderr.write("Try changing 'config:pyrextag' to a different value\n")
            return None

        print("Getting container image up to date...")

        (_, _, image_type) = config["config"]["image"].split("-")

        engine_args = shlex.split(config["imagebuild"]["buildcommand"])

        for e in ("http_proxy", "https_proxy", "no_proxy"):
            if e in os.environ:
                engine_args.extend(["--build-arg", "%s=%s" % (e, os.environ[e])])

        env = os.environ.copy()
        for e in shlex.split(config["imagebuild"]["env"]):
            name, val = e.split("=", 1)
            env[name] = val

        try:
            if os.environ.get("PYREX_BUILD_QUIET", "1") == "1" and config[
                "imagebuild"
            ].getboolean("quiet"):
                engine_args.append("-q")
                build_config["build"]["buildid"] = (
                    subprocess.check_output(engine_args, env=env)
                    .decode("utf-8")
                    .rstrip()
                )
            else:
                subprocess.check_call(engine_args, env=env)
                build_config["build"]["buildid"] = get_image_id(config, tag)

            build_config["build"]["runid"] = build_config["build"]["buildid"]

        except subprocess.CalledProcessError:
            return None

        build_config["build"]["buildhash"] = get_build_hash(build_config)
    else:
        registry = config["config"].get("registry")
        if registry:
            if not registry.endswith("/"):
                registry = registry + "/"
            tag = registry + tag

        try:
            # Try to get the image This will fail if the image doesn't
            # exist locally
            build_config["build"]["buildid"] = get_image_id(config, tag)
        except subprocess.CalledProcessError:
            try:
                engine_args = [engine, "pull", tag]
                subprocess.check_call(engine_args)

                build_config["build"]["buildid"] = get_image_id(config, tag)
            except subprocess.CalledProcessError:
                return None

        build_config["build"]["runid"] = tag

    return build_config


def get_build_hash(config):
    # Docker doesn't currently have any sort of "dry-run" mechanism that could
    # be used to determine if the Dockerfile has changed and needs a rebuild.
    # (See https://github.com/moby/moby/issues/38101).
    #
    # Until one is added, we use a simple hash of the files in the pyrex
    # "image" folder to determine when it is out of date.

    h = hashlib.sha256()
    for (root, dirs, files) in os.walk(os.path.join(PYREX_ROOT, "image")):
        # Process files and directories in alphabetical order so that hashing
        # is consistent
        dirs.sort()
        files.sort()

        for f in files:
            # Skip files that aren't interesting. This way any temporary editor
            # files are ignored
            if not (
                f.endswith(".py")
                or f.endswith(".sh")
                or f.endswith(".patch")
                or f == "Dockerfile"
            ):
                continue

            with open(os.path.join(root, f), "rb") as f:
                b = f.read(4096)
                while b:
                    h.update(b)
                    b = f.read(4096)

    return h.hexdigest()


def get_engine_info(config):
    engine = config["config"]["engine"]
    output = subprocess.check_output([engine, "--version"]).decode("utf-8")
    m = re.match(r"(?P<provider>\S+) +version +(?P<version>[^\s,]+)", output)
    if m is not None:
        return (m.group("provider").lower(), m.group("version"))
    return (None, None)


def get_subid_length(filename, name):
    r = re.compile(r"{}:\d+:(\d+)".format(re.escape(name)))

    with open(filename, "r") as f:
        for line in f:
            m = r.match(line)
            if m is not None:
                return int(m.group(1))

    return 0


def parse_bind_options(bind):
    options = types.SimpleNamespace(optional=False, readonly=False)
    bad_options = []

    if "," in bind:
        s = bind.split(",")
        bind = s[0]
        for opt in s[1:]:
            if hasattr(options, opt):
                setattr(options, opt, True)
            else:
                bad_options.append(opt)

    return bind, options, bad_options


def prep_container(
    config,
    build_config,
    command,
    *,
    extra_env={},
    preserve_env=[],
    extra_bind=[],
    allow_test_config=False,
    extra_envvars=[],
):
    runid = build_config["build"]["runid"]

    if not runid:
        print(
            "Container was not enabled when the environment was setup. Cannot use it now!"
        )
        return []

    engine = config["config"]["engine"]

    try:
        buildid = get_image_id(config, runid)
    except subprocess.CalledProcessError as e:
        print("Cannot verify container image: %s\n" % e.output)
        return []

    if buildid != build_config["build"]["buildid"]:
        sys.stderr.write(
            "WARNING: buildid for container image %s has changed\n" % runid
        )

    if config["config"]["buildlocal"] == "1" and build_config["build"][
        "buildhash"
    ] != get_build_hash(config):
        sys.stderr.write(
            "WARNING: The container image source has changed and should be rebuilt.\n"
            "Try running: 'pyrex-rebuild'\n"
        )

    uid = os.getuid()
    gid = os.getgid()
    username = pwd.getpwuid(uid).pw_name
    groupname = grp.getgrgid(gid).gr_name

    groups = ["%d:%s" % (gid, groupname)]

    for group in grp.getgrall():
        if group.gr_name == groupname:
            continue
        if username in group.gr_mem:
            groups.append("%d:%s" % (group.gr_gid, group.gr_name))

    # These are "hidden" keys in pyrex.ini that aren't publicized, and
    # are primarily used for testing. Use they at your own risk, they
    # may change
    if allow_test_config:
        uid = int(config["run"].get("uid", uid))
        username = config["run"].get("username") or username
        groups = config["run"].get("groups", "").split() or groups

    command_prefix = config["run"].get("commandprefix", "").splitlines()

    engine_args = [
        engine,
        "run",
        "--rm",
        "-i",
        "-e",
        "PYREX_USER=%s" % username,
        "-e",
        "PYREX_UID=%d" % uid,
        "-e",
        "PYREX_GROUPS=%s" % " ".join(groups),
        "-e",
        "PYREX_HOME=%s" % os.environ["HOME"],
        "-e",
        "PYREX_COMMAND_PREFIX=%s" % " ".join(command_prefix),
        "--workdir",
        os.getcwd(),
    ]

    # Use host networking. This is mainly to support simple integration
    # of IceCream's daemon.
    #
    # Use a bind-mounted copy of the host's resolv.conf to ensure that
    # hostname lookup in the container stays in sync as the host's networking
    # configuration changes on-the-fly.
    #
    # Docker documentation at [1] indicates that the dns settings are
    # inherited from the Docker daemon itself, but if you launch
    # your vpn (hence changing /etc/resolv.conf) you will have a mismatch
    # causing an issue.
    #
    # Further evidence supporting explicitly bind mounting /etc/resolv.conf
    # can be seen at [2]:
    #
    # [1] https://docs.docker.com/config/containers/container-networking/
    # [2] https://github.com/docker/docker-ce/blob/master/components/cli/docs/reference/commandline/service_create.md
    engine_args.extend(
        [
            "--net=host",
            "--mount",
            "type=bind,src=/etc/resolv.conf,dst=/etc/resolv.conf",
        ]
    )

    container_envvars = [
        "PYREX_CLEANUP_EXIT_WAIT",
        "PYREX_CLEANUP_LOG_FILE",
        "PYREX_CLEANUP_LOG_LEVEL",
        "TINI_VERBOSITY",
        "TERM",
    ]

    if build_config["provider"] == "podman":
        uid_length = get_subid_length("/etc/subuid", username)
        if uid_length < 1:
            sys.stderr.write("subuid name space is too small\n")
            sys.exit(1)

        gid_length = get_subid_length("/etc/subgid", username)
        if gid_length < 1:
            sys.stderr.write("subgid name space is too small\n")
            sys.exit(1)

        (soft, hard) = resource.getrlimit(resource.RLIMIT_NOFILE)

        engine_args.extend(
            [
                "--security-opt",
                "label=disable",
                # Fix up the UID/GID mapping so that the actual UID/GID
                # inside the container maps to their actual UID/GID
                # outside the container. Note that all offsets outside
                # the container are relative to the start of the users
                # subuid/subgid range.
                # Map UID 0 up the actual user ID inside the container
                # to the users subuid
                "--uidmap",
                "0:1:%d" % uid,
                # Map the users actual UID inside the container to 0 in
                # the users subuid namespace. The "root" user in the
                # subuid namespace is special and maps to the users
                # actual UID outside the namespace
                "--uidmap",
                "%d:0:1" % uid,
                # Map the remaining UIDs after the actual user ID to
                # continue using the users subuid range
                "--uidmap",
                "%d:%d:%d" % (uid + 1, uid + 1, uid_length - uid),
                # Do the same for the GID
                "--gidmap",
                "0:1:%d" % gid,
                "--gidmap",
                "%d:0:1" % gid,
                "--gidmap",
                "%d:%d:%d" % (gid + 1, gid + 1, gid_length - gid),
                # Set the rlimit for the number of open files to be the maximum
                # hard limit, otherwise the hard limit will be pinned to the
                # current soft limit (usually 1024), which is too low. The
                # fuse-overlayfs driver does this from version 0.3 onward, see:
                # https://github.com/containers/fuse-overlayfs/commit/d3729baa932bae444586ce9343bae59147ab2efb
                "--ulimit",
                "nofile=%d:%d" % (hard, hard),
            ]
        )

    # Run the container with a TTY if this script was run in a tty
    if os.isatty(1):
        engine_args.append("-t")

    # Configure binds
    binds = (
        config["run"]["bind"].split()
        + os.environ.get("PYREX_CONFIG_BIND", "").split()
        + extra_bind
    )
    for b in set(binds):
        b, options, bad_options = parse_bind_options(b)
        if bad_options:
            print("Error: bad option(s) '%s' for bind %s" % (" ".join(bad_options), b))
            return []

        if not os.path.exists(b):
            if options.optional:
                continue
            print("Error: bind source path {b} does not exist".format(b=b))
            return []

        engine_args.extend(
            [
                "--mount",
                "type=bind,src={b},dst={b}{ro}".format(
                    b=b, ro=",readonly" if options.readonly else ""
                ),
            ]
        )

    container_envvars.extend(config["run"]["envvars"].split())
    container_envvars.extend(extra_envvars)

    # Pass along extra environment variables
    for e in ("BB_ENV_EXTRAWHITE", "BB_ENV_PASSTHROUGH_ADDITIONS"):
        if e in os.environ:
            engine_args.extend(["-e", e])
            container_envvars.extend(os.environ[e].split())

    # Pass environment variables. If a variable passed with an argument
    # "-e VAR" is not set in the parent environment, podman passes an
    # empty value, where as Docker doesn't pass it at all. For
    # consistency, manually check if the variables exist before passing
    # them.
    env_sock_proxy = config["run"]["envsockproxy"].split()
    for name in set(container_envvars + preserve_env):
        if name not in os.environ:
            continue

        val = os.environ[name]

        if name in env_sock_proxy:
            socket = os.path.realpath(val)
            if not os.path.exists(socket):
                print("Warning: {} {} does not exist".format(name, socket))
            else:
                dest = "/tmp/pyrex/sock/%s-%s" % (username, name)
                engine_args.extend(
                    [
                        "--mount",
                        "type=bind,src=%s,dst=%s" % (socket, dest),
                        "-e",
                        "%s=%s" % (name, dest),
                    ]
                )
        else:
            engine_args.extend(["-e", name])

    for k, v in extra_env.items():
        engine_args.extend(["-e", "%s=%s" % (k, v)])

    engine_args.extend(shlex.split(config["run"].get("args", "")))

    engine_args.append("--")
    engine_args.append(runid)
    engine_args.extend(command)
    return engine_args


def create_shims(config, build_config, buildconf):
    shimdir = os.path.join(build_config["tempdir"], "bin")

    try:
        shutil.rmtree(shimdir)
    except Exception:
        pass
    os.makedirs(shimdir)

    # Write out run convenience command
    runfile = os.path.join(shimdir, "pyrex-run")
    with open(runfile, "w") as f:
        f.write(
            textwrap.dedent(
                """\
            #! /bin/sh
            exec {this_script} run {conffile} -- "$@"
            """.format(
                    this_script=THIS_SCRIPT, conffile=buildconf
                )
            )
        )
    os.chmod(runfile, stat.S_IRWXU)

    # write out config convenience command
    configcmd = os.path.join(shimdir, "pyrex-config")
    with open(configcmd, "w") as f:
        f.write(
            textwrap.dedent(
                """\
            #! /bin/sh
            exec {this_script} config {conffile} "$@"
            """.format(
                    this_script=THIS_SCRIPT, conffile=buildconf
                )
            )
        )
    os.chmod(configcmd, stat.S_IRWXU)

    # write out the shim file
    shimfile = os.path.join(shimdir, "exec-shim-pyrex")
    with open(shimfile, "w") as f:
        f.write(
            textwrap.dedent(
                """\
            #! /bin/sh
            exec {runfile} "$(basename $0)" "$@"
            """.format(
                    runfile=runfile
                )
            )
        )
    os.chmod(shimfile, stat.S_IRWXU)

    # write out the shell convenience command
    shellfile = os.path.join(shimdir, "pyrex-shell")
    with open(shellfile, "w") as f:
        f.write(
            textwrap.dedent(
                """\
            #! /bin/sh
            exec {runfile} {shell} "$@"
            """.format(
                    runfile=runfile, shell=build_config["container"]["shell"]
                )
            )
        )
    os.chmod(shellfile, stat.S_IRWXU)

    # write out image rebuild command
    rebuildfile = os.path.join(shimdir, "pyrex-rebuild")
    with open(rebuildfile, "w") as f:
        f.write(
            textwrap.dedent(
                """\
            #! /bin/sh
            exec {this_script} rebuild {conffile}
            """.format(
                    this_script=THIS_SCRIPT, conffile=buildconf
                )
            )
        )
    os.chmod(rebuildfile, stat.S_IRWXU)

    # Create shims
    user_commands = config["config"].get("commands")
    if user_commands:
        user_commands = user_commands.split()
        command_globs = [c for c in user_commands if not c.startswith("!")]
        nopyrex_globs = [c[1:] for c in user_commands if c.startswith("!")]
    else:
        command_globs = build_config["container"].get("commands", {}).get("include", {})
        nopyrex_globs = build_config["container"].get("commands", {}).get("exclude", {})

    commands = set()

    def add_commands(globs, target):
        nonlocal commands

        for g in globs:
            for cmd in glob.iglob(g):
                norm_cmd = os.path.normpath(cmd)
                if (
                    norm_cmd not in commands
                    and os.path.isfile(cmd)
                    and os.access(cmd, os.X_OK)
                ):
                    commands.add(norm_cmd)
                    name = os.path.basename(cmd)

                    os.symlink(target.format(command=cmd), os.path.join(shimdir, name))

    add_commands(nopyrex_globs, "{command}")
    add_commands(command_globs, "exec-shim-pyrex")

    return shimdir


def main():
    def capture(args):
        config = load_config()
        build_config = build_image(config, {})
        if build_config is None:
            return 1

        with tempfile.NamedTemporaryFile(mode="r") as f:
            env_args = {k: v for (k, v) in args.arg}
            env_args["PYREX_CAPTURE_DEST"] = f.name

            # Startup script are only supposed to run after the initial capture
            env_args["PYREX_SKIP_STARTUP"] = "1"

            engine_args = prep_container(
                config,
                build_config,
                ["/usr/libexec/pyrex/capture"] + args.init,
                extra_env=env_args,
                preserve_env=args.env,
                extra_bind=[f.name],
                extra_envvars=config["capture"]["envvars"].split(),
            )

            if not engine_args:
                return 1

            p = subprocess.run(engine_args)
            if p.returncode:
                return 1

            capture = json.load(f)

        build_config["run"] = capture["run"]
        build_config["container"] = capture["container"]
        build_config["tempdir"] = capture["tempdir"]

        try:
            os.makedirs(build_config["tempdir"])
        except Exception:
            pass

        buildconf = os.path.join(build_config["tempdir"], "build.json")

        build_config["shimdir"] = create_shims(config, build_config, buildconf)

        with open(buildconf, "w") as f:
            json.dump(build_config, f)

        def write_cmd(c):
            os.write(args.fd, c.encode("utf-8"))
            os.write(args.fd, "\n".encode("utf-8"))

        write_cmd("PATH=%s:$PATH" % build_config["shimdir"])
        user_export = capture["user"].get("export", {})
        for name in sorted(user_export.keys()):
            write_cmd('export %s="%s"' % (name, user_export[name]))
        if capture["user"].get("cwd"):
            write_cmd('cd "%s"' % capture["user"]["cwd"])
        return 0

    def rebuild(args):
        config = load_config()
        with open(args.buildconf, "r") as f:
            build_config = json.load(f)

        build_config = build_image(config, build_config)

        if build_config is None:
            return 1

        build_config["shimdir"] = create_shims(config, build_config, args.buildconf)

        with open(args.buildconf, "w") as f:
            json.dump(build_config, f)

        return 0

    def run(args):
        config = load_config()
        with open(args.buildconf, "r") as f:
            build_config = json.load(f)

        engine_args = prep_container(
            config,
            build_config,
            ["/usr/libexec/pyrex/run"] + args.command,
            extra_env=build_config.get("run", {}).get("env", {}),
            allow_test_config=True,
        )

        if not engine_args:
            sys.exit(1)

        stop_coverage()
        os.execvp(engine_args[0], engine_args)
        print("Cannot exec container!")
        sys.exit(1)

    def config_get(args):
        config = load_config()
        try:
            (section, name) = args.var.split(":")
        except ValueError:
            sys.stderr.write('"%s" is not of the form SECTION:NAME\n' % args.var)
            return 1

        try:
            val = config[section][name]
        except KeyError:
            return 1

        print(val)
        return 0

    def mkconfig(args):
        @contextlib.contextmanager
        def get_output_file():
            if args.output == "-":
                yield sys.stdout
            else:
                with open(args.output, "w" if args.force else "x") as f:
                    yield f
                print(os.path.abspath(args.output))

        try:
            with get_output_file() as f:
                f.write(read_default_config(False))
        except FileExistsError:
            sys.stderr.write("Refusing to overwrite existing file '%s'\n" % args.output)
            return 1

        return 0

    subparser_args = {}
    if sys.version_info >= (3, 7, 0):
        subparser_args["required"] = True

    parser = argparse.ArgumentParser(description="Pyrex Setup Argument Parser")
    subparsers = parser.add_subparsers(
        title="subcommands",
        description="Setup subcommands",
        dest="subcommand",
        **subparser_args,
    )

    capture_parser = subparsers.add_parser(
        "capture", help="Capture OE init environment"
    )
    capture_parser.add_argument("fd", help="Output file descriptor", type=int)
    capture_parser.add_argument(
        "-a",
        "--arg",
        nargs=2,
        metavar=("NAME", "VALUE"),
        action="append",
        default=[],
        help="Set additional arguments as environment variable when capturing",
    )
    capture_parser.add_argument(
        "-e",
        "--env",
        action="append",
        default=[],
        help="Pass additional environment variables if present in parent shell",
    )
    capture_parser.add_argument(
        "init", nargs="*", help="Initialization arguments", default=[]
    )
    capture_parser.set_defaults(func=capture)

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild Pyrex image")
    rebuild_parser.add_argument("buildconf", help="Pyrex build config file")
    rebuild_parser.set_defaults(func=rebuild)

    run_parser = subparsers.add_parser("run", help="Run command in Pyrex")
    run_parser.add_argument("buildconf", help="Pyrex build config file")
    run_parser.add_argument("command", nargs="*", help="Command to execute", default=[])
    run_parser.set_defaults(func=run)

    config_parser = subparsers.add_parser("config", help="Pyrex configuration")
    config_parser.add_argument("buildconf", help="Pyrex build config file")
    config_subparsers = config_parser.add_subparsers(
        title="subcommands",
        description="Config subcommands",
        dest="config_subcommand",
        **subparser_args,
    )

    config_get_parser = config_subparsers.add_parser(
        "get", help="Get Pyrex config value"
    )
    config_get_parser.add_argument(
        "var", metavar="SECTION:NAME", help="Config variable to get"
    )
    config_get_parser.set_defaults(func=config_get)

    mkconfig_parser = subparsers.add_parser(
        "mkconfig", help="Create a default Pyrex configuration"
    )
    mkconfig_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )
    mkconfig_parser.add_argument(
        "output",
        default="-",
        nargs="?",
        help="Output file. Use '-' for standard out. Default is %(default)s",
    )
    mkconfig_parser.set_defaults(func=mkconfig)

    args = parser.parse_args()

    func = getattr(args, "func", None)
    if not func:
        parser.print_usage()
        print("error: subcommand required")
        sys.exit(1)

    sys.exit(func(args))


if __name__ == "__main__":
    main()
