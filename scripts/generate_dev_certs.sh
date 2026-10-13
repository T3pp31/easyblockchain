#!/usr/bin/env bash
# 開発用自己署名 TLS 証明書を生成する。
set -euo pipefail
umask 077

OUT_DIR="${1:-./certs}"
mkdir -p "$OUT_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/key.pem" \
  -out "$OUT_DIR/cert.pem" \
  -days 365 \
  -subj "/CN=localhost"

# umask は新規作成時にしか効かないため、再実行時に既存鍵の緩い権限が残らないよう明示的に制限する
chmod 600 "$OUT_DIR/key.pem"
chmod 700 "$OUT_DIR" 2>/dev/null || true

echo "Generated: $OUT_DIR/cert.pem, $OUT_DIR/key.pem"
