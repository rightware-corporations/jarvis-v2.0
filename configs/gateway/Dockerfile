# syntax=docker/dockerfile:1
# RIGHTWARE Tool Gateway runtime image (JRV-P3A). Build ONLY through `python -m rightware.gateway.image build`,
# which stages the minimal context, pins the base by digest, checks the OpenJarvis pin and records the manifest.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS build
ARG VENDOR_VERSION
ARG SOURCE_DATE_EPOCH
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PIP_ROOT_USER_ACTION=ignore \
    UV_PROJECT_ENVIRONMENT=/opt/ojvenv UV_PYTHON=/usr/local/bin/python3.12 UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy UV_NO_CACHE=1 UV_COMPILE_BYTECODE=0 PYTHONDONTWRITEBYTECODE=1 \
    SETUPTOOLS_SCM_PRETEND_VERSION=${VENDOR_VERSION}
COPY build-requirements.txt /build/build-requirements.txt
# The optional build secret "ca" is only a TLS trust bundle for an outbound proxy; it is never stored in a layer.
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-compile --require-hashes --no-deps -r /build/build-requirements.txt
COPY vendor/openjarvis /src/openjarvis
WORKDIR /src/openjarvis
# Runtime dependencies come ONLY from the pinned vendor's uv.lock (hash-verified, --frozen: no re-resolution).
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca UV_NATIVE_TLS=1; fi; \
    uv sync --frozen --no-dev --no-editable \
    && /opt/ojvenv/bin/python -B -c "import openjarvis, httpx" \
    && find /opt/ojvenv -name uv_cache.json -path '*.dist-info/*' -print -delete \
    && sed -i '/\.dist-info\/uv_cache\.json,/d' /opt/ojvenv/lib/python3.12/site-packages/*.dist-info/RECORD \
    && mkdir -p /out/opt && mv /opt/ojvenv /out/opt/ojvenv
COPY rightware /out/app/rightware
# Every timestamp in the copied tree (including /opt and /app themselves) = the pin's commit time.
RUN find /out -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +

FROM ${BASE_IMAGE}
ARG SOURCE_DATE_EPOCH
COPY --from=build /out/ /
# No setuid/setgid binaries; fixed unprivileged runtime user.
RUN touch /tmp/.mark && sleep 1 \
    && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
    && groupadd --gid 10001 rightware && useradd --uid 10001 --gid 10001 --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin rightware \
    && find / -xdev -cnewer /tmp/.mark ! -path /tmp/.mark -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} + \
    && rm -f /tmp/.mark && touch -h -d "@${SOURCE_DATE_EPOCH}" /tmp
ENV PATH=/opt/ojvenv/bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
USER 10001:10001
