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

ARG PYREX_BASE=ubuntu-18.04
ARG MY_REGISTRY=
#
# Base image for prebuilt static binaries
#
FROM ${MY_REGISTRY}alpine:3.9 AS prebuilt-base

RUN apk add --update \
    alpine-sdk \
    autoconf \
    automake \
    bash \
    cmake \
    file \
    libcap-ng-dev \
    libtool \
    lzo-dev \
    musl-utils \
    wget \
    xz \
;

RUN mkdir -p /dist
RUN mkdir -p /usr/src

#
# Prebuilt static icecream
#
FROM prebuilt-base AS prebuilt-icecream
COPY patches/icecream-recompile.patch /usr/src/

# Use a recent version of Icecream, which has many bug fixes
ENV ICECREAM_SHA1=e39103ff5fb6aa7e939b486df25d621696ba1d6f
RUN mkdir -p /usr/src/icecream && \
    cd /usr/src/icecream && \
    wget -O icecream.tar.gz https://github.com/icecc/icecream/archive/${ICECREAM_SHA1}.tar.gz && \
    tar -xvzf icecream.tar.gz && \
    cd icecream-${ICECREAM_SHA1} && \
    patch -p1 < /usr/src/icecream-recompile.patch && \
    mkdir build && \
    cd build && \
    ../autogen.sh && \
    ../configure --prefix=/usr/local/ \
        --enable-gcc-color-diagnostics \
        --enable-gcc-show-caret \
        --enable-gcc-fdirectives-only \
        --enable-clang-rewrite-includes \
        --without-man \
        LDFLAGS="-static" && \
    make -j$(nproc) LDFLAGS="--static" && \
    make install-strip DESTDIR=/dist/icecream

#
# Prebuilt static setpriv
#
FROM prebuilt-base AS prebuilt-setpriv
RUN mkdir -p /usr/src/util-linux && \
    cd /usr/src/util-linux && \
    wget https://mirrors.edge.kernel.org/pub/linux/utils/util-linux/v2.33/util-linux-2.33.1.tar.xz && \
    tar -xvf util-linux-2.33.1.tar.xz && \
    cd util-linux-2.33.1 && \
    mkdir build && \
    cd build && \
    ../configure \
        --disable-all-programs \
        --enable-setpriv \
        --disable-doc \
        LDFLAGS="-static" \
        --disable-nls \
        --without-bashcompletion \
        --prefix=/usr/local && \
    make -j$(nproc) LDFLAGS="--static" && \
    make install-strip DESTDIR=/dist/setpriv

#
# Prebuilt static tini
#
FROM prebuilt-base as prebuilt-tini
ENV TINI_SHA1=c3b92ce685d0387c5d508f1856aa6d4cae25db8d
RUN mkdir -p /usr/src/tini && \
    cd /usr/src/tini && \
    wget -O tini.tar.gz https://github.com/JPEWdev/tini/archive/${TINI_SHA1}.tar.gz && \
    tar -xvzf tini.tar.gz && \
    mkdir build && \
    cd build && \
    cmake -DCMAKE_INSTALL_PREFIX:PATH=/usr/local ../tini-${TINI_SHA1} && \
    make && \
    make install DESTDIR=/dist/tini && \
    mv /dist/tini/usr/local/bin/tini-static /dist/tini/usr/local/bin/tini

#
# Ubuntu 14.04 base
#
FROM ${MY_REGISTRY}ubuntu:trusty as ubuntu-14.04
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to add ppa's
RUN apt-get -y update && apt-get -y install \
    python-software-properties \
    software-properties-common

# Add a non-ancient version of git
RUN add-apt-repository -y ppa:git-core/ppa

RUN export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
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
# Dependencies for "bitbake -c menuconfig"
    libncurses5-dev \
    libtinfo-dev \
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
# Base OS stuff that reasonable workstations have, but which the Docker
# registry image doesn't
    tzdata \
&& rm -rf /var/lib/apt/lists/*

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 16.04 Base
#
FROM ${MY_REGISTRY}ubuntu:xenial as ubuntu-16.04
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to add ppa's
RUN apt-get -y update && apt-get -y install \
    python-software-properties \
    software-properties-common

# Add a non-ancient version of git
RUN add-apt-repository -y ppa:git-core/ppa

RUN export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
# Poky 2.7 build dependencies
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
    python3-git \
    python3-jinja2 \
    libegl1-mesa \
    libsdl1.2-dev \
    xterm \
# Dependencies for "bitbake -c menuconfig"
    libncurses5-dev \
    libtinfo-dev \
# Not listed, but required dependencies (from ASSUME_PROVIDED)
    bzip2 \
    libbz2-dev \
    sed \
    findutils \
# Dependencies for "bitbake -c menuconfig"
    libncurses5-dev \
    libtinfo-dev \
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
# Base OS stuff that reasonable workstations have, but which the Docker
# registry image doesn't
    tzdata \
&& rm -rf /var/lib/apt/lists/*

# Python modules used by resulttool
RUN python3 -m pip install jinja2

# Install wine, needed to test meta-mingw SDKs
RUN dpkg --add-architecture i386 && \
    apt-get -y update && \
    (echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections) && \
    apt-get -y install \
    wine \
&& rm -rf /var/lib/apt/lists/*

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 18.04 Base
#
FROM ${MY_REGISTRY}ubuntu:bionic as ubuntu-18.04
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
# Poky 2.7 build dependencies
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
    python3-git \
    python3-jinja2 \
    libegl1-mesa \
    libsdl1.2-dev \
    xterm \
    coreutils \
# Testing dependencies
    iproute2 \
    sysstat \
# Dependencies for "bitbake -c menuconfig"
    libncurses5-dev \
    libtinfo-dev \
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
# Corollary to the core Yocto gcc-multilib package. Allows various
# prebuilt native tools to work
    g++-multilib \
# Screen to enable devshell
    screen \
# Tools used by Pyrex
    lsb-release \
    setpriv \
# Base OS stuff that reasonable workstations have, but which the Docker
# registry image doesn't
    tzdata \
&& rm -rf /var/lib/apt/lists/*

# Install wine, needed to test meta-mingw SDKs
RUN dpkg --add-architecture i386 && \
    apt-get -y update && \
    (echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections) && \
    apt-get -y install \
    wine-stable \
&& rm -rf /var/lib/apt/lists/*

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /
COPY --from=prebuilt-tini /dist/tini /

# 
# Target image
#
FROM ${PYREX_BASE}

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

# Add startup scripts
COPY ./startup.sh /usr/libexec/tini/startup.sh
COPY ./entry.py /usr/libexec/tini/entry.py
COPY ./cleanup.py /usr/libexec/tini/cleanup.py
RUN chmod +x /usr/libexec/tini/cleanup.py \
    /usr/libexec/tini/entry.py \
    /usr/libexec/tini/startup.sh

# Precompile python files for improved startup time
RUN python3 -m py_compile /usr/libexec/tini/*.py

# Use tini as the init process and instruct it to invoke the cleanup script
# once the primary command dies
ENTRYPOINT ["/usr/local/bin/tini", "-P", "/usr/libexec/tini/cleanup.py", "{}", ";", "--", "/usr/libexec/tini/entry.py", "/usr/libexec/tini/startup.sh"]

# The startup script is expected to chain along to some other
# command. By default, we'll use an interactive shell.
CMD ["/bin/bash"]
