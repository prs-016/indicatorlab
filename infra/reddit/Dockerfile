# One linux/arm64 image for both Reddit jobs (build context = repo root; see infra/reddit/deploy.sh):
#   hourly  AWS Lambda container      CMD src.reddit.pipeline.lambda_handler
#   weekly  ECS Fargate task          entry point overridden to `python -m src.reddit.pipeline --mode weekly`
FROM public.ecr.aws/lambda/python:3.12

ENV PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

COPY requirements-pipeline.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4" \
 && pip install -r ${LAMBDA_TASK_ROOT}/requirements-pipeline.txt

# FinBERT at the revision pinned in config.yaml, baked in so no run ever downloads the model.
COPY config.yaml ${LAMBDA_TASK_ROOT}/
RUN python -c "import yaml; from huggingface_hub import snapshot_download; \
s = yaml.safe_load(open('${LAMBDA_TASK_ROOT}/config.yaml'))['sentiment']; \
snapshot_download(s['model'], revision=str(s['revision']))"

# Lambda's code directory is read-only: logs and library scratch go to /tmp; the model is read offline.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    REDDIT_LOG_DIR=/tmp/logs \
    HOME=/tmp

COPY src/ ${LAMBDA_TASK_ROOT}/src/

CMD ["src.reddit.pipeline.lambda_handler"]
