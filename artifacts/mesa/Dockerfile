FROM python:3.13-alpine3.23@sha256:75f27d686432419c9d42420b2b9ef605868c7a0682a6be10a6601fad46c2df01
RUN apk add --no-cache build-base cmake meson ninja linux-headers pkgconf \
    llvm21-dev clang21-dev libclc-dev spirv-llvm-translator-dev spirv-tools-dev \
    libdrm-dev expat-dev zlib-dev zstd-dev elfutils-dev bison flex binutils
RUN python -m pip install --no-cache-dir mako==1.3.10 pyyaml==6.0.3 packaging==25.0
COPY build-musl.sh /build-musl.sh
ENTRYPOINT ["sh", "/build-musl.sh"]
