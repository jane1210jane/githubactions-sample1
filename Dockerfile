# Lambda のコンテナイメージ用のベース。Stage 8 でそのまま使えるように
# 最初からこれを選んでおく。ローカル実行にも使える。
FROM public.ecr.aws/lambda/python:3.12

# 依存の解決だけを先に行う。requirements の内容が変わらない限り、
# ここまでのレイヤはキャッシュが効く。
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-dev --format requirements-txt > requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

# アプリ本体は最後に置く。コードだけ変えたときに再利用できるレイヤを増やすため。
COPY src/ "${LAMBDA_TASK_ROOT}/"

CMD ["sales_report.lambda_handler.handler"]
