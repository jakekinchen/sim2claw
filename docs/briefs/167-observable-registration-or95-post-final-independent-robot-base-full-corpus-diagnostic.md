# OR95 post-final independent robot-base full-corpus diagnostic

OR94's independent left/right base transforms improve six exact comparison frames. OR95 freezes them and renders every fixed `5 Hz` state across all eleven retained action-identical episodes, producing eleven simulator videos and frame-level full, motion, whole-edge, board, and outside-board metrics.

The original full-frame gates remain, but cannot establish same-video similarity alone. OR95 additionally requires board edge F1 mean/p10 of `0.60/0.50`, outside-board mean/p10 of `0.60/0.45`, and every episode's outside-board mean to reach `0.50`. No fit, candidate selection, threshold change, retry, action change, timing change, or simulator replay is allowed.

All corpus pixels were opened by prior cards. This is a retrospective temporal diagnostic, not held-out validation or prospective generalization, and cannot establish physics, physical transfer, or simulator promotion.
