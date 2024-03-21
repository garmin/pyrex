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
wget --no-check-certificate -O "$TOP_DIR/poky/poky-2.6.tar.bz2" "https://downloads.yoctoproject.org/releases/yocto/yocto-2.6.4/poky-thud-20.0.4.tar.bz2"

wget --no-check-certificate -O "$TOP_DIR/poky/poky-3.1.tar.bz2" "http://downloads.yoctoproject.org/releases/yocto/yocto-3.1.32/poky-dunfell-23.0.32.tar.bz2"

wget --no-check-certificate -O "$TOP_DIR/poky/poky-4.0.tar.bz2" "http://downloads.yoctoproject.org/releases/yocto/yocto-4.0.16/poky-54af8c5e80ebf63707ef4e51cc9d374f716da603.tar.bz2"

sha256sum -c <<HEREDOC
9210c22c1f533c09202219ca89317c1ab06d27ac987cc856ee3a6a2aa41ad476 *poky/poky-2.6.tar.bz2
8a80432093ee79a27ea4984bea89f0ca8a9f7de5da3837d69ed4d5a6410bfad6 *poky/poky-3.1.tar.bz2
a53ec3a661cf56ca40c0fbf1500288c2c20abe94896d66a572bc5ccf5d92e9d6 *poky/poky-4.0.tar.bz2
HEREDOC

for v in "2.6" "3.1" "4.0"; do
    mkdir "$TOP_DIR/poky/$v"
    echo "Extracting $v..."
    tar -xf "$TOP_DIR/poky/poky-$v.tar.bz2" -C "$TOP_DIR/poky/$v" --strip-components=1
    ln -s ../../pyrex-init-build-env "$TOP_DIR/poky/$v/"
done
