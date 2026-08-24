#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
if python /tests/verify_answer.py; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi
