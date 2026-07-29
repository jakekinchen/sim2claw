# Brief 071 — proxy-collision V2 quarantine and V3 freeze

Decision: CONTINUE after commit and push.

V2 generated episode and trace files but failed before summary receipt
serialization. The output was not parsed or inspected. Its path/content
aggregate is bound and the whole directory is non-admissible.

V3 adds only the missing JSON `dumps` pass-through. The collision mechanism,
exact actions, plants, resets, gates, and authority are unchanged. Execute V3
exactly once after its freeze is pushed.
