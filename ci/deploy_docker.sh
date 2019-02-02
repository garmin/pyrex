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

NAMESPACE=garminpyrex
DOCKER_DIR=$(readlink -f $(dirname "$0")/../docker)
IMAGE="$1"
shift

cd $DOCKER_DIR

if [ -n "$TRAVIS_TAG" ]; then
    TAG=$TRAVIS_TAG
else
    TAG=latest
fi

NAME="$NAMESPACE/$IMAGE:$TAG"

echo "Building $NAME"
docker build -t "$NAME" -f $IMAGE/Dockerfile "$@" -- .

echo "Pushing $NAME"
docker push $NAME

