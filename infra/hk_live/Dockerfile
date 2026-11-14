FROM public.ecr.aws/lambda/python:3.13
COPY infra/hk_live/requirements.txt ${LAMBDA_TASK_ROOT}/requirements-hk.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-hk.txt
COPY src/__init__.py ${LAMBDA_TASK_ROOT}/src/__init__.py
COPY src/hk/__init__.py src/hk/calendar.py src/hk/live.py ${LAMBDA_TASK_ROOT}/src/hk/
COPY src/hk/cloud/ ${LAMBDA_TASK_ROOT}/src/hk/cloud/
COPY config/hsi_constituents_2026-11-04.csv ${LAMBDA_TASK_ROOT}/config/hsi_constituents_2026-11-04.csv
CMD ["src.hk.cloud.watchdog.handler"]
