#!/usr/bin/env bash
# 開発用自己署名 TLS 証明書を生成する。
set -euo pipefail

OUT_DIR="${1:-./certs}"
mkdir -p "$OUT_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/key.pem" \
  -out "$OUT_DIR/cert.pem" \
  -days 365 \
  -subj "/CN=localhost"

echo "Generated: $OUT_DIR/cert.pem, $OUT_DIR/key.pem"
