# Pinned deliberately. `langchain/langgraph-api:3.11-wolfi` is a floating tag, so
# rebuilding the same commit months apart produces a different Agent Server and
# a different dependency set (the base image's /api/constraints.txt bounds what
# this project can install).
#
# Self-hosted: this must be compatible with your LangSmith platform version. An
# Agent Server much newer than the platform can fail to start. Match it to your
# platform, and regenerate with `langgraph dockerfile` after changing it.
FROM langchain/langgraph-api:0.13.0-py3.11-wolfi

# -- Adding local package . --
ADD . /deps/text2sql-agent
# -- End of local package . --

# -- Installing all local dependencies --
RUN for dep in /deps/*; do             echo "Installing $dep";             if [ -d "$dep" ]; then                 echo "Installing $dep";                 (cd "$dep" && PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir -c /api/constraints.txt -e .);             fi;         done
# -- End of local dependencies install --
ENV LANGSERVE_GRAPHS='{"simple_text2sql": "/deps/text2sql-agent/agents/simple_text2sql.py:agent"}'

# -- Ensure user deps didn't inadvertently overwrite langgraph-api
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api
# -- End of ensuring user deps didn't inadvertently overwrite langgraph-api --
# -- Removing build deps from the final image ~<:===~~~ --
RUN pip uninstall -y pip setuptools wheel
RUN rm -rf /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* /usr/local/lib/python*/site-packages/wheel* && find /usr/local/bin -name "pip*" -delete || true
RUN rm -rf /usr/lib/python*/site-packages/pip* /usr/lib/python*/site-packages/setuptools* /usr/lib/python*/site-packages/wheel* && find /usr/bin -name "pip*" -delete || true
RUN uv pip uninstall --system pip setuptools wheel && rm /usr/bin/uv /usr/bin/uvx

WORKDIR /deps/text2sql-agent
