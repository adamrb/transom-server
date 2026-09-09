# agent-runner container: Python service + Node ACP agents.
#
# Build:  docker build -t plaud-agent-runner .
# Run (compose snippet in README.md):
#   docker run -d --network plaud-bridge-server_default \
#     -v ./runner-config:/config \
#     -v ~/.claude:/home/node/.claude \
#     plaud-agent-runner
#
# The config mounted at /config/config.toml must set listen = "0.0.0.0:8091"
# (the token is the guard inside the compose network). Claude Code
# subscription auth lives in ~/.claude on the host; claude-code-acp resolves
# it via $HOME (or CLAUDE_CONFIG_DIR), so mount it at the container user's
# HOME: /home/node/.claude.

FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ACP agents. @openai/codex is optional -- remove it for a slimmer image if
# you only use Claude (`codex acp` needs its own auth in ~/.codex).
RUN npm install -g @zed-industries/claude-code-acp @openai/codex

COPY agent_runner.py /app/agent_runner.py
# For `completion = "child"` actions: the helper a launched process calls to report its outcome.
COPY report-result.sh /app/report-result.sh

# node:22-slim ships user `node` = uid 1000, HOME=/home/node
USER node
ENV HOME=/home/node

EXPOSE 8091
ENTRYPOINT ["python3", "/app/agent_runner.py", "--config", "/config/config.toml"]
