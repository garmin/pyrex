# Developer Guide

Pyrex development information and processes

## Making a release

To make a release of Pyrex:

1. Bump the `VERSION` in [pyrex.py](./pyrex.py). Note that all versions should
   be of the form `MAJOR.MINOR.MICRO` + an optional `-rcN` suffix. For example,
   the following are all valid versions: `1.0.0`, `1.0.0-rc1`. Push this
   changes to the master branch.
2. Wait for [Travis](https://travis-ci.org/garmin/pyrex/branches) to finish the
   CI build and verify it passes
3. Create a new [GitHub Release](https://github.com/garmin/pyrex/releases). The
   release must be tagged with the version in `pyrex.py`, prefixed with `v`.
   For example, the `1.0.0` release would be tagged `v1.0.0`
4. Tagging the repository will trigger a new Travis CI build. This build will
   automatically push the docker images to
   [dockerhub](https://cloud.docker.com/u/garminpyrex/repository/list) using
   with the same tag that was created for the release. Verify that the CI build
   passes and the docker images are pushed.

