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

ARG PYREX_BASE=ubuntu-20.04-oe

#
# Base image for prebuilt static binaries
#
FROM alpine:3.9 AS prebuilt-base
ENV PYREX_BASE none

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

ENV ICECREAM_SHA1=6eec038c11a821b1d2848e8197cbc5b6bca6b3a0
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
RUN mkdir -p /usr/src/util-linux && \
    cd /usr/src/util-linux && \
    wget https://mirrors.edge.kernel.org/pub/linux/utils/util-linux/v2.36/util-linux-2.36.1.tar.xz && \
    tar -xvf util-linux-2.36.1.tar.xz && \
    cd util-linux-2.36.1 && \
    wget https://git.kernel.org/pub/scm/utils/util-linux/util-linux.git/patch/?id=8bf68f78d8a3c470e5a326989aa3e78385e1e79b -O setpriv_all_cap.patch && \
    patch -p1 < setpriv_all_cap.patch && \
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
# Prebuilt util-linux and libcap-ng for Ubuntu 14.04
#
FROM ubuntu:trusty AS prebuilt-util-linux-14.04
ENV PYREX_BASE none
RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
    apt-get -y update && apt-get -y install \
        build-essential \
        wget

# Work around Let's Encrypt certificate expiration September 2021
RUN sed -i 's/mozilla\/DST_Root_CA_X3.crt/!mozilla\/DST_Root_CA_X3.crt/g' /etc/ca-certificates.conf && \
    update-ca-certificates

RUN set -x && mkdir -p /usr/src/libcap-ng && \
    cd /usr/src/libcap-ng && \
    wget http://people.redhat.com/sgrubb/libcap-ng/libcap-ng-0.8.2.tar.gz && \
    tar -xvf libcap-ng-0.8.2.tar.gz && \
    cd libcap-ng-0.8.2 && \
    mkdir build && \
    cd build && \
    ../configure --prefix=/usr/local && \
    make -j$(nproc) LDFLAGS="-lpthread" && \
    make install-strip

RUN set -x && mkdir -p /usr/src/util-linux && \
    cd /usr/src/util-linux && \
    wget https://mirrors.edge.kernel.org/pub/linux/utils/util-linux/v2.36/util-linux-2.36.1.tar.xz && \
    tar -xvf util-linux-2.36.1.tar.xz && \
    cd util-linux-2.36.1 && \
    wget https://git.kernel.org/pub/scm/utils/util-linux/util-linux.git/patch/?id=8bf68f78d8a3c470e5a326989aa3e78385e1e79b -O setpriv_all_cap.patch && \
    patch -p1 < setpriv_all_cap.patch && \
    mkdir build && \
    cd build && \
    ../configure \
        --disable-doc \
        --disable-nls \
        --enable-setpriv \
        --without-bashcompletion \
        --prefix=/usr/local && \
    make -j$(nproc) && \
    make install-strip

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
FROM ubuntu:trusty as ubuntu-14.04-base
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
    apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        sudo \
        curl \
    && \
# Clean up apt-cache
    rm -rf /var/lib/apt/lists/* &&\
# generate utf8 locale
    locale-gen en_US.UTF-8 && \
    (locale -a | tee /dev/stderr | grep -qx en_US.utf8)

# Work around Let's Encrypt certificate expiration September 2021
RUN sed -i 's/mozilla\/DST_Root_CA_X3.crt/!mozilla\/DST_Root_CA_X3.crt/g' /etc/ca-certificates.conf && \
    update-ca-certificates

# Copy prebuilt items
COPY --from=prebuilt-util-linux-14.04 /usr/local/ /usr/local/
COPY --from=prebuilt-tini /dist/tini /

# Rebuild library cache after copying prebuilt utl-linux
RUN ldconfig -v

#
# Ubuntu 16.04 Base
#
FROM ubuntu:xenial as ubuntu-16.04-base
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
    apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        sudo \
        curl \
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
FROM ubuntu:bionic as ubuntu-18.04-base
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
    apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        setpriv \
        sudo \
        curl \
    && \
# Clean up apt-cache
    rm -rf /var/lib/apt/lists/* && \
# generate utf8 locale
    locale-gen en_US.UTF-8 && \
    (locale -a | tee /dev/stderr | grep -qx en_US.utf8)

# Copy prebuilt items
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 20.04 Base
#
FROM ubuntu:focal as ubuntu-20.04-base
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

# Install software required to run init scripts.
RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
    apt-get -y update && apt-get -y install \
        locales \
        lsb-release \
        ncurses-term \
        python \
        python3 \
        util-linux \
        sudo \
        curl \
    && \
# Clean up apt-cache
    rm -rf /var/lib/apt/lists/* && \
# generate utf8 locale
    locale-gen en_US.UTF-8 && \
    (locale -a | tee /dev/stderr | grep -qx en_US.utf8)

# Copy prebuilt items
COPY --from=prebuilt-setpriv /dist/setpriv /
COPY --from=prebuilt-tini /dist/tini /

#
# Ubuntu 14.04 Yocto Base
#
FROM ubuntu-14.04-base as ubuntu-14.04-oe
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
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
# An updated version of Git (from the PPA source above)
# that supports doing Yocto externalsrc recipes against free-
# standing working copies that use Git worktrees.
    git>=1:2.17.* \
# Corollary to the core Yocto gcc-multilib package. Allows various
# prebuilt native tools to work
    g++-multilib \
# Screen to enable devshell
    screen \
# Base OS stuff that reasonable workstations have, but which the registry image
# doesn't
    tzdata \
&& rm -rf /var/lib/apt/lists/*

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /

#
# Ubuntu 16.04 Yocto Base
#
FROM ubuntu-16.04-base as ubuntu-16.04-oe
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    ulimit -n 1024 && \
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
# An updated version of Git (from the PPA source above)
# that supports doing Yocto externalsrc recipes against free-
# standing working copies that use Git worktrees.
    git>=1:2.17.* \
# Corollary to the core Yocto gcc-multilib package. Allows various
# prebuilt native tools to work
    g++-multilib \
# Screen to enable devshell
    screen \
# Base OS stuff that reasonable workstations have, but which the registry image
# doesn't
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
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    sudo dpkg --add-architecture i386 && \
    ulimit -n 1024 && \
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
# Corollary to the core Yocto gcc-multilib package. Allows various
# prebuilt native tools to work
    g++-multilib \
# Screen to enable devshell
    screen \
# Base OS stuff that reasonable workstations have, but which the registry image
# doesn't
    tzdata \
# Testing requirements
    wine64 \
    wine32 \
&& rm -rf /var/lib/apt/lists/*

# Python modules used by resulttool
RUN python3 -m pip install iterfzf testtools python-subunit

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /

#
# Ubuntu 20.04 Base
#
FROM ubuntu-20.04-base as ubuntu-20.04-oe
ENV PYREX_BASE none
LABEL maintainer="Joshua Watt <Joshua.Watt@garmin.com>"

RUN set -x && export DEBIAN_FRONTEND=noninteractive && \
    sudo dpkg --add-architecture i386 && \
    ulimit -n 1024 && \
    apt -y update && apt upgrade apt -y && apt -y install \
# Poky 3.3 build dependencies
    gawk \
    wget \
    git \
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
    pylint3 \
    xterm \
    coreutils \
    python3-subunit \
    mesa-common-dev \
    zstd \
    liblz4-tool \
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
# Corollary to the core Yocto gcc-multilib package. Allows various
# prebuilt native tools to work
    g++-multilib \
# Screen to enable devshell
    screen \
# Base OS stuff that reasonable workstations have, but which the registry image
# doesn't
    tzdata \
# Dependencies for other layers
    xxd \
# Testing requirements
    wine64 \
    wine32 \
&& rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install iterfzf testtools python-subunit

# Copy prebuilt items
COPY --from=prebuilt-icecream /dist/icecream /

#
# Ubuntu 18.04 OE Test Image
#
FROM ubuntu-18.04-oe as ubuntu-18.04-oetest
ENV PYREX_BASE none

#
# Ubuntu 20.04 OE Test Image
#
FROM ubuntu-20.04-oe as ubuntu-20.04-oetest
ENV PYREX_BASE none

#
# Ubuntu 14.04 Base, customized with Garmin internal LAN configuration.
#
FROM ubuntu-14.04-oe AS ubuntu-14.04-oegarmin
ENV PYREX_BASE none

#
# Ubuntu 16.04 Base, customized with Garmin internal LAN configuration.
#
FROM ubuntu-16.04-oe AS ubuntu-16.04-oegarmin
ENV PYREX_BASE none

#
# Ubuntu 18.04 Base, customized with Garmin internal LAN configuration.
#
FROM ubuntu-18.04-oe AS ubuntu-18.04-oegarmin
ENV PYREX_BASE none

#
# Ubuntu 20.04 Base, customized with Garmin internal LAN configuration.
#
FROM ubuntu-20.04-oe AS ubuntu-20.04-oegarmin
ENV PYREX_BASE none

#
# Base image target.
#
# This stage sets up the minimal image startup and entry points. It also
# ensures that the en_US.UTF-8 locale is installed and set correctly.
#
FROM ${PYREX_BASE} as pyrex-base
ENV PYREX_BASE none

# Set Locales
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Add startup scripts
COPY ./run.sh /usr/libexec/pyrex/run
COPY ./capture.sh /usr/libexec/pyrex/capture
COPY ./entry.py /usr/libexec/pyrex/entry.py
COPY ./cleanup.py /usr/libexec/pyrex/cleanup.py
RUN chmod +x /usr/libexec/pyrex/cleanup.py \
    /usr/libexec/pyrex/entry.py \
    /usr/libexec/pyrex/run \
    /usr/libexec/pyrex/capture

# Add startup script directory & test script.
COPY ./test_startup.sh /usr/libexec/pyrex/startup.d/

# Precompile python files for improved startup time
RUN python3 -m py_compile /usr/libexec/pyrex/*.py

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

# Setup Icecream distributed compiling client. The client tries several IPC
# mechanisms to find the daemon, including connecting to a localhost TCP
# socket. Since the local Icecream daemon (iceccd) is not started when the
# container starts, the client will not find it and instead connect to the host
# Icecream daemon (as long as the container is run with --net=host).
RUN mkdir -p /usr/share/icecc/toolchain && \
    cd /usr/share/icecc/toolchain/ && \
    TC_NAME=$(mktemp) && \
    /usr/local/libexec/icecc/icecc-create-env --gcc $(which gcc) $(which g++) 5> $TC_NAME && \
    mv $(cat $TC_NAME) native-gcc.tar.gz && \
    rm $TC_NAME

ENV ICECC_VERSION=/usr/share/icecc/toolchain/native-gcc.tar.gz

#
# OE build image. Includes many additional packages for testing
#
FROM pyrex-oe as pyrex-oetest
ENV PYREX_BASE none

#
# Garmin developer image. Same as regular Yocto-compatible target image except
# it has additional Garmin-internal TLS root certificates installed into the
# trust store to facilitate using internal Garmin hosts whose certificate chain
# does not extend up to publicly registered CA's.
FROM pyrex-oe as pyrex-oegarmin
ENV PYREX_BASE none

RUN mkdir -p /usr/share/ca-certificates/garmin

# Root certificate that issued the cert for firewall TLS inspection.
# Certificate originally obtained from https://pki.garmin.com/crl/Garmin%20Root%20CA%20-%202018.cer
COPY garmin/Garmin_Root_CA_-_2018.cer /tmp/
RUN openssl x509 -inform DER -in /tmp/Garmin_Root_CA_-_2018.cer -out /usr/share/ca-certificates/garmin/Garmin_Root_CA_-_2018.crt
RUN echo garmin/Garmin_Root_CA_-_2018.crt >> /etc/ca-certificates.conf
RUN rm /tmp/Garmin_Root_CA_-_2018.cer

# Rebuild the CA database
RUN update-ca-certificates
