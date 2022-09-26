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

# Prevent some variables from being unset so their value can be captured
unset() {
    for var in "$@"; do
        case "$var" in
            BITBAKEDIR) ;;
            OEROOT) ;;
            *)
                builtin unset "$var"
                ;;
        esac
    done
}

check_bound() {
    if [ ! -e "$1" ]; then
        echo "ERROR: $1 not bound in container (File doesn't exist). "
        echo "Please set either \$PYREX_CONFIG_BIND or 'run:bind' in" \
             "$PYREXCONFFILE to ensure it is bound into the container."
        exit 1
    fi

    if [ "$(findmnt -f -n -o TARGET --target "$1")" == "/" ]; then
        echo "ERROR: $1 not bound in container (File mount target is root)"
        echo "Please set either \$PYREX_CONFIG_BIND or 'run:bind' in" \
             "$PYREXCONFFILE to ensure it is bound into the container."
        exit 1
    fi
}

# Consume all arguments before sourcing the environment script
declare -a PYREX_ARGS=("$@")
shift $#

# Ensure the init script is bound in the container
check_bound "$PYREX_OEINIT"

# If the bitbake directory argument or environment variable is provided, ensure
# it is bound in the container
if [ -n "${PYREX_ARGS[1]}" ]; then
    check_bound "${PYREX_ARGS[1]}"

    if [ -n "${PYREX_ARGS[2]}" ]; then
        check_bound "${PYREX_ARGS[2]}"
    fi
fi

if [ -n "$BITBAKEDIR" ]; then
    check_bound "$BITBAKEDIR"
fi

if [ -n "$BDIR" ]; then
    check_bound "$BDIR"
fi

if [ -n "$OEROOT" ]; then
    check_bound "$OEROOT"
fi

. "$PYREX_OEINIT" "${PYREX_ARGS[@]}"
if [ $? -ne 0 ]; then
    exit 1
fi

if [ -z "$BITBAKEDIR" ]; then
    echo "\$BITBAKEDIR not captured!"
    exit 1
fi

if [ -z "$OEROOT" ]; then
    echo "\$OEROOT not captured!"
    exit 1
fi

# Ensure the build directory is bound into the container.
check_bound "$(pwd)"

check_bound "$PYREX_CAPTURE_DEST"

json_str() {
    echo "\"$1\": \"${!1}\""
}

cat > "$PYREX_CAPTURE_DEST" <<HEREDOC
{
    "tempdir": "$PWD/pyrex",
    "user" : {
        "cwd": "$PWD",
        "export": {
            ${BB_ENV_EXTRAWHITE:+$(json_str "BB_ENV_EXTRAWHITE"),}
            ${BB_ENV_PASSTHROUGH_ADDITIONS:+$(json_str "BB_ENV_PASSTHROUGH_ADDITIONS"),}
            "BUILDDIR": "$BUILDDIR"
        }
    },
    "container": {
        "shell": "/bin/bash",
        "commands": {
            "include": [
                "$BITBAKEDIR/bin/*",
                "$OEROOT/scripts/*"
            ],
            "exclude": [
                "$OEROOT/scripts/runqemu*",
                "$OEROOT/scripts/oe-run-native",
                "$OEROOT/scripts/oe-find-native-sysroot",
                "$OEROOT/scripts/wic",
                "$OEROOT/scripts/git"
            ]
        }
    },
    "run": {
        "env" : {
            "BBPATH": "$BBPATH",
            "PATH": "$PATH",
            "BUILDDIR": "$BUILDDIR"
        }
    }
}
HEREDOC

