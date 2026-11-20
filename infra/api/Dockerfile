# The dashboard API (src/api/main.py) as a Lambda container behind a Function URL (see infra/README.md).
# AWS Lambda Web Adapter forwards each request to uvicorn, so the FastAPI app runs unchanged; App Runner,
# the guide's choice, has not accepted new customers since Apr 30, 2026. Build context = repo root:
#   docker build --platform linux/arm64 -f infra/api/Dockerfile -t indicatorlab-api .
FROM public.ecr.aws/docker/library/python:3.12-slim
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

ENV PIP_NO_CACHE_DIR=1 PORT=8080
WORKDIR /app
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt
COPY config.yaml .
COPY config/ config/
COPY src/ src/

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
