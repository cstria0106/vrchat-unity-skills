---
name: transplant-avatar-head
description: Transplant a rigged avatar head onto another avatar's body in Blender from FBX or an existing scene. Align eyes, chin and occiput; construct matching neck loops; preserve UVs, weights and shape keys; validate geometry and transfer custom normals to separate meshes on one armature. Use for head swaps and repairing their neck seams.
---

# Avatar head transplant

Produce a donor head and recipient body as separate meshes driven by one armature, with a continuous neck in rest and motion. Use the configured Blender MCP connection. This is an inspected modeling workflow, not a universal one-click conversion. Unfamiliar avatars require discovery and explicit correspondence; unresolved anatomy or rig semantics must not be guessed.

Use `scripts/avatar_tools.py` inside Blender for measurements and explicit edits. Read [the tool contract](references/tools.md) before calling a helper. Helpers do not certify artistic completion. Keep diagnostic assets and test copies in the task workspace, separate from source FBX files. Tested with Blender 5.1.2; other versions require compatibility checks. The helpers run in Blender Python with its bundled NumPy. Optional image renderers need standard Python, NumPy and Matplotlib.

## Language and Blender connection

Write progress updates, explanations, feedback requests, review instructions and final reports in the user's language. Keep API identifiers, source object/bone names and file paths unchanged; the English wording in this package is not a requirement to answer in English.

Before importing, editing, launching a Blender process or preparing candidates, discover the configured Blender MCP tools and make a read-only request for the current file, scene and mode. A running Blender process or a listed tool alone does not confirm connectivity.

If the tool is unavailable, the request fails, or the active Blender connection cannot be confirmed, pause the transplant workflow. Tell the user to open the intended Blender file, enable/start their configured Blender MCP add-on or server, and verify that their assistant is connected to it. Ask them to let you know when it is ready. Do not auto-launch/reinstall Blender, repeatedly retry, or use background Blender as a workaround. Resume only after a successful read-only connection check. Apply this rule again if the connection is lost during work.

With connectivity established, isolated background Blender is appropriate for verification on copies; it does not replace native Blender review. Preserve unsaved work in the connected instance.

## Completed Blender samples and final confirmation

Present **actual completed Blender candidates** for final review. Read [the review protocol](references/review.md). Prepare normally 2–3 meaningfully different joining-loop choices as independent candidate scenes, including the actual joining topology, fitting, rigging and finished custom normals. Keep the baseline and working deliverable untouched. A task-local checkpoint or candidate `.blend` is a review artifact, not final delivery.

Let the user orbit, inspect wireframe/shading and try poses in Blender. Clearly label candidates A/B/C and their chosen head/body loops. On feedback, branch a new version from the baseline or a known candidate checkpoint; do not rely on Undo history. Show the revised completed sample again. Only an explicit final confirmation of a specific candidate/version authorizes final application, delivery save or requested export. Silence, a broad initial request and test success are not confirmation. Reuse confirmation for the identical candidate; changed candidates require confirmation again.

## 1. Discover the actual inputs

- Inspect the connected Blender file, objects and mode. Preserve unrelated open work; the MCP instance may differ from the user's visible window. Save a checkpoint before edits.
- Import sources with distinct provenance labels. Identify head/body by anatomy, connected components, materials, bounds and bone influences. `Body`, `body`, `face` and other names are hints only. Default retained set: recipient body, clothing and their supporting rig; donor head, eyes, teeth, facial overlays, hair/head accessories and their supporting rig. Remove the replaced recipient head and its attached parts, and the donor body/clothing and their exclusive rig branches. Record a source/anatomy ownership manifest; a combined mesh needs component-level inspection. A user-requested narrower set overrides this default.
- Record the original object name and mesh datablock name before adding import/review labels; store source identity separately from display labels.
- Capture baseline topology, UV corner data, materials/image paths, weights, shape-key names/relative relationships/drivers and rest bones. Keep originals for differential checks. Repair texture references only with inspected supplied textures, not guessed similar filenames or UV-layout images.
- Establish units, world transforms and symmetry plane. Inspect the overlap region to choose a useful junction; the original mesh end is not automatically the best junction. `boundary_loops` supports existing openings (`OPEN`), inspected interior edge selections (`EDGES`) and temporary plane sections (`SECTION`). Mouth/scalp/eye openings and incidental sections are not automatically necks.

Completion: retained anatomy, actual neck candidates, provenance, coordinate system and preservation contracts are established from the files and views.

## 2. Align the head before fitting the neck

- Compare original recipient and donor heads in the same front/side orthographic views. Mark corresponding left/right eye centers, chin tip and occiput. Eye bones are useful hints, but verify them against the visible eyes.
- `fit_landmarks()` proposes positive uniform scale, proper rotation and translation. Inspect residuals and overlays; fit eye height/center, chin position and posterior silhouette together. Ear-inclusive width or crown height alone cannot determine scale.
- Compare the original recipient and fitted donor directly in Blender at matching front/side views. Image exporters remain optional diagnostics or a user-requested fallback, not the primary review. A small fitting residual alone does not approve the placement.
- Preserve donor facial identity. Crown, nose, ears and the overall outline are secondary checks, not constraints that justify facial deformation. Different head shapes need not have identical outlines. Report meaningful residual differences rather than claiming exact agreement.
- Freeze the inspected candidate placement and record its matrix and front/side comparison. A later placement change invalidates neck fitting, affected binding work, normal transfer and their acceptance results.

## 3. Build corresponding neck topology

Read [construction and preservation](references/modeling.md) before topology or rig edits.

Prepare these operations on independent candidate scenes. Keep source provenance, chosen loops and vertex-ID maps for every candidate. Save a baseline checkpoint first; use `create_review_scene()` and `save_review_checkpoint()` to branch recoverable versions.

- Find several useful head/body joining-loop combinations in the overlap region. Prefer a small curated set with meaningful differences in position, curvature, overlap removal or topology cost; do not generate all combinations or invent poor candidates to reach a quota. Show which head loop is paired with which body loop for each. `SECTION` points without vertex IDs require real cut construction. An arbitrary section/intersection is not automatically an anatomical join.
- Preserve useful **interior joining loops and the faces above/below them**. This is the default junction: coincident internal vertex pairs, with controlled overlapping collar surfaces. Use end-to-end open boundaries only when no usable internal loop exists. A loop inside a mesh is not a request to trim the mesh there.
- Order the selected actual edge cycles with `EDGES` (or `OPEN` for the fallback). Visually establish front/back/side anchors and left/right partners. Inspect front, side, back and underside wireframe views. Proximity searches may suggest candidates, but do not establish correspondence.
- If counts differ, design the smallest local **split-and-connection** plan. Connect added vertices through adjacent faces into intentional quads and explicit transition triangles. Avoid global subdivision and least-common-multiple densification. An edge split leaving a pentagon does not finish the task.
- `apply_topology_plan()` executes explicit split edges and diagonals on an isolated candidate and rejects newly introduced/touched n-gons. Verify face flow, UV seams, every shape-key layer and interpolated weights. A helper refusal means the plan needs correction, not bypassing its check.
- Compute each inspected pair's world-space midpoint and place both vertices there without welding. Check symmetry. If exact midpoints are asymmetric, reconcile the input regions symmetrically or clarify intentional asymmetry; silently averaging the targets again is not the requested midpoint operation.
- Model neighboring rows individually and symmetrically. `apply_vertex_targets()` executes reviewed coordinates across all keys; it is not an automatic neck fitter. Maintain spacing, curvature, face orientation and separation. Check for pinching, foldovers, intersections, or a bend merely shifted onto the next row.

Create **real connected samples** for each candidate, not only loop curves or calculated target points. Keep actual head/body meshes separate at coincident seams, as required for the final structure. Store source-loop markers/reference geometry in a clearly separate review-only collection. Complete the remaining rig/normal phases before asking the user to select/finalize a sample. Geometry diagrams may help internal diagnosis, but do not replace an editable Blender candidate.

Completion: full joining-loop vertex **and edge** correspondence, cyclic order, symmetry and acceptable local triangles/quads. Coordinate equality alone is insufficient. Inspect geometry independently of custom normals.

## 4. Consolidate deformation

- Prefer the recipient skeleton unless the inspected rig warrants a different explicit choice. Map bones by anatomy, hierarchy, rest transforms and actual influences; equal names alone are insufficient.
- Use `copy_head_bones()` for explicitly mapped donor head bones and `audit_bone_fit()` to compare their heads, tails and all three local axes. Apply exactly the same uniform world transform to donor head geometry and attached bones (Eye, jaw, hair, etc.), preserving their original relative placement and orientation. Consolidate shared roles explicitly. Name the single resulting armature `Armature` unless specified otherwise. Preserve evaluated rest anatomy while rebinding.
- Preserve existing weights outside the transition; avoid automatic weight regeneration. Seam partners need matching effective bone influences and deformation settings. Retain bones supporting the kept body/clothing and head/hair, including twist/corrective/control bones. Remove only branches exclusive to discarded source parts after checking surviving weights, ancestors, constraints, drivers and animation references. Zero weight alone is not a deletion criterion; do not perform a general rig reduction.
- Inspect shape-key seam motion. Create an explicitly driven counterpart or a documented mapping when one side moves the seam. Preserve original names and facial behavior; do not erase meaningful deltas to make checks pass.
- `pose_probe()` checks seam continuity, not correctness of eye/limb movement. Separately use `compare_deformation()` on source and result under matching local bone rotations and expression values, with the recorded fit and preserved vertex correspondence. Test actual influenced eye/head attachment vertices, retained corrective/twist-driven limbs, and seam-affecting keys. Restore states and report continuity versus deformation preservation separately.

## 5. Transfer normals after geometry passes

Finish this normal result on each independent candidate before review. No intermediate normal approval is required; the final completed sample is what the user confirms.

- Check actual geometric face directions and neighboring row widths first. Judge thresholds from anatomy, local scale and surrounding curvature, not one previous avatar's numbers. Smooth corner normals cannot fix folded surfaces.
- Snapshot shading before topology work with `snapshot_shading()`. On temporary Basis copies only, select the outward body and head surfaces to retain for a continuous normal donor; use `donor_keep_faces` to exclude internal overhangs from that donor. Keep those overlap faces on both final meshes. Join copies, weld only joining pairs, Select More 2–3 times, run Smooth Normals three times on the same selection at Blender's default factor `0.5` each time, then masked Face Corner Custom Normals transfer. `bake_seam_normals()` limits target changes to this local region and preserves distant shading/normal data. Whole-body Smooth Shading is outside this operation.
- `bake_seam_normals()` handles this donor workflow with preconditions and cleanup. Bake corner normals without applying armatures or destroying shape keys. Remove the donor; it must not become a third final avatar mesh.

Present the finished candidates in Blender with matching neutral-material lighting, plus wireframe/loop inspection and pose controls. Keep a pre-normal checkpoint if comparison is useful, but normal before/after views are supplementary; do not force a second approval cycle. Check front/side/back/oblique views and another light direction yourself before presenting.

## 6. Candidate validation, feedback and final delivery

Run `audit_seam()` on every candidate offered as viable. Record a pass/fail decision against the inspected model's tolerances for each required numerical check; merely writing measurements to JSON is not a pass. Resolve failed preservation or deformation checks before presenting the candidate as complete. Its structural checks and measurements are not a complete quality verdict. Require the following evidence before requesting final confirmation:

- The requested separate meshes and single common armature; no unwanted accessory or helper remains. Apply the final naming contract below and verify it again after reopening.
- Full actual joining-loop correspondence and symmetry; near-zero world gaps at rest and in tested deformations. Numerical tolerance comes from local mesh scale.
- Intentional local triangles/quads, with no hidden pentagons, degeneracy, crushed strips, foldovers or unintended intersections. Review BVH contact candidates, including shared-border contacts; a candidate count is not a complete collision proof.
- Neutral shared material without texture, front/side/back/underside/oblique views and multiple light directions. Inspect shaded surfaces and wireframe. Distinguish preexisting facial overlays and open scalps from neck defects.
- Preserved UV/material/weight/shape-key contracts, proper interpolation of additions, and all retained vertices bound. Compare unaffected face smoothing and corner normals to the pre-edit snapshot using explicit face/corner ID maps (`compare_shading`); testing only the seam or only the last operation is insufficient. Require rest-bone orientation checks and source-relative deformation checks, not just a count of poses. Report vertex/triangle count changes.
- Save review checkpoints under the task workspace and test reloading them without replacing the user's live work. Ensure the user can inspect and compare the real Blender samples, with overlays/bones/vertices available when needed. Reference loops/helpers are clearly labeled and optional, not hidden missing geometry.

### Final naming contract

- The final face/head mesh object must be named exactly `Body` (case-sensitive), without a prefix or numeric suffix.
- The recipient body mesh object must retain its original source name exactly (for example `Body_base`). Reserve these two names before resolving other objects; never rename either to make room for an accessory or a review copy. If a source body itself uses `Body`, report that exceptional conflict instead of silently choosing a different name.
- All other retained mesh objects retain their original source names. Resolve genuine collisions among final retained objects with the smallest deterministic numeric suffix, keeping one unsuffixed original name. Do not add avatar-name prefixes for readability.
- Preserve original mesh datablock names as well, resolving only actual datablock-name collisions. The exact `Body` requirement above applies to the face object, independently of its mesh datablock's source name.
- Import prefixes, A/B labels and Blender-generated suffixes on review copies are temporary. Assemble the final candidate in a separate file so other candidates and source references do not occupy final names. Preserve those review/source scenes in their checkpoints.
- Record an expected-name map by source identity, including reasons for any accessory suffix. Before saving and after reopening, assert that the face object is `Body`, the body object has its original name, and every other retained mesh matches this map. Update name-based metadata and references after restoring names. The single armature remains `Armature`.

Ask which completed candidate/version to finalize, or what should change. Wait for the user's explicit confirmation. Feedback requiring changes creates a new pending version; choosing a starting candidate while requesting edits is not final approval. After confirmation, assemble only the chosen candidate's deliverable objects, remove review references/layout offsets/helpers, restore intended materials/pose, save the output `.blend`, and reopen it for checks. Export FBX only if requested and reimport-check it. Do not carry review-only geometry into final delivery.

Report output, checks actually performed and remaining differences. Failed gates return to their phase and invalidate downstream evidence. Unsupported topology/anatomy must be reported specifically; a partial numerical match is not a completed natural transplant.
