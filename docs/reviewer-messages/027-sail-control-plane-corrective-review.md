# Reviewer disposition 027: SAIL corrective control plane

Status: `SUPERSEDED BY SECOND ADVERSARIAL CORRECTIVE REVIEW`

The first corrective implementation kept the truthful terminal C2 abstention
and repaired the original proof/control defects, but this disposition was not
merge authority. A later adversarial review showed that mutually consistent
simulator raw/result/receipt files could still self-assert evaluator identity,
state remained caller-output-local, append preceded all closure validation,
and the final operator receipt had no read-time verifier. Those findings are
closed in reviewer message 028; this message is retained as history only.

The offline measurement lane performs no device enumeration or I/O. It admits
synthetic fixtures only after verifying the sealed packet, evaluator
code/config/source identity, raw and result hashes, common clock, sampling,
skew, calibration, phases, all-false authority, and separate measurement-trial
budget. The preregistered features return flexural-dominant,
actuator-dominant, or ambiguous abstention.

The corrected comparison is exact: 514 historical evaluations informed the
frozen retrospective decision; SAIL used zero additional evaluations after the
pause. No task gain, physical mechanism, simulator promotion, training
admission, capture authority, or motion authority follows.

Evidence hashes and full-suite counts are recorded in the corrective run log;
the final commit is reported in the worker handoff. Main merge and PR creation
remain owner decisions.
