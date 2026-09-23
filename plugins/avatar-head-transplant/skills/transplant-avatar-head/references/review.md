# Completed Blender samples and feedback

Present editable Blender samples with geometry and normals already finished, then obtain a final choice. Image exporters remain optional diagnostics; do not make static images the main approval interface.

## Recoverable baseline and candidate versions

Save an immutable task-local baseline with `save_review_checkpoint()` before experimenting. Keep the current deliverable unchanged. Use `create_review_scene(label, source_scene)` to branch independent scenes, normally `Review_A_v1`, `Review_B_v1`, and `Review_C_v1`. The helper copies scene objects/data and remaps internal dependencies; resolve any external rig dependency before presenting a candidate as independent.

Each candidate represents a meaningful head-loop/body-loop combination: for example a higher junction, a lower junction, or a route that better follows existing topology. These are examples, not fixed anatomical prescriptions. Prefer 2–3 viable choices; if only one makes sense, explain why instead of manufacturing poor alternatives. Record source loops before cutting, their markers, and subsequent vertex-ID maps.

Fully execute internal-loop fitting (preserving collar overlap), local split/connection plans, paired midpoint placement, neighboring shape adjustment, rig consolidation, seam weights/keys, normal smoothing and transfer on each candidate. A collection containing two unconnected avatars or only loop curves is not a finished sample. Retain separate head/body meshes and the intended clothing/head attachments on one armature, as required for final delivery.

Save immutable checkpoints with unique names after construction and before significant revisions. `discard_review_scene()` can discard a marked candidate; it must never delete the baseline. To undo feedback-driven experimentation, switch to an earlier kept scene or append the scene from its task-owned library checkpoint and activate it and branch a new version. Do not rely on Ctrl-Z history, and do not accumulate uncontrolled edits on an only copy.

## What the user sees in Blender

- Default to a native Blender side-by-side A/B/C comparison scene via `create_review_comparison`, plus canonical individual candidate scenes for detailed inspection. Frame the actual avatars together, use identical neutral shading and keep labels readable. Provide neck-only and full retained-avatar views. Comparison offsets and labels must not enter final delivery.
- In a review-only reference collection, show the selected source head loop and body loop in different colors, with optional pair numbers. Preserve both the pre-cut reference and finished sample so the user can understand which loop combination produced it.
- Default to the real shaded candidate with neutral material and consistent lighting. Let the user orbit/zoom and switch to wireframe or edit mode to inspect actual vertices and faces. Make overlays, bones and vertex visibility available; do not leave them disabled without explanation.
- Provide pose checks for the head/neck and relevant limbs. Ensure samples use their own mesh/armature/key data; editing or posing one candidate must not alter another or the baseline.
- Mark source references and labels clearly; they must not be mistaken for duplicate final surfaces. Keep them out of final export.

Materials/images may be shared by scene copies. Assign independent neutral review materials instead of modifying source materials, and restore original material assignments for delivery. Inspect custom node setups and resolve the helper’s reported external rig dependencies before presenting independent samples. Compare under the same material/lighting conditions. Before/after normal copies can help diagnose a specific concern, but the default review is of the fully finished candidates, not another mandatory intermediate approval.

Example (translate into the user's language): "A uses the higher joining loops; B uses the middle loops. Both samples are finished. Inspect them in Blender and tell me which version to finalize or what to change."

## Feedback and final confirmation

Record candidate/version, source checkpoint, loop choices, topology plan, normal settings, validation results and the user's actual response in `work/review.json`.

- "Raise the back of B's neck slightly" means branch B_v2, modify it, finish its normals and tests again, then show B_v2. It is not permission to publish B_v1 or an unseen revision.
- "Finalize B_v2" authorizes committing that completed version and the requested deliverables.
- Silence, elapsed time, a passing test, a broad initial request or a mere preference without final confirmation does not finalize a candidate.

Wait for an explicit response about a concrete completed sample. If necessary, end the turn awaiting feedback; continue only independent preparation. No default approval or approval timeout.

After final confirmation, assemble only the chosen candidate's deliverable objects in a clean final scene. Remove reference geometry, labels, preview offsets and temporary donors. Verify one `Armature`, separate head/body plus the requested retained attachment meshes, preserved data and intended pose/materials. Save the final `.blend` to the deliverables location and perform the reopened checks; export FBX only if requested and verify by reimport. Saving checkpoints for review before confirmation is allowed; replacing final deliverables or exporting the final avatar is not.
