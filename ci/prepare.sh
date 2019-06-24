#! /bin/sh
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

set -e

TOP_DIR=$(readlink -f $(dirname $0)/../)

rm -rf $TOP_DIR/poky
mkdir $TOP_DIR/poky
wget --no-check-certificate -O $TOP_DIR/poky/poky.tar.bz2 "https://downloads.yoctoproject.org/releases/yocto/yocto-2.6/poky-thud-20.0.0.tar.bz2"
echo 'ef3d4305054282938bfe70dc5a08eba8a701a22b49795b1c2d8ed5aed90d0581 *poky/poky.tar.bz2' | sha256sum -c
echo "Extracting..."
tar -xf $TOP_DIR/poky/poky.tar.bz2 -C $TOP_DIR/poky --strip-components=1
ln -s ../pyrex-init-build-env $TOP_DIR/poky/
