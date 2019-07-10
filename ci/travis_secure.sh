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

# Use this script to setup the secure variables in .travis.yml

TRAVIS=$(which travis 2> /dev/null)

if [ -z "$TRAVIS" ]; then
    echo "'travis' not found. Please install it with 'gem install travis'"
    exit 1
fi

echo "NOTE: The Travis command line tool will append the new secure"
echo "environment. If you want to replace the existing one, you must delete it"
echo "from .travis.yml manually before running this script"
echo

travis encrypt --add env.global <<HEREDOC
DOCKER_USERNAME=$(read -e -p "Dockerhub Username (NOT email address): " && printf "%q" "$REPLY")
HEREDOC
travis encrypt --add env.global <<HEREDOC
DOCKER_PASSWORD=$(read -e -p "Dockerhub Password: " -s && printf "%q" "$REPLY")
HEREDOC

REPLY=""
echo
