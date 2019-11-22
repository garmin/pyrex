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

ARG PYREX_BASE=ubuntu-18.04-oe
ARG MY_REGISTRY=

#
# Base image for prebuilt static binaries
#
FROM ${MY_REGISTRY}alpine:3.9 AS prebuilt-base
ENV PYREX_BASE none
ENV MY_REGISTRY none

RUN apk add --update \
    acl-dev \
    alpine-sdk \
    autoconf \
    automake \
    bash \
    bzip2-dev \
    cmake \
    expat-dev \
    file \
    libarchive-dev \
    libcap-ng-dev \
    libtool \
    lz4-dev \
    lzo-dev \
    musl-utils \
    openssl-dev \
    wget \
    xz \
    xz-dev \
    zlib-dev \
    zstd-dev \
    zstd-static \
;

RUN mkdir -p /dist
RUN mkdir -p /usr/src
COPY patches/0001-Use-pkg-config-to-find-packages.patch /usr/src/

#
# Prebuilt static icecream
#
FROM prebuilt-base AS prebuilt-icecream
ENV PYREX_BASE none
ENV MY_REGISTRY none

# Use a recent version of Icecream, which has many bug fixes
ENV ICECREAM_SHA1=1aa08857cb9c2639dbde1c2f6a05212c842581f1
RUN mkdir -p /usr/src/icecream && \
    cd /usr/src/icecream && \
    wget -O icecream.tar.gz https://github.com/icecc/icecream/archive/${ICECREAM_SHA1}.tar.gz && \
    tar -xvzf icecream.tar.gz && \
    cd icecream-${ICECREAM_SHA1} && \
    patch -p1 < /usr/src/0001-Use-pkg-config-to-find-packages.patch && \
    mkdir build && \
    cd build && \
    ../autogen.sh && \
    ../configure --prefix=/usr/local/ \
        --enable-gcc-color-diagnostics \
        --enable-gcc-show-caret \
        --enable-gcc-fdirectives-only \
        --enable-clang-rewrite-includes \
        --without-man \
        --enable-static \
        --disable-shared \
        LDFLAGS="-static" \
        PKG_CONFIG="pkg-config --static" && \
    make -j$(nproc) LDFLAGS="--static" && \
    make install-strip DESTDIR=/dist/icecream

#
# Prebuilt static setpriv
#
FROM prebuilt-base AS prebuilt-setpriv
ENV PYREX_BASE none
ENV MY_REGISTRY none
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
ENV PYREX_BASE none
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
FROM ${MY_REGISTRY}ubuntu:trusty as ubuntu-14.04-base
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        sudo \
    && \
# Clean up apt-cache
    rm -rf /var/lib/apt/lists/* &&\
# generate utf8 locale
    locale-gen en_US.UTF-8 && \
    (locale -a | tee /dev/stderr | grep -qx en_US.utf8)

# Copy prebuilt items
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 16.04 Base
#
FROM ${MY_REGISTRY}ubuntu:xenial as ubuntu-16.04-base
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        sudo \
    && \
# Clean up apt-cache
    rm -rf /var/lib/apt/lists/* &&\
# generate utf8 locale
    locale-gen en_US.UTF-8 && \
    (locale -a | tee /dev/stderr | grep -qx en_US.utf8)

# Copy prebuilt items
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 18.04 Base
#
FROM ${MY_REGISTRY}ubuntu:bionic as ubuntu-18.04-base
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        setpriv \
        sudo \
    && \
# Clean up apt-cache
    rm -rf /var/lib/apt/lists/* && \
# generate utf8 locale
    locale-gen en_US.UTF-8 && \
    (locale -a | tee /dev/stderr | grep -qx en_US.utf8)

# Copy prebuilt items
COPY --from=prebuilt-tini /dist/tini /

#
# Centos 7
#
FROM ${MY_REGISTRY}centos:7 as centos-7-base
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="James Harris <james.harris@garmin.com>"
RUN set -x && \
      #Install default components
      yum install -y yum-utils \
          which \
          sudo \
          redhat-lsb-core \
          &&\
      yum install -y https://centos7.iuscommunity.org/ius-release.rpm &&\
      yum install -y python36u &&\
      yum clean all &&\
      localedef -c -f UTF-8 -i en_US en_US.UTF-8

# Reset the default useradd options for when the primary user is added
RUN echo "SHELL=/bin/bash" > /etc/default/useradd

# Copy prebuilt items
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 14.04 Yocto Base
#
FROM ubuntu-14.04-base as ubuntu-14.04-oe
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
# Add a non-ancient version of git
    apt-get -y update && apt-get -y install software-properties-common && \
    add-apt-repository -y ppa:git-core/ppa && \
    apt-get -y update && apt-get -y install \
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
    curl \
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

#
# Ubuntu 16.04 Yocto Base
#
FROM ubuntu-16.04-base as ubuntu-16.04-oe
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
# Add a non-ancient version of git
    apt-get -y update && apt-get -y install software-properties-common && \
    add-apt-repository -y ppa:git-core/ppa && \
    apt-get -y update && apt-get -y install \
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
    curl \
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
RUN python3 -m pip install jinja2 iterfzf

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /

#
# Ubuntu 18.04 Base
#
FROM ubuntu-18.04-base as ubuntu-18.04-oe
ENV PYREX_BASE none
ENV MY_REGISTRY none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && apt-get -y update && apt-get -y install \
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
    curl \
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
RUN python3 -m pip install iterfzf

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /

#
# Base image target.
#
# This stage sets up the minimal image startup and entry points. It also
# ensures that the en_US.UTF-8 locale is installed and set correctly.
#
FROM ${PYREX_BASE} as pyrex-base
ENV PYREX_BASE none
ENV MY_REGISTRY none

# Set Locales
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Add startup scripts
COPY ./run.sh /usr/libexec/pyrex/run
COPY ./capture.sh /usr/libexec/pyrex/capture
COPY ./bypass.sh /usr/libexec/pyrex/bypass
COPY ./entry.py /usr/libexec/pyrex/entry.py
COPY ./cleanup.py /usr/libexec/pyrex/cleanup.py
RUN chmod +x /usr/libexec/pyrex/cleanup.py \
    /usr/libexec/pyrex/entry.py \
    /usr/libexec/pyrex/run \
    /usr/libexec/pyrex/capture \
    /usr/libexec/pyrex/bypass

# Add startup script directory & test script.
COPY ./test_startup.sh /usr/libexec/pyrex/startup.d/

# Precompile python files for improved startup time
RUN python3 -m py_compile /usr/libexec/pyrex/*.py

# Remove all non-root users and groups so that there are no conflicts when the
# user is added
RUN getent passwd | cut -f1 -d: | grep -v '^root$' | xargs -L 1 userdel
RUN getent group | cut -f1 -d: | grep -v '^root$' | xargs -L 1 groupdel

# Use tini as the init process and instruct it to invoke the cleanup script
# once the primary command dies
ENTRYPOINT ["/usr/local/bin/tini", "-P", "/usr/libexec/pyrex/cleanup.py", "{}", ";", "--", "/usr/libexec/pyrex/entry.py"]

# The startup script is expected to chain along to some other
# command. By default, we'll use an interactive shell.
CMD ["/usr/libexec/pyrex/run", "/bin/bash"]

#
# Yocto compatible target image.
#
# The final image is the yocto compatible target image. This image has the
# Icecream destributed target setup correctly and install all of the desired
# yocto dependencies.
#
FROM pyrex-base as pyrex-oe
ENV PYREX_BASE none
ENV MY_REGISTRY none

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

