FROM python:3.13-alpine3.23@sha256:75f27d686432419c9d42420b2b9ef605868c7a0682a6be10a6601fad46c2df01 AS certificates
FROM ubuntu:22.04@sha256:829f6df217bcbae2b371026e81711d1a787c61b2967ad09d015063663ebafbf7
COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
# Test-image provisioning only: retain Ubuntu's official hosts and use HTTPS.
# The installer itself never changes the target machine's repository settings.
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update && apt-get install -y --no-install-recommends bash curl python3 ca-certificates tar zstd && rm -rf /var/lib/apt/lists/*
