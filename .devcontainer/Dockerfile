# OpenSolve Pipe Development Container
# Base: Python 3.11 + Node.js 20 LTS

FROM mcr.microsoft.com/devcontainers/python:3.11

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Configure apt and install packages
RUN apt-get update \
    && apt-get -y install --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
        build-essential \
        libpq-dev \
        postgresql-client \
        redis-tools \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 LTS using nvm
ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=20.11.0

RUN mkdir -p $NVM_DIR \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash \
    && . $NVM_DIR/nvm.sh \
    && nvm install $NODE_VERSION \
    && nvm alias default $NODE_VERSION \
    && nvm use default

# Add node and npm to path
ENV NODE_PATH=$NVM_DIR/versions/node/v$NODE_VERSION/lib/node_modules
ENV PATH=$NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH

# Install global npm packages
RUN npm install -g pnpm eslint prettier

# Install Python development tools
# Note: black and isort removed - using Ruff for linting and formatting
RUN pip install --no-cache-dir \
    ruff \
    mypy \
    pytest \
    pytest-cov \
    pytest-asyncio \
    pre-commit

# Set up non-root user (vscode user is created by base image)
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Ensure proper permissions for workspace
RUN mkdir -p /workspace \
    && chown -R $USERNAME:$USERNAME /workspace

# Switch back to dialog for any ad-hoc use of apt-get
ENV DEBIAN_FRONTEND=dialog

# Set working directory
WORKDIR /workspace

# Set default user
USER $USERNAME
