# OR87 reject-only validation camera/workcell/response evaluation

OR87 rendered the complete frozen OR82 camera, OR84 workcell transform, and OR86 uniform camera response on all three preregistered validation episodes. It performed no fit, selection, development retuning, replay, or evaluator-heldout read.

Five of six metric gates and all seven integrity gates pass across `328` renderer-native frames. Mean similarity is `0.842051`, p10 is `0.825361`, motion-union similarity is `0.799354`, and all phase and episode mean gates pass. Tolerant-edge F1 is `0.391734`, below the frozen `0.4` minimum, so the candidate is rejected and the original evaluator-heldout remains sealed.

The admissible continuation starts a new preregistered split. The three opened validation episodes become development evidence; original split positions `8-9` become fresh validation; positions `10-11` remain the final evaluator-heldout. OR88 freezes this reallocation without decoding any original held-out pixels.
