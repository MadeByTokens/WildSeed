# Forest3D Docker image with GDAL, Blender, and Gazebo Harmonic
# Build: docker build -t forest3d -f docker/Dockerfile .
# Run:   docker run -v $(pwd):/workspace forest3d --help
# Run with GUI: docker run -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix -v $(pwd):/workspace forest3d launch

# Base image pinned by DIGEST (not the moving `22.04` tag) so the OS layer is frozen.
# ubuntu:22.04 == 22.04.5 LTS as of 2026-06-28. Update the digest deliberately.
FROM ubuntu:22.04@sha256:ce941a2a18bbb922e434d6d6d2b31e571a5c3826eaf6ada0a41dcc905bd2d906

LABEL maintainer="AI4Forest <khalid.bourr@gmail.com>"
LABEL description="Forest3D - Terrain and forest generation for Gazebo simulation"
LABEL version="0.1.0"

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Blender — pinned version, URL, and tarball checksum (verified after download).
ARG BLENDER_VERSION=4.2.3
ARG BLENDER_URL=https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz
ARG BLENDER_SHA256=3a64efd1982465395abab4259b4091d5c8c56054c7267e9633e4f702a71ea3f4
# Gazebo Harmonic apt version that works with this stack (gz-sim8 8.14.0).
ARG GZ_HARMONIC_VERSION=1.0.0-1~jammy
# pip pinned so a rebuild doesn't pull a newer resolver that changes the dependency graph.
ARG PIP_VERSION=26.1.2

# Install system dependencies including Python, GDAL, Blender requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    wget \
    xz-utils \
    gnupg \
    lsb-release \
    curl \
    software-properties-common \
    # Blender dependencies
    libxi6 \
    libxxf86vm1 \
    libxfixes3 \
    libxrender1 \
    libgl1 \
    libxkbcommon0 \
    # Gazebo/GUI dependencies
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    mesa-utils \
    && rm -rf /var/lib/apt/lists/*

# Add OSRF repository for Gazebo Harmonic
RUN curl -fsSL https://packages.osrfoundation.org/gazebo.gpg -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" > /etc/apt/sources.list.d/gazebo-stable.list

# Install Gazebo Harmonic (pinned version)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gz-harmonic=${GZ_HARMONIC_VERSION} \
    && rm -rf /var/lib/apt/lists/*

# Download and install Blender, verifying the tarball checksum before extracting.
RUN mkdir -p /opt/blender && \
    wget -q -O /tmp/blender.tar.xz ${BLENDER_URL} && \
    echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c - && \
    tar -xf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 && \
    rm /tmp/blender.tar.xz && \
    ln -s /opt/blender/blender /usr/local/bin/blender

# Set GDAL environment variables
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Set Blender path for Forest3D
ENV FOREST3D_BLENDER_PATH=/opt/blender/blender

# Set Gazebo model path
ENV GZ_SIM_RESOURCE_PATH=/workspace/models

# Create non-root user for security
RUN useradd -m -s /bin/bash forest3d
WORKDIR /home/forest3d

# Copy and install Forest3D
COPY --chown=forest3d:forest3d . /home/forest3d/forest3d-src

# Pin pip, then install Forest3D against the frozen constraints lock so the exact
# dependency versions that work in this image are reinstalled on every rebuild.
RUN pip3 install --no-cache-dir "pip==${PIP_VERSION}" && \
    pip3 install --no-cache-dir -c /home/forest3d/forest3d-src/docker/constraints.txt \
        /home/forest3d/forest3d-src && \
    pip3 install --no-cache-dir pygdal==$(gdal-config --version).* || true

USER forest3d

# Default working directory for mounting projects
WORKDIR /workspace

# Set environment for mounted projects
ENV FOREST3D_BASE_PATH=/workspace

ENTRYPOINT ["forest3d"]
CMD ["--help"]
