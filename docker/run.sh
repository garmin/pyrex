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

# Consume all arguments before sourcing the environment script
shift $#

if [ -n "$PYREX_INIT_DIR" ] && [ -n "$PYREX_INIT_COMMAND" ]; then
    pushd "$PYREX_INIT_DIR" > /dev/null
    source $PYREX_INIT_COMMAND > /dev/null
    popd > /dev/null
fi

exec $PYREX_COMMAND_PREFIX "${COMMAND[@]}"
