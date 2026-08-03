# OR133C union-silhouette exact-reproduction repair

Repair only OR133B's classification-distance mismatch. The boundary residual
classifier must use distance to the morphological boundary of the union of the
left- and right-robot ID masks, exactly as OR133A did. Separate left/right
distance fields may still be reported descriptively, but they may not alter
silhouette, shadow, non-shadow, component, track, or association membership.

All other OR133B bindings remain byte-identical in meaning: expanded-development
positions `1-7`, `751` physical and `751` OR131 frames, seven OR132 occupancy
maps, seven physical sample files, one `751`-frame baseline ID rerender, exact
`825,548` triangles per frame, fixed components/tracks, lags `-3..3`, 40
circular-shift nulls at least five seconds away, and the `6/7` episode rule.

This is a new experiment identity, not an OR133B retry. It has zero intervention
DOF and no branch authorizes geometry or a simulator change. Positions `8-11`
and sibling pixels remain closed. If exact OR133A boundary mass does not
reproduce in all seven episodes, stop terminally. Otherwise close on follower
coupling, leader coupling, shared action/phase confounding, or retained-evidence
unidentifiability exactly as preregistered.

## Outcome

The repair reproduced OR133A exactly in all seven episodes over 751 frames.
Follower-speed association qualified in `5/7` episodes and leader innovation
in `3/7`, below the frozen `6/7` gate. The result is therefore
`TERMINAL_REGIONAL_DYNAMIC_RESIDUAL_UNIDENTIFIABLE_WITH_RETAINED_EVIDENCE`.
The actor/cable label is rejected; only a boundary-connected non-shadow
residual was measured. No intervention or regional-progress claim is allowed.
