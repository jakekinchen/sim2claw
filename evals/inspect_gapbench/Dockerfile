FROM node:22.17.1-bookworm-slim

ARG CODEX_CLI_VERSION=0.144.6
ARG CLAUDE_CODE_VERSION=2.1.199

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git jq python3 ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global \
        "@openai/codex@${CODEX_CLI_VERSION}" \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

RUN useradd --create-home --uid 10001 --shell /bin/bash agent \
    && install -d -m 0777 -o agent -g agent /workspace \
    && install -d -m 0777 -o agent -g agent /home/agent/.codex /home/agent/.claude

ENV HOME=/home/agent \
    CODEX_HOME=/home/agent/.codex \
    CLAUDE_CONFIG_DIR=/home/agent/.claude \
    DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1

WORKDIR /workspace
# Inspect's injected sandbox supervisor starts as root, then the agent adapters
# explicitly run Codex and Claude as the unprivileged `agent` user.
USER root

CMD ["sleep", "infinity"]
