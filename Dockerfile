# Lambda のコンテナイメージ用のベース。Stage 8 でそのまま使えるように
# 最初からこれを選んでおく。ローカル実行にも使える。
FROM public.ecr.aws/lambda/python:3.12

# 依存の解決だけを先に行う。requirements の内容が変わらない限り、
# ここまでのレイヤ（boto3 など aws extra の依存一式）はキャッシュが効く。
# --extra aws で Lambda 実行に要る boto3 系を含め、--no-emit-project で
# 自分自身（sales-report）の editable install はここでは出さない。
# アプリ本体は次の COPY src/ でそのまま配置するので、distribution としての
# インストールは不要（Lambda ランタイムが LAMBDA_TASK_ROOT を sys.path に
# 加えるため import は通る）。
#
# boto3 をここで明示的に固定するのは慣習ではなく AWS の公式な推奨事項。
# Lambda の Python ランタイムには boto3/botocore が同梱されているが、AWS は
# 「ランタイム同梱版に依存せず、boto3 を含む全依存関係を自分のデプロイパッケージに
# 含めることを推奨する（ランタイムが同梱版を更新した際のバージョン不整合を防ぐため）」
# と明記している。
# 参照: https://docs.aws.amazon.com/lambda/latest/dg/python-package.html
#   ("Runtime dependencies in Python" - Important 注記)
# EXPERIMENT(stage-07 Q1): COPY src/ を依存インストールより前に一時的に動かす。
# 演習1の検証用。検証後は元の順序（依存を先、コードを後）に戻す。
COPY src/ "${LAMBDA_TASK_ROOT}/"

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-dev --extra aws --no-emit-project --format requirements-txt > requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

CMD ["sales_report.lambda_handler.handler"]
