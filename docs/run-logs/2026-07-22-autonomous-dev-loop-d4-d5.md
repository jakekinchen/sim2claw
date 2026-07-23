# Autonomous dev-loop D4-D5 run log

Date: 2026-07-22

Proof class: deterministic repository control-plane and synthetic fixture
adapter evidence. This is not a simulator-campaign, training, transfer, or
physical-task result.

## Retained compatibility

- Before receipt SHA-256:
  `80e427ec673043ca875b226a73a832c45b587baa6547d87f0e38fbb82b7807cd`.
- Final v3 receipt SHA-256:
  `b2e671761cc77cd0ac2e83c3ec7bef9cb8ea01bcee1c17da4a3956bbd41d6c34`.
- Migration digest:
  `61ff4e4a697cf80c30d0bb8a65bec4b6463def4b7e1bfc12710a76c078efc172`.
- Four changed receipt fields: compiler hashes, evaluator identity, receipt
  digest, and schema version.
- Fourteen non-receipt output artifacts: byte-identical.

## Generic fixture proof

- Config SHA-256:
  `b2cacaf902a99dc282286a9042a60cca8858ba3109a13f62e5c0f2bb20520cc7`.
- Frozen fixture SHA-256:
  `1ef0750503f4a5d9428be4c4e3f2614fa06b7d991041f649220074ed759f2cc7`.
- Result-free request SHA-256:
  `7181028d5c2763fcb3931642023fe2d3299b2a640c2deba8c810755a05d476e0`.
- Derived result SHA-256:
  `63d4d2a7e392979fba1c21949b82cb222d16063da34a1667fd365207b0dd7bc3`.
- Adapter receipt SHA-256:
  `bc5c36ecb721c06f114155fc89490ad7276bfe7fb7013affb3e31427c70ffe09`.
- Operator receipt SHA-256:
  `5eb07d5a746465b4c3d9264ec4d1d4fec57ac143f57f4a0d4bd79f2de492da1f`.
- Result: `evaluator_pass`, one intervention, one anchor replay, no training,
  promotion, capture, or motion authority.

## Cleanup and tests

One hundred six legacy directories under the dedicated ignored
`outputs/sail/test-live-campaigns` root were verified as test-only files and
moved recoverably to `/tmp/sim2claw-test-live-campaigns-cleanup.P0YPNL`. A
fresh run left zero undeclared directories; the one current directory is the
declared ignored adapter proof input. The focused suite passed 47 tests in
4.12 seconds and the independent review passed with zero blocking findings.
