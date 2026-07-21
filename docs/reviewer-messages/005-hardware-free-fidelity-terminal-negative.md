# Reviewer message 005: retained-data fidelity closeout

We tested the physical plausibility of the board scale and then ran an
action-frozen simulator mechanism campaign. A visible tag36h11 id 0 supports the
355.6 mm board hypothesis under the nominal printed-tag model and materially
disfavors the optimizer's 301.3 mm compensation, but does not establish metric
authority because the print was never measured.

The main quantitative improvement comes from simulator semantics and actuator
response, not policy correction. Timestamp-aligned record-then-ZOH replay plus
a grouped-CV 110 ms delay reduces joint RMS from 2.563 to 1.461 degrees. A
2-degree shoulder-lift/elbow servo-deadband model selected independently in all
four folds reduces joint RMS to 1.296 degrees and EE RMS from 20.843 to
12.936 mm overall. Source action arrays are byte-identical across every variant.

The same unchanged replay improves simulated contact from 9/11 to 11/11 and
lift from 0/11 to 2/11, but never produces a strict task success. A frozen
rubber-tip contact ensemble spans only 2--3 lifts and 0 successes. Since retained
video provides endpoint appearance intervals rather than authoritative contact,
retention, or transport labels, selecting a contact prior would be overfitting.

Our final claim is therefore diagnostic: we localize and reduce the trace gap,
rule out board-scale compensation and reset semantics as primary explanations,
and isolate the remaining unidentifiable gap to grasp contact geometry,
retention/slip, and transport observability. We do not claim a physically
calibrated simulator, successful policy, training admission, or sim-to-real
transfer.
