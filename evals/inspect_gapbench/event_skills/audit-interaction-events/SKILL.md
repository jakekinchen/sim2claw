---
name: audit-interaction-events
description: Audit deterministic Sim2Claw interaction candidates and annotate only visible evidence in synchronized frame strips.
---

# Audit Interaction Events

1. Call `event_status` first and preserve its recording, partition, prompt, and
   evidence digests.
2. Read the ordered event proposals and event-conditioned metrics. Treat the
   gripper/current result as a mechanical-load proxy, not physical contact.
3. Read the interaction strip once. Judge only visible source occupancy,
   overlap, object co-motion, destination occupancy, release, exact-contact
   visibility, and occlusion.
4. Use `ambiguous` or `not_visible` whenever occlusion prevents a conclusion.
   Never infer metric coordinates, depth, force, contact time, or task success.
5. Submit one visual annotation with the exact finite fields and the prompt
   digest returned by `event_status`. The receipt outcome was not shown.
6. Submit the event audit using the returned annotation digest and
   `claim_boundary=retrospective_multimodal_candidates_only`.

Completion proves a bounded annotation/audit record only. It does not prove
the annotation is correct, that contact occurred, that the object was securely
grasped, that the simulator is calibrated, or that a policy transfers.
