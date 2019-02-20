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

ARG MY_REGISTRY=
FROM ${MY_REGISTRY}ubuntu:trusty
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to add ppa's
RUN apt-get -y update && apt-get -y install \
    python-software-properties \
    software-properties-common

# Add a non-ancient version of git
RUN add-apt-repository -y ppa:git-core/ppa

RUN apt-get -y update && apt-get -y install \
# Poky 2.0 build dependencies
    gawk \
    wget \
    git-core \
    diffstat \
    unzip \
    texinfo \
    gcc-multilib \
    build-essential \
    chrpath \
    socat \
    libsdl1.2-dev \
    xterm \
# Poky 2.1 build dependencies
    gawk \
    wget \
    git-core \
    diffstat \
    unzip \
    texinfo \
    gcc-multilib \
    build-essential \
    chrpath \
    socat \
# Poky 2.2 build dependencies
    gawk \
    wget \
    git-core \
    diffstat \
    unzip \
    texinfo \
    gcc-multilib \
    build-essential \
    chrpath \
    socat \
# Not listed, but required dependencies (from ASSUME_PROVIDED)
    bzip2 \
    libbz2-dev \
    sed \
    findutils \
# Required for some poorly written 3rd party recipes :(
    python-crypto \
    python-six \
    python3-six \
# Useful tools for debugging Pyrex images
    sudo \
    curl \
    locales \
# An updated version of Git (from the PPA source above)
# that supports doing Yocto externalsrc recipes against free-
# standing working copies that use Git worktrees.
    git>=1:2.17.* \
# Corollary to the core Yocto gcc-multilib package. Allows various
# prebuilt native tools to work
    g++-multilib \
# Screen to enable devshell
    screen \
&& rm -rf /var/lib/apt/lists/*

ENV PYREX_UTILS_VERSION=2019.02.22

# Use a recent version of Icecream, which has many bug fixes
RUN wget https://github.com/JoshuaWatt/pyrex-utilities/releases/download/${PYREX_UTILS_VERSION}/icecream.tar.gz && \
    echo "b534eb98be51ae605bed79456e80e47636d9bf429797f3f446b4cfc62fac1e87 *icecream.tar.gz" | sha256sum -c - && \
    tar -xzf icecream.tar.gz -C / && \
    rm -rf icecream.tar.gz

# Setup Icecream distributed compiling client. The client tries several IPC
# mechanisms to find the daemon, including connecting to a localhost TCP
# socket. Since the local Icecream daemon (iceccd) is not started when the
# docker container starts, the client will not find it and instead connect to
# the host Icecream daemon (as long as the container is run with --net=host).
RUN mkdir -p /usr/share/icecc/toolchain && \
    cd /usr/share/icecc/toolchain/ && \
    TC_NAME=$(mktemp) && \
    /usr/local/libexec/icecc/icecc-create-env --gcc $(which gcc) $(which g++) 5> $TC_NAME && \
    mv $(cat $TC_NAME) native-gcc.tar.gz && \
    rm $TC_NAME

ENV ICECC_VERSION=/usr/share/icecc/toolchain/native-gcc.tar.gz

# Generate locales
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Download and install tini
RUN wget -O /usr/local/bin/tini https://github.com/JoshuaWatt/pyrex-utilities/releases/download/${PYREX_UTILS_VERSION}/tini && \
    echo "118592085431040a9981ab64c180e6d1f04d49ea63557463e6458dfbcaa89f8f */usr/local/bin/tini" | sha256sum -c - && \
    chmod +x /usr/local/bin/tini

# Download and install setpriv
RUN wget -O /usr/local/bin/setpriv https://github.com/JoshuaWatt/pyrex-utilities/releases/download/${PYREX_UTILS_VERSION}/setpriv && \
    echo "001506e1eb52e93f34fa1677a1d52dda6c3e77e10308655d3d525392e01ab75f */usr/local/bin/setpriv" | sha256sum -c - && \
    chmod +x /usr/local/bin/setpriv

# Add startup scripts
COPY ./startup.sh /usr/libexec/tini/startup.sh
COPY ./entry.py /usr/libexec/tini/entry.py
COPY ./wrapper.py /usr/libexec/tini/wrapper.py
COPY ./cleanup.py /usr/libexec/tini/cleanup.py
RUN chmod +x /usr/libexec/tini/cleanup.py \
    /usr/libexec/tini/entry.py \
    /usr/libexec/tini/startup.sh \
    /usr/libexec/tini/wrapper.py

# Precompile python files for improved startup time
RUN python3 -m py_compile /usr/libexec/tini/*.py

# Use tini as the init process and instruct it to invoke the cleanup script
# once the primary command dies
ENTRYPOINT ["/usr/local/bin/tini", "-P", "/usr/libexec/tini/cleanup.py", "{}", ";", "--", "/usr/libexec/tini/entry.py", "/usr/libexec/tini/startup.sh"]

# The startup script is expected to chain along to some other
# command. By default, we'll use an interactive shell.
CMD ["/bin/bash"]
