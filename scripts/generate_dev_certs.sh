#!/usr/bin/env bash
# 開発用自己署名 TLS 証明書を生成する。
# 注: -addext を使用するため OpenSSL 1.1.1 以上が必要。
set -euo pipefail

OUT_DIR="${1:-./certs}"
CERT_CN="${CERT_CN:-localhost}"
# CERT_SAN 未指定時は CERT_CN に追従した SAN を使う（主要クライアントは SAN のみを検証する）
CERT_SAN="${CERT_SAN:-DNS:${CERT_CN},IP:127.0.0.1,IP:::1}"

# -subj は '/' を RDN の区切りとして解釈するため、CN に含めると Subject の解析が崩れる
case "$CERT_CN" in
  */*)
    echo "ERROR: CERT_CN must not contain '/': ${CERT_CN}" >&2
    exit 1
    ;;
esac

mkdir -p "$OUT_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/key.pem" \
  -out "$OUT_DIR/cert.pem" \
  -days 365 \
  -subj "/CN=${CERT_CN}" \
  -addext "subjectAltName=${CERT_SAN}"

echo "Generated: $OUT_DIR/cert.pem, $OUT_DIR/key.pem (CN=${CERT_CN}, SAN=${CERT_SAN})"
