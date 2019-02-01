#! /bin/bash
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

declare -a COMMAND=("$@")

if [ "$PYREX_IN_DOCKER" == "1" ]; then
    eval $(fixuid -q)

    # Give the new username sudo permissions
    echo "$PYREX_NEW_USER ALL=(ALL) NOPASSWD: ALL" | sudo tee -a /etc/sudoers > /dev/null

    # Rename user and group
    sudo groupmod -n $PYREX_NEW_GROUP $GROUP > /dev/null
    sudo usermod -l $PYREX_NEW_USER $USER > /dev/null

    USER=$PYREX_NEW_USER
    GROUP=$PYREX_NEW_GROUP
fi

# Consume all arguments before sourcing the environment script
shift $#

if [ -n "$PYREX_OEROOT" ] && [ -n "$PYREX_INIT_COMMAND" ]; then
    pushd "$PYREX_OEROOT" > /dev/null
    source $PYREX_INIT_COMMAND > /dev/null
    popd > /dev/null
fi

exec $PYREX_COMMAND_PREFIX "${COMMAND[@]}"
