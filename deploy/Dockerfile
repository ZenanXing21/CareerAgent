FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY career_agent ./career_agent
COPY vendor/liepin-cil/pyproject.toml vendor/liepin-cil/README.md ./vendor/liepin-cil/
COPY vendor/liepin-cil/liepin_cli ./vendor/liepin-cil/liepin_cli

RUN python -m pip install --no-cache-dir . ./vendor/liepin-cil

EXPOSE 8000
CMD ["python", "-m", "career_agent.web", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
