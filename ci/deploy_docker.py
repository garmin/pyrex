#! /usr/bin/env python3
# Copyright 2021 Garmin Ltd. or its subsidiaries
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

import argparse
import os
import re
import requests
import subprocess
import sys

ALL_IMAGES = [
    "ubuntu-14.04-base",
    "ubuntu-16.04-base",
    "ubuntu-18.04-base",
    "ubuntu-20.04-base",
    "ubuntu-14.04-oe",
    "ubuntu-16.04-oe",
    "ubuntu-18.04-oe",
    "ubuntu-20.04-oe",
    "ubuntu-18.04-oetest",
    "ubuntu-20.04-oetest",
]


def deploy_image(top_dir, image, tag):
    image_dir = os.path.join(top_dir, "image")

    (_, _, image_type) = image.split("-")

    repo = "garmin/%s" % image
    name = "ghcr.io/%s:%s" % (repo, tag)

    print("Deploying %s..." % name)

    # Get a login token for the Docker registry and download the manifest
    token = requests.get(
        "https://ghcr.io/token?scope=repository:%s:pull" % repo,
        json=True,
    ).json()["token"]
    manifest = requests.get(
        "https://ghcr.io/v2/%s/manifests/%s" % (repo, tag),
        headers={"Authorization": "Bearer %s" % token},
        json=True,
    ).json()

    found_manifest = manifest.get("name", "") == repo

    # Only 'latest' and 'next' tags are allowed to be overwritten
    if found_manifest and tag != "latest" and tag != "next":
        print("Tag '%s' already exists. Refusing to push" % tag)
        return 1

    print("Building", name)
    # Construct the arguments for the build command.
    build_args = [
        "-t",
        name,
        "-f",
        "%s/Dockerfile" % image_dir,
        "--build-arg",
        "PYREX_BASE=%s" % image,
        "--target",
        "pyrex-%s" % image_type,
    ]

    # Add the build context directory to our arguments.
    build_args.extend(["--", image_dir])

    try:
        subprocess.check_call(["docker", "build"] + build_args)
    except subprocess.CalledProcessError:
        print("Building failed!")
        return 1

    print("Testing", name)
    try:
        env = os.environ.copy()
        env["TEST_PREBUILT_TAG"] = tag
        test_name = "PyrexImage_docker_" + re.sub(r"\W", "_", image)

        subprocess.check_call(
            ["%s/ci/test.py" % top_dir, "-vbf", test_name], env=env, cwd=top_dir
        )
    except subprocess.CalledProcessError:
        print("Testing failed!")
        return 1

    print("Pushing", name)
    try:
        subprocess.check_call(["docker", "push", name])
    except subprocess.CalledProcessError:
        print("Pushing failed!")
        return 1

    return 0


def main():
    parser = argparse.ArgumentParser(description="Deploy container images to Dockerhub")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Login to Dockerhub using the environment variables $DOCKER_USERNAME and $DOCKER_PASSWORD",
    )
    parser.add_argument(
        "image",
        metavar="IMAGE[:TAG]",
        help="The image to build and push, or 'all' to deploy all images at the current tagged commit",
    )

    args = parser.parse_args()

    top_dir = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), ".."))

    if args.login:
        print("Logging in...")
        for v in ("DOCKER_USERNAME", "DOCKER_PASSWORD"):
            if v not in os.environ:
                print(
                    "$%s is missing from the environment. Images will not be deployed"
                    % v
                )
                return 0

        with subprocess.Popen(
            [
                "docker",
                "login",
                "--username",
                os.environ["DOCKER_USERNAME"],
                "--password-stdin",
            ],
            stdin=subprocess.PIPE,
        ) as p:
            try:
                p.communicate(os.environ["DOCKER_PASSWORD"].encode("utf-8"), timeout=60)
            except subprocess.TimeoutExpired:
                print("Docker login timed out")
                p.kill()
                p.communicate()

            if p.returncode != 0:
                print("Docker login failed. Images will not be deployed")
                return 0

    if args.image == "all":
        p = subprocess.run(
            ["git", "-C", top_dir, "tag", "-l", "--points-at", "HEAD"],
            stdout=subprocess.PIPE,
        )
        tag = p.stdout.decode("utf-8").strip()
        if p.returncode or not tag:
            print("No tag at the current commit")
            return 1

        for image in ALL_IMAGES:
            ret = deploy_image(top_dir, image, tag)
            if ret:
                return ret
    else:
        image = args.image
        if ":" in image:
            image, tag = image.split(":", 1)
        else:
            tag = "latest"

        return deploy_image(top_dir, image, tag)


if __name__ == "__main__":
    sys.exit(main())
