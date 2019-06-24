#! /usr/bin/env python3

import argparse
import os
import requests
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description='Deploy docker images')
    parser.add_argument('image', metavar='IMAGE[:TAG]', help='The image to build and push')

    args = parser.parse_args()

    this_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
    docker_dir = os.path.join(this_dir, '..', 'docker')

    image = args.image
    if ':' in image:
        image, tag = image.split(':', 1)
    elif 'TRAVIS_TAG' in os.environ:
        tag = os.environ['TRAVIS_TAG']
    else:
        tag = 'latest'

    repo = 'garminpyrex/%s' % image
    name = '%s:%s' % (repo, tag)

    # Get a login token for the docker registry and download the manifest
    token = requests.get("https://auth.docker.io/token?service=registry.docker.io&scope=repository:%s:pull" % repo, json=True).json()["token"]
    manifest = requests.get(
            "https://registry.hub.docker.com/v2/%s/manifests/%s" % (repo, tag),
            headers={"Authorization": "Bearer %s" % token},
            json=True
            ).json()

    found_manifest = (manifest.get('name', '') == repo)

    # Only 'latest' and 'next' tags are allowed to be overwritten
    if found_manifest and tag != 'latest' and tag != 'next':
        print("Tag '%s' already exists. Refusing to push" % tag)
        return 1

    print("Building", name)
    try:
        subprocess.check_call(['docker', 'build', '-t', name, '-f', '%s/Dockerfile' % docker_dir,
                               '--build-arg', 'PYREX_BASE=%s' % image, '--', docker_dir])
    except subprocess.CalledProcessError as e:
        print("Building failed!")
        return 1

    print("Testing", name)
    try:
        env = os.environ.copy()
        env['TEST_IMAGE'] = image
        env['TEST_PREBUILT_TAG'] = tag

        subprocess.check_call(['%s/test.py' % this_dir, '-vbf'], env=env, cwd=os.path.join(this_dir, '..'))
    except subprocess.CalledProcessError as e:
        print("Testing failed!")
        return 1

    print("Pushing", name)
    try:
        subprocess.check_call(['docker', 'push', name])
    except subprocess.CalledProcessError as e:
        print("Pushing failed!")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
