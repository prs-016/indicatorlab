# Build from a dedicated reviewed context described in README.md, never all data.
FROM public.ecr.aws/lambda/python:3.13
COPY infra/india_live/requirements.txt ${LAMBDA_TASK_ROOT}/requirements-live.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-live.txt
COPY src/__init__.py ${LAMBDA_TASK_ROOT}/src/__init__.py
COPY src/live/__init__.py src/live/india.py src/live/dhan.py src/live/india_app.py src/live/india_watchdog.py ${LAMBDA_TASK_ROOT}/src/live/
# runtime contains only reviewed non-secret configuration/data, never .env files.
COPY runtime/ ${LAMBDA_TASK_ROOT}/runtime/
ENV INDIA_LIVE_CONFIG=/var/task/runtime/india-live.json
# Lambda uses this handler; ECS explicitly overrides the image entry point.
CMD ["src.live.india_watchdog.handler"]
