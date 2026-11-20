# The daily Wikipedia job (src/wiki_daily.py) as a Lambda container, started at 06:00 UTC by
# EventBridge Scheduler (see infra/README.md). Build context = repo root:
#   docker build --platform linux/arm64 -f infra/wikipedia/Dockerfile -t indicatorlab-wikipedia .
FROM public.ecr.aws/lambda/python:3.12

ENV PIP_NO_CACHE_DIR=1 HOME=/tmp
COPY requirements-api.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements-api.txt
COPY config.yaml ${LAMBDA_TASK_ROOT}/
COPY config/ ${LAMBDA_TASK_ROOT}/config/
COPY src/ ${LAMBDA_TASK_ROOT}/src/

CMD ["src.wiki_daily.lambda_handler"]
