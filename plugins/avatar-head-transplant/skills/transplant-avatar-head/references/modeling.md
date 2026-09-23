# Fragile operations

## Unequal loops

Trace actual complete joining-loop connectivity, not a cached list of previously edited vertices. Equal counts with a twisted cycle are not a match.

Plan edge splits and internal connections together. A midpoint on a quad edge creates a pentagon until its interior is partitioned. Use a quad plus triangle, or an opposite-edge split and connecting edge when the surrounding flow warrants it. Mirror the construction; do not propagate splits across the entire body merely to maintain all-quads.

For example, quad `[0,1,2,3]` with midpoint `s` on edge `(0,1)` can become triangle `[s,1,2]` and quad `[0,s,2,3]` by connecting `s` to `2`. This illustrates connectivity, not a universal diagonal choice. Judge geometry and UV direction for each face.

Re-extract the selected interior/open joining cycles after topology edits. Old vertex IDs remain valid only if the edit returns an identity map. Adding BMesh layers may invalidate retained wrappers; create layers first. Operate in object mode or explicitly handle and flush edit BMesh state.

## Shape keys, UVs and weights

Interpolate every shape-key coordinate at the same split fraction. Preserve relative-key references, names, slider limits, drivers and original vertex order. Check a non-Basis key and split UV island: Basis-only verification is insufficient.

UVs are face-corner data: the two sides of a UV seam may have different values at one geometric vertex. Interpolate each side independently rather than averaging by vertex.

Weights store indices into the object's vertex-group list. Replacing mesh data and then removing/reordering the old groups can erase or misassign weights on the new mesh. Preserve the group index layout, or snapshot weights by bone name and rebuild from that snapshot afterward. Test eyes and limbs too: forced seam weights can hide an otherwise unbound avatar.

Moving a vertex by the same delta in every relative key preserves its expression deltas. Moving only Basis changes every expression. Distinguish meaningful seam motion from numerical noise using a recorded scale-aware tolerance, not a universal absolute cutoff.

## Rig mapping

Joining Armature objects does not consolidate a rig. Inspect rest matrices, parents, constraints, drivers, bone scale, modifier targets, object transforms and preserve-volume settings. Establish a semantic map preserving world-space rest anatomy. Do not blindly apply a pose as a new rest pose.

A zero-weight ancestor may still be necessary. Remap/retain facial bones and verify eye movement geometrically. Imported animation and transform drivers are dependencies, not disposable clutter.

## Geometry before normals

Record geometric face-normal angles separately from custom corner normals. Equal corner normals can hide a severe physical kink. Inspect several adjacent rows after every correction: moving a bend one row away is not fixing it.

Spacing alone is not a universal quality criterion. Judge collar width against neighboring rows and cross-sections. Distinguish Workbench shadow artifacts, texture differences, facial overlays and scalp openings from geometric defects using neutral materials and actual lighting.

Bake normals from rest/Basis geometry only. Preserve normals outside the transition and rebuild the donor after any geometry edit; a stale donor can conceal changed geometry.

## Retained internal collars

Use internal edge cycles when available. Match corresponding vertices while preserving the collar faces continuing past the junction on each original mesh. Inspect hidden ends and overlap under poses, so they stay inside and do not produce exposed double surfaces. Open-boundary joining is the fallback when usable internal loops are absent.

For the normal donor, explicitly identify the body-side outward surface below the join and head-side outward surface above it. Pass their face IDs to `bake_seam_normals(donor_keep_faces=...)`; only the temporary copies are trimmed. Review both sides and normals after transfer. An intentional overlap is not automatically a collision failure, and a generic BVH contact count does not prove the hidden collar stays inside.

## Source ownership and rig preservation

Retain recipient body/clothing and donor head/hair by default. An object/bone name is only a hint; classify by source, anatomy and surviving dependencies. Remove discarded recipient-head and donor-body exclusive branches only after checking retained weights, parents, constraints, drivers and animation. Preserve body twist/corrective bones and head-attached eye/jaw/hair bones. Rig minimization is not a goal.

Use identical world fit for donor head geometry and attached bones. Establish nonzero head/tail before roll orientation; assigning a matrix to a zero-length new EditBone produced incorrect forward-facing bones in a real test. `copy_head_bones` centralizes the supported operation; unsupported constraints/animation need an explicit remapping. Verify endpoints and all axes, then compare source/result deformed vertices under matching rotations. A continuous neck alone cannot validate eye movement.
