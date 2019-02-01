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

ARG MY_REGISTRY
FROM ${MY_REGISTRY}/ubuntu:xenial
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to add ppa's
RUN apt-get -y update && apt-get -y install \
    python-software-properties \
    software-properties-common

# Add a non-ancient version of git
RUN add-apt-repository -y ppa:git-core/ppa

RUN apt-get -y update && apt-get -y install \
# Poky 2.5 build dependencies
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
    cpio \
    python \
    python3 \
    python3-pip \
    python3-pexpect \
    xz-utils \
    debianutils \
    iputils-ping \
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
# Required to build tini from source
    cmake \
# Required to build icecream from source
    autotools-dev \
    autoconf \
    libtool \
    libcap-ng-dev \
    liblzo2-dev \
&& rm -rf /var/lib/apt/lists/*

# Install wine, needed to test meta-mingw SDKs
RUN dpkg --add-architecture i386 && \
    apt-get -y update && \
    (echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections) && \
    apt-get -y install \
    wine \
&& rm -rf /var/lib/apt/lists/*

env USER pyrex
env GROUP pyrex
env HOME /home/pyrex

RUN addgroup --gid 1000 $GROUP && \
    adduser --uid 1000 --ingroup $GROUP --home $HOME --shell /bin/sh --disabled-password --gecos "" $USER

# Allow pyrex to run any command as root
RUN echo "$USER ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Use a recent version of Icecream, which has many bug fixes
RUN mkdir -p /usr/src/icecream && \
    cd /usr/src/icecream && \
    ICECREAM_VER="1.2" && \
    wget -O icecream.tar.gz https://github.com/icecc/icecream/archive/${ICECREAM_VER}.tar.gz && \
    tar -xvzf icecream.tar.gz && \
    cd icecream-${ICECREAM_VER} && \
    wget -O recompile.patch https://github.com/icecc/icecream/commit/cd082c64adcd3c2a22dc0565f6e5b249a975694a.patch && \
    patch -p1 < recompile.patch && \
    cd .. && \
    mkdir build && \
    cd build && \
    ../icecream-${ICECREAM_VER}/autogen.sh && \
    ../icecream-${ICECREAM_VER}/configure \
        --prefix=/usr \
        --enable-gcc-color-diagnostics \
        --enable-gcc-show-caret \
        --enable-gcc-fdirectives-only \
        --enable-clang-rewrite-includes \
        --without-man \
        && \
    make && \
    make install && \
    cd / && \
    rm -rf /usr/src/icecream

# Setup Icecream distributed compiling client. The client tries several IPC
# mechanisms to find the daemon, including connecting to a localhost TCP
# socket. Since the local Icecream daemon (iceccd) is not started when the
# docker container starts, the client will not find it and instead connect to
# the host Icecream daemon (as long as the container is run with --net=host).
RUN mkdir -p /usr/share/icecc/toolchain && \
    cd /usr/share/icecc/toolchain/ && \
    TC_NAME=$(mktemp) && \
    /usr/libexec/icecc/icecc-create-env --gcc $(which gcc) $(which g++) 5> $TC_NAME && \
    mv $(cat $TC_NAME) native-gcc.tar.gz && \
    rm $TC_NAME

ENV ICECC_VERSION=/usr/share/icecc/toolchain/native-gcc.tar.gz
ENV INIT_DIR=$HOME

# Generate locales
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Turn on background color erase. This fixes screen not correctly erasing when
# it is nested in another terminal emulator
RUN echo "defbce on" >> $HOME/.screenrc

# Download and install tini
RUN mkdir -p /usr/src/tini && \
    cd /usr/src/tini && \
    TINI_SHA1=c3b92ce685d0387c5d508f1856aa6d4cae25db8d && \
    wget -O tini.tar.gz https://github.com/JPEWdev/tini/archive/${TINI_SHA1}.tar.gz && \
    tar -xvzf tini.tar.gz && \
    mkdir build && \
    cd build && \
    cmake ../tini-${TINI_SHA1} && \
    make && \
    make install && \
    cd / && \
    rm -rf /usr/src/tini

# Add startup scripts
COPY ./startup.sh /usr/libexec/tini/startup.sh
COPY ./wrapper.py /usr/libexec/tini/wrapper.py
COPY ./cleanup.py /usr/libexec/tini/cleanup.py
RUN chmod +x /usr/libexec/tini/cleanup.py /usr/libexec/tini/startup.sh /usr/libexec/tini/wrapper.py

# Install and configure the fixuid script
RUN curl -SsL https://github.com/boxboat/fixuid/releases/download/v0.4/fixuid-0.4-linux-amd64.tar.gz | tar -C /usr/local/bin -xzf - && \
    chown root:root /usr/local/bin/fixuid && \
    chmod 4755 /usr/local/bin/fixuid && \
    mkdir -p /etc/fixuid && \
    printf "user: $USER\ngroup: $GROUP\npaths:\n  - $HOME" > /etc/fixuid/config.yml

# Use tini as the init process and instruct it to invoke the cleanup script
# once the primary command dies
USER $USER:$GROUP
ENTRYPOINT ["/usr/local/bin/tini", "-P", "/usr/libexec/tini/cleanup.py", "{}", ";", "--", "/bin/bash", "/usr/libexec/tini/startup.sh"]

# The startup script is expected to chain along to some other
# command. By default, we'll use an interactive shell.
CMD ["/bin/bash"]
