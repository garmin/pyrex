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

TOP_DIR=$(readlink -f "$(dirname "$0")/../")

rm -rf "$TOP_DIR/poky"
mkdir "$TOP_DIR/poky"
wget --no-check-certificate -O "$TOP_DIR/poky/poky-2.6.tar.bz2" "https://downloads.yoctoproject.org/releases/yocto/yocto-2.6/poky-thud-20.0.0.tar.bz2"
echo 'ef3d4305054282938bfe70dc5a08eba8a701a22b49795b1c2d8ed5aed90d0581 *poky/poky-2.6.tar.bz2' | sha256sum -c

wget --no-check-certificate -O "$TOP_DIR/poky/poky-3.1.tar.bz2" "http://downloads.yoctoproject.org/releases/yocto/yocto-3.1/poky-dunfell-23.0.0.tar.bz2"
echo 'c1f4a486e5f090dbdf50c15a5d22afa6689bd609604b48d63eb0643ad58eb370 *poky/poky-3.1.tar.bz2' | sha256sum -c

wget --no-check-certificate -O "$TOP_DIR/poky/poky-4.0.tar.bz2" http://downloads.yoctoproject.org/releases/yocto/yocto-4.0/poky-00cfdde791a0176c134f31e5a09eff725e75b905.tar.bz2
echo '4cedb491b7bf0d015768c61690f30d7d73f4266252d6fba907bba97eac83648c *poky/poky-4.0.tar.bz2' | sha256sum -c

mkdir "$TOP_DIR/poky/2.6" "$TOP_DIR/poky/3.1" "$TOP_DIR/poky/4.0"
echo "Extracting..."
tar -xf "$TOP_DIR/poky/poky-2.6.tar.bz2" -C "$TOP_DIR/poky/2.6" --strip-components=1
tar -xf "$TOP_DIR/poky/poky-3.1.tar.bz2" -C "$TOP_DIR/poky/3.1" --strip-components=1
tar -xf "$TOP_DIR/poky/poky-4.0.tar.bz2" -C "$TOP_DIR/poky/4.0" --strip-components=1
ln -s ../../pyrex-init-build-env "$TOP_DIR/poky/2.6/"
ln -s ../../pyrex-init-build-env "$TOP_DIR/poky/3.1/"
ln -s ../../pyrex-init-build-env "$TOP_DIR/poky/4.0/"
