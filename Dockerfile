# Multi-stage Dockerfile for Comicarr
# Stage 1: Build frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /app

# Create backend directory structure for frontend build output
RUN mkdir -p backend/comicarr/static

# Copy frontend dependency files
COPY frontend/package.json frontend/package-lock.json ./frontend/

# Install frontend dependencies
RUN cd frontend && npm ci

# Copy frontend source code
COPY frontend/ ./frontend/

# Build frontend (outputs to ../backend/comicarr/static/frontend relative to frontend/)
RUN cd frontend && npm run build

# Stage 2: Final image with backend
FROM lsiobase/ubuntu:jammy

# Set version label
ARG BUILD_DATE
ARG VERSION
LABEL build_version="Linuxserver.io version:- ${VERSION} Build-date:- ${BUILD_DATE}"
LABEL maintainer="ComicarrDev"

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    COMICARR_DATA_DIR=/config \
    COMICARR_HOST_BIND_ADDRESS=0.0.0.0 \
    UV_CACHE_DIR=/config/.cache/uv \
    PATH="/usr/local/bin:${PATH}"

# Install base dependencies
RUN \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        build-essential \
        ca-certificates \
        software-properties-common

# Try to install Python 3.12 from deadsnakes PPA, fallback to building from source
# AKA, python 3.12 isn't available for ARM64 in the PPA as of late-2025
RUN \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    if apt-get install -y --no-install-recommends python3.12 python3.12-dev python3.12-distutils 2>/dev/null; then \
        echo "Python 3.12 installed from PPA"; \
        ln -sf /usr/bin/python3.12 /usr/local/bin/python3; \
    else \
        echo "Python 3.12 not in PPA, building from source..."; \
        apt-get install -y --no-install-recommends \
            libssl-dev \
            libbz2-dev \
            libreadline-dev \
            libsqlite3-dev \
            libncurses5-dev \
            libncursesw5-dev \
            xz-utils \
            tk-dev \
            libffi-dev \
            liblzma-dev \
            zlib1g-dev && \
        cd /tmp && \
        curl -f -O https://www.python.org/ftp/python/3.12.7/Python-3.12.7.tgz && \
        tar -xzf Python-3.12.7.tgz && \
        cd Python-3.12.7 && \
        ./configure --prefix=/usr/local --with-ensurepip=install && \
        make -j$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2) && \
        make altinstall && \
        ln -sf /usr/local/bin/python3.12 /usr/local/bin/python3 && \
        rm -rf /tmp/Python-3.12.7*; \
    fi && \
    python3 --version

# Install uv via pip (system-wide, accessible by all users)
RUN \
    python3 -m pip install --no-cache-dir --break-system-packages uv && \
    /usr/local/bin/uv --version

# Cleanup (keep build-essential for uv package compilation)
RUN \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory
WORKDIR /app

# Copy dependency files and backend code (needed for package build)
COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/

# Install backend dependencies (production only, no dev/test extras)
RUN /usr/local/bin/uv sync --frozen --no-dev

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/backend/comicarr/static/frontend ./backend/comicarr/static/frontend

# Add local files (s6-overlay scripts)
COPY root/cont-init.d/ /etc/cont-init.d/
COPY root/services.d/ /etc/services.d/

# Set permissions for s6-overlay scripts
RUN chmod -v +x /etc/cont-init.d/* /etc/services.d/*/run /etc/services.d/*/*.sh 2>/dev/null || true

# Volume mount points
VOLUME ["/config"]

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

