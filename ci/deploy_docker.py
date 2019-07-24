#! /usr/bin/env python3

import argparse
import os
import re
import requests
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description='Deploy docker images')
    parser.add_argument('--login', action='store_true',
                        help='Login to Dockerhub using the environment variables $DOCKER_USERNAME and $DOCKER_PASSWORD')
    parser.add_argument('image', metavar='IMAGE[:TAG]', help='The image to build and push')

    args = parser.parse_args()

    this_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
    docker_dir = os.path.join(this_dir, '..', 'docker')

    image = args.image
    if ':' in image:
        image, tag = image.split(':', 1)
    elif 'TRAVIS_TAG' in os.environ:
        tag = os.environ['TRAVIS_TAG'] or 'latest'
    else:
        tag = 'latest'

    (_, _, image_type) = image.split('-')

    repo = 'garminpyrex/%s' % image
    name = '%s:%s' % (repo, tag)

    if args.login:
        print("Logging in...")
        for v in ('DOCKER_USERNAME', 'DOCKER_PASSWORD'):
            if v not in os.environ:
                print("$%s is missing from the environment. Images will not be deployed" % v)
                return 0

        with subprocess.Popen(['docker', 'login', '--username', os.environ['DOCKER_USERNAME'],
                               '--password-stdin'], stdin=subprocess.PIPE) as p:
            try:
                p.communicate(os.environ['DOCKER_PASSWORD'].encode('utf-8'), timeout=60)
            except subprocess.TimeoutExpired:
                print("Docker login timed out")
                p.kill()
                p.communicate()

            if p.returncode != 0:
                print("Docker login failed. Images will not be deployed")
                return 0

    print("Deploying %s..." % name)

    # Get a login token for the docker registry and download the manifest
    token = requests.get("https://auth.docker.io/token?service=registry.docker.io&scope=repository:%s:pull" %
                         repo, json=True).json()["token"]
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
    # Construct the arguments for the build command.
    docker_build_args = [
        '-t', name,
        '-f', '%s/Dockerfile' % docker_dir,
        '--build-arg', 'PYREX_BASE=%s' % image,
        '--target', 'pyrex-%s' % image_type
    ]

    # Add the build context directory to our arguments.
    docker_build_args.extend(['--', docker_dir])

    try:
        subprocess.check_call(['docker', 'build'] + docker_build_args)
    except subprocess.CalledProcessError:
        print("Building failed!")
        return 1

    print("Testing", name)
    try:
        env = os.environ.copy()
        env['TEST_PREBUILT_TAG'] = tag
        test_name = 'PyrexImage_docker_' + re.sub(r'\W', '_', image)

        subprocess.check_call(['%s/test.py' % this_dir, '-vbf', test_name], env=env, cwd=os.path.join(this_dir, '..'))
    except subprocess.CalledProcessError:
        print("Testing failed!")
        return 1

    print("Pushing", name)
    try:
        subprocess.check_call(['docker', 'push', name])
    except subprocess.CalledProcessError:
        print("Pushing failed!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
