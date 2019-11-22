# Pyrex
Containerize your bitbake

[![Build Status](https://travis-ci.com/garmin/pyrex.svg?branch=master)](https://travis-ci.com/garmin/pyrex)
[![Coverage Status](https://coveralls.io/repos/github/garmin/pyrex/badge.svg?branch=master)](https://coveralls.io/github/garmin/pyrex?branch=master)

## What is Pyrex?
At its core, Pyrex is an attempt to provided a consistent environment in which
developers can run Yocto and bitbake commands. Pyrex is targeted at development
teams who want are doing interactive development with Yocto (although, Pyrex
doesn't aim to be a full development environment, see below), and as such makes
some different design decisions than other containerized solutions like
[CROPS][].

Pyrex works by setting up a container image in which to run commands, then
"trapping" the commands such that when the user executes the command in their
shell, it is (hopefully) transparently executed inside the container instead.

## What *isn't* Pyrex?
Pyrex isn't designed to be a complete Yocto IDE. The intention of Pyrex is not
to run `vim`, `emacs` etc. and faithfully reproduce your development PC
environment while also creating a reproducible build environment. Instead,
Pyrex is designed to allow developers the freedom to use whatever tools and
editors they want, run whatever distro they want, and configure their system
how they want, but still run the actual Yocto build commands in a controlled
environment.

Note that there are some provisions in the Pyrex image for running utilities
tied into bitbake that can't easily be run any other way. For example, the
commands `bitbake -c devshell`, `bitbake -c devpyshell`, and `bitbake -c
menuconfig` (or any other commands that run in [OE_TERMINAL][]) are all
supported since there is no other way to easily run them outside the bitbake
environment.

Note that because of this philosophy, it may not be possible to run some
graphical tools such as `hob` when using Pyrex.

## When should you use Pyrex?
There are a number of situations where Pyrex can be very useful:

1. If you have multiple developers building on development machines with
   different setups (e.g. different distros). In these cases, Pyrex can help
   ensure that builds are consistent between different developers.
2. You have to build multiple different versions of Yocto. Sadly, it isn't
   always possible to always use the latest and greatest version of Yocto, or
   even to use the same version of Yocto for all projects within a group. In
   these cases, Pyrex can be helpful because it will easily allow the different
   versions to use a container image that suits them without the developers
   having to think about it too much.

## When should you *not* use Pyrex?
There are some situations where Pyrex may not always make sense:

1. You aren't doing development. If all you need is a reproducible container
   to build Yocto in (for example, you just want to try out a build to see
   what Yocto is like), Pyrex is probably not for you. Pyrex has some amount
   of setup overhead and because of its focus doesn't isolate the container as
   much as some other solutions. In these cases [CROPS][] is probably a better
   solution.
2. You are a lone developer. Pyrex is primarily intended to ensure that a group
   of developers (e.g. a corporate or other group environment) working in Yocto
   will get consistent builds, regardless of their individual machine setups.
   This probably isn't much of a concern for a single individual.

## Using Pyrex

### Setup
Using vanilla Pyrex with a stock version of Yocto is pretty straight forward.
First, add Pyrex to your project. There are many ways of doing this, but for
this example, we will just clone it into a subdirectory of [poky][].

```shell
git clone https://github.com/garmin/pyrex.git meta-pyrex
```

*NOTE: Cloning down Pyrex with the name `meta-pyrex` can be helpful if you want
to put it as a subdirectory of poky, since poky's .gitignore will ignore all
directories that start with 'meta-'*

Next, you will need to create the environment setup script to initialize the
Pyrex build environment. This script is equivalent to the `oe-init-build-env`
script provided by poky and should be used by your developers in place of that
script when they want to use Pyrex. There are a few ways to create this script,
but all of them eventually must source the
[pyrex-init-build-env](./pyrex-init-build-env) script. By default, this script
assumes that you will create a symbolic link (named whatever you want) that
lives alongside the `oe-init-build-env` script and points to
`pyrex-init-build-env`. You can do this in our example like so:

```shell
ln -s meta-pyrex/pyrex-init-build-env
```

Alternatively, if you want your script to live somewhere else, or use a
non-standard layout, you can write your own environment init script that tells
`pyrex-init-build-env` where everything lives. A crude example script might
look like:

```shell
# The top level Yocto/OE directory (usually, poky). This variable *must* be
# specified if writing a custom script.
PYREX_OEROOT="$(pwd)"

# The path to the build init script. If unspecified, defaults to
# "${PYREX_OEROOT}/oe-init-build-env"
PYREX_OEINIT="$(pwd)/oe-init-build-env"

# The location of Pyrex itself. If not specified, pyrex-init-build-env will
# assume it is the directory where it is currently located (which is probably
# correct)
PYREX_ROOT="$(pwd)/meta-pyrex"

# The location of the pyrex.ini template file to use if the user doesn't
# already have one. Defaults to "$TEMPLATECONF/pyrex.ini.sample" (the same
# location that oe-init-build-env will look for local.conf.sample & friends)
PYREXCONFTEMPLATE="$(pwd)/pyrex.ini.sample"

# Alternatively, if it is desired to always use a fixed config file that users
# can't change, set the following:
#PYREXCONFFILE="$(pwd)/pyrex.ini"

# Source the core pyrex environment script. Note that you must pass the
# arguments
. $(pwd)/meta-pyrex/pyrex-init-build-env "$@"
```

### Configuration
Pyrex is configured using a ini-style configuration file. The location of this
file is specified by the `PYREXCONFFILE` environment variable. This environment
variable must be set before the environment is initialized.

The configuration file is the ini file format supported by Python's
[configparser](https://docs.python.org/3/library/configparser.html) class, with
the following notes:
1. The only allowed comment character is `#`
2. The only allowed key assignment character is `=` (e.g. `key : value` is not
   supported)
3. Extended interpolation is supported. Thus, you can reference other variables
   in the form `${section:key}`
4. All keys are case sensitive

For more information about specific configuration values, see the default
[pyrex.ini](./pyrex.ini)

#### Binding directories into the container
In order for bitbake running in the container to be able to build, it must have
access to the data and config files from the host system. To make this easy, a
variable called `run:bind` is specified in the config file. Any directory that
appears in this variable will be bound into the container image at the same
path (e.g. `/foo/bar` in the host will be bound to `/foo/bar` in the container
engine. By default, only the Openembedded root directory (a.k.a.
`$PYREX_OEROOT`, `${build:oeroot}`) is bound. This is the minimum that can be
bound, and is generally sufficient for most use cases. If additional
directories need to be accessed by the container image, they can be added to
this list by the user. Common reasons for adding new paths include:
* Alternate (out of tree) locations for sstate and download caches
* Alternate (out of tree) build directories
* Additional layers that are not under the OEROOT directory

It is recommended to use this variable and bind directories in a 1-to-1 fashion
rather than try to remap them to different paths inside the container image.
Bitbake tends to encode file paths into some of its internal state (*Note*
**Not** sstate, which should always be position independent), and remapping the
paths might make it difficult to do builds outside of Pyrex if necessary.

You should **never** map directories like `/usr/bin`, `/etc/`, `/` as these
will probably just break the container. It is probably also unwise to map your
entire home directory; although in some cases may be necessary to map
$HOME/.ssh or other directories to access SSH keys and the like. For user
convenience, the proxy user created in the container image by default has the
same $HOME as the user who created the container, so these types of bind can be
done by simply adding `${env:HOME}/.ssh` to `run:bind`

#### Debugging the container
In the event that you need to get a shell into the container to run some
commands, Pyrex creates a command called `pyrex-shell`. Executing this command
in a Pyrex environment will run a shell in the container image, allowing
interactive commands to be run. This can be very useful for debugging Pyrex
containers.

You can also run arbitrary commands in the container with the `pyrex-run`
command. Be aware that any changes made to the container are not persistent,
and will be discarded when `pyrex-run` exits.

### Running Pyrex
Once Pyrex is configured, using it is very straight forward. First, source the
Pyrex environment setup you created. This will setup up the current shell to
run the commands listed in `${config:command}` inside of Pyrex. Once this is
done, you can simply run those commands and they will be executed in Pyrex.

### Bypassing Pyrex
In some cases, it may be desirable to bypass Pyrex and run the commands it
wraps locally instead of in the container. This can be done in one of two ways:

1. Set `${run:enable}` to `0` in `pyrex.ini` which will disable using the
   container engine for all commands
2. Set the environment variable `PYREX_DOCKER` to `0`. Any Pyrex commands run
   with this variable will not be run in the container.

## What doesn't work?
The following items are either known to not work, or haven't been fully tested:
* **Bitbake Server** Since the container starts and stops each time a command
  is run, it is currently not possible to use the bitbake server that runs
  persistently in the background. I believe it *might* be possible to do this
  using persistent container images and `docker exec`, but it hasn't been
  thoroughly investigated.
* **devtool** This may or may not work, and it might not take too much to get
  it working, but it hasn't been tested.
* **GUI terminals** It is unlikely that you will be able to set
  [OE_TERMINAL][] to use a GUI shell (e.g. `rvxt`) for use with
  `devshell`, `pydevshell`, `menuconfig`, etc. There currently isn't a
  mechanism for running GUI programs inside of the container and having them
  draw in the parent windowing system (although I suspect this isn't
  impossible).  The only terminal for that is known to work inside the
  container `screen`. Thankfully, the default value for `OE_TERMINAL` of `auto`
  chooses this by default with the default Pyrex container image.
* **Shell job control** Currently, using `CTRL+Z` to background the container
  doesn't work. It might be possible to get it to work one day, but until then
  the `SIGTSTP` signal is ignored by all child processes in Pyrex to prevent it
  from causing bad behaviors. It is still possible to pause the container using
  the `docker pause` command, but this doesn't integrate with the parent shells
  job control.

## Developing on Pyrex
 If you are doing development on Pyrex itself, please read the [Developer
 Documentation][]

## Using the latest image
While you *can* instruct Pyrex to pull the `latest` tag from dockerhub for a
given image instead of a versioned release tag, this is highly discouraged, as
it will most certainly cause problems. In these cases, you probably want to
build the image locally instead. See the [Developer Documentation][].

## FAQ
* *Why use a Ubuntu image as the default?* The default container image that
  Pyrex creates is based on Ubuntu. Yes, it is known that there are other
  images out there that are lighter weight (e.g. Alpine Linux), but Ubuntu was
  chosen because it is one of the [Sanity Tested Distros][] that Yocto
  supports. Pyrex aims to support a vanilla Yocto setup with minimal manual
  configuration.
* *What's with [cleanup.py](./docker/cleanup.py)?* When a container's main
  process exits, any remaining process appears to be sent a `SIGKILL`.  This
  can cause a significant problem with many of the child processes that bitbake
  spawns, since unceremoniously killing them might result in lost data.  The
  cleanup script is attached to a modified version of
  [tini](https://github.com/krallin/tini/pull/129), and prevents tini from
  exiting until all child processes have exited (it sends them `SIGTERM` if
  they are being tardy). One of the particularly bad culprits is pseudo, which
  uses an in-memory sqlite database to record file permissions. This database
  is only written to disk periodically, meaning a significant amount of very
  important data can be lost if it is killed without being given the chance to
  cleanup. If you find yourself in the unfortunate circumstance of needing to
  debug the cleanup script, you can set the environment variable
  `PYREX_CLEANUP_LOG_LEVEL` to `INFO` or `DEBUG` for more logging.
* *Does the "py" in Pyrex refer to "Python"?* No, it is incidental. The fact
  that the implementation currently uses Python is an implementation detail
  that users should not rely on (or be concerned with). Python was chosen
  because it is already a dependency for using bitbake, so it should already be
  present on a host machine.
* *Were you aware of
  [Pyrex](http://www.cosc.canterbury.ac.nz/greg.ewing/python/Pyrex/)?* Oops.
  Hopefully there isn't too much confusion; that Pyrex looks abandoned anyway

[OE_TERMINAL]: https://www.yoctoproject.org/docs/current/mega-manual/mega-manual.html#var-OE_TERMINAL
[CROPS]: https://github.com/crops
[TEMPLATECONF]: https://www.yoctoproject.org/docs/latest/mega-manual/mega-manual.html#creating-a-custom-template-configuration-directory
[poky]: https://git.yoctoproject.org/cgit/cgit.cgi/poky/
[Sanity Tested Distros]: https://www.yoctoproject.org/docs/current/mega-manual/mega-manual.html#var-SANITY_TESTED_DISTROS
[Developer Documentation]: ./DEVELOPING.md
