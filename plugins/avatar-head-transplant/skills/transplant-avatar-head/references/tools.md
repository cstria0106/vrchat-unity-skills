# Tool contract

Helpers run inside Blender's Python with `bpy`, `bmesh`, `mathutils` and bundled NumPy. Discover current MCP schemas: some tools print, others need `result = {...}`. Verify the connected file. Isolated tests use the actual Blender executable with `--background`; do not assume `blender` is on PATH or replace a live scene to test.

```python
import importlib.util
spec = importlib.util.spec_from_file_location('avatar_tools', '/absolute/skill/path/scripts/avatar_tools.py')
av = importlib.util.module_from_spec(spec)
spec.loader.exec_module(av)
result = av.inspect_scene()
```

Object names are discovered at runtime. Public fitting/movement coordinates are world-space; vertex IDs are mesh-local indices. Edits require object mode and independent mesh data. Helpers do not import FBX, choose anatomy or finalize/export an avatar. The checkpoint helper writes a separate review .blend; the discard helper removes only marked candidates. Diagnostic exporters write JSON. Checkpoint before edits. Never run the fixture suite in a live scene.

## Native Blender review versions

- `create_review_scene(label, source_scene=None)` — branch a new uniquely named scene using Blender FULL_COPY. Returns source-to-candidate object names, pending status and `external_rig_dependencies`. Mesh, armature, shape-key data and animation actions are independent; internal object and Key driver references are remapped. It leaves the candidate active, without saving or finalizing. Resolve reported external dependencies and inspect custom node/rig setups before claiming independence. Materials/images may be shared: assign a new neutral review material instead of editing shared source materials.
- `save_review_checkpoint(filepath, scene_name=None)` — writes the scene and dependencies to a new absolute `.blend` path using Blender library writing. Rejects existing paths, preserves the active file path, and never implies final confirmation. Use task-local versioned files, including an immutable baseline. Append the saved scene with `bpy.data.libraries.load` and explicitly activate it to restore, then branch a new version. These are library checkpoints; create a regular `save_as_mainfile` review file for the user and reopen-test its active scene.
- `discard_review_scene(scene_name)` — removes only a scene marked as a review candidate and its otherwise-unused objects/mesh data. Switches away before deletion. Baseline scenes and disk checkpoints remain. No global orphan purge or final export.

Follow [the review protocol](review.md): finish geometry, rigging and normals on actual independent Blender candidates before review; feedback produces a new completed version. Only the user's explicit final confirmation authorizes applying that version to the final deliverable and performing requested exports. Temporary review checkpoint saves are allowed earlier.

- `create_review_comparison(label, scene_names, spacing)` — makes independent native copies of two or more candidate scenes, lays them out along world X, labels them and activates the comparison. `spacing` is world units chosen from actual avatar bounds. Canonical candidates stay at their original coordinates; use those for final delivery. External rig references must be resolved first. Configure neutral shading, inspection layers, framing and visible pose controls afterward.

## Read-only

- `inspect_scene()` — current file/mode, transforms, armature/key counts, weighted bones and unbound vertices.
- `boundary_loops(name, mode='OPEN', ...)` — `OPEN` lists actual holes. `EDGES`, with explicit `edge_indices`, orders selected existing edges, including internal loops. `SECTION`, with world `plane_origin` and `plane_normal`, bisects a temporary BMesh to show middle-of-surface cut candidates; optional `face_indices` limits the inspected region and `tolerance` controls numerical distance. All modes return `kind`, `closed`, `branched`, `requires_cut` and coordinates. New section points have `vertices: null` entries; they are not existing mesh vertices. No mode automatically identifies a neck or edits geometry. Midpoint/audit tools accept closed actual edge cycles, interior or open. `requires_cut` means section geometry needs new edges, not that existing interior loops should be opened.
- `fit_landmarks(source, target, weights=None)` — corresponding arrays of at least three noncollinear 3D points; positive uniform similarity matrix and residuals. For real work use both eyes, chin and occiput, then preview.
- `midpoint_targets(body, body_loop, head, head_loop)` — validates full ordered joining edge cycles and returns world targets. Does not choose pairs or edit.
- `symmetry_report(name, vertex_ids, plane_origin, plane_normal, tolerance)` — mirror distances and candidate partners in the specified world plane. Checks a bijective correspondence; does not automatically move vertices or decide anatomy.
- `audit_seam(body, body_loop, head, head_loop, rings=4, tolerance=None)` — correspondence, Basis/evaluated gap, local n-gons/degeneracy, geometric seam and adjacent angles, row-edge lengths, custom normal differences, binding, and BVH contacts. Default numerical tolerance is a small fraction of median boundary edge length. Structural validity is not artistic acceptance; views and chosen quality criteria remain required.
- `pose_probe(body, body_loop, head, head_loop, armature, cases, tolerance=None)` — cases contain `name`, optional `rotations={bone: [local XYZ radians]}` and `keys={mesh: {key: value}}`. Measures seam gaps and movement only (not anatomical deformation correctness), then restores matrices, modes and keys even on failure. Rejects active actions/NLA/driven pose channels. Existing shape-key drivers are evaluated; do not directly set driven keys.

- `audit_bone_fit(source, target, bone_map, transform=None)` — compares source-to-target world rest heads, tails and all three bone axes; `transform` is the donor mesh world fit.
- `compare_deformation(source, target, vertex_map, transform=None)` — compares evaluated world vertex positions in already configured corresponding poses. Uses each object's owning scene and restores the active scene. Supply influenced vertices, original-to-result IDs and the same fit transform; caller configures/restores rig/key states and chooses tolerance.
- `snapshot_shading(name)` / `compare_shading(name, snapshot, corner_map, face_map)` — save pre-edit local corner normals and face smooth flags; compare explicitly mapped unaffected corners/faces after all operations. Compare in the same local orientation (or transform snapshot normals into result space first). Return measured normal errors and changed shading flags, not blanket success.

## Explicit edits

- `apply_vertex_targets(name, targets)` — `{vertex_id: [world_x,world_y,world_z]}`; moves every key by the same local delta. Execute approved midpoint coordinates on both sides, then explicit reviewed transition edits. Not automatic smoothing.
- `apply_topology_plan(name, splits, connections)` — `splits=[{'a':0,'b':1,'tag':'s','factor':0.5}]`, `connections=[['s',2]]`. Original IDs are integers; new vertices use unique tags. Connections must identify one containing face. Builds an isolated candidate and rejects new/touched n-gons or degeneracy before committing. Returns tag IDs and old-ID mapping, preserving material/group layouts. Inspect the resulting flow and triangulation.
- `open_neck_loop(name, loop, remove_seed_face, dry_run=True)` — optional trimming utility, not the default interior-junction procedure; inspect a closed separating **interior** edge loop and the face-connected side reached from the supplied face without crossing it. Returns removal IDs and the predicted surviving vertex map. `dry_run=False` exposes the loop by removing that side and only its newly loose geometry. Preserves independent eyes/teeth/overlays, surviving UV/weights/keys and the Key datablock identity. Rejects nonmanifold/nonseparating loops or a seed in another component. Apply returned ID mappings to all cached correspondence and metadata.
- `copy_head_bones(source, target, bone_map, parent_map, transform=None)` — explicit source-to-new bone names plus shared-parent mappings. Copies transformed head/tail/roll and basic inheritance/deform properties, restores selection/mode and reports rest-fit errors. Meshes must receive the same world fit. Names cannot overwrite existing bones. Animated/driven donor rigs or selected constrained bones require a separately inspected mapping; the helper refuses to silently drop those behaviors. It does not prune rigs or bind meshes automatically.
- `bake_seam_normals(body, body_loop, head, head_loop, regions=None, expand=3, factor=0.5, donor_keep_faces=None, tolerance=None)` — supports open or interior joins. `expand` is 2 or 3. Optional transfer masks may not extend beyond that many edge steps; absent masks taper from the seam. Interior loops require `donor_keep_faces={mesh: [face_ids]}` selecting inspected outward surfaces on temporary copies so their joining loops become open before weld. Original overlap faces, UVs, keys and weights remain. Applies local face smoothing, weld/Select More/Smooth Normals/masked Data Transfer; explicitly restores distant corner normals and rolls back shading on failure. Never set all original faces smooth before calling it. Requires rest/Basis, positive uniform world scales and valid geometry/binding. Set a recorded scale-aware `tolerance` when imported float precision exceeds the default; the same value governs gap checks and temporary welding.


Tools fail preconditions instead of guessing diagonals, retrying, or silently adding topology. Rig semantics, artistic fit and topology planning remain explicit agent work.

## Optional alignment image diagnostics

`export_alignment_comparison(reference_head, donor_head, fit_matrix, output_json, source_landmarks, target_landmarks, labels=None, reference_vertices=None, donor_vertices=None, previous_matrix=None, view_origin=(0,0,0), view_axes=((1,0,0),(0,1,0),(0,0,1)))` runs inside Blender and does not edit the scene. It exports Basis geometry, not evaluated expressions/modifiers. `fit_matrix` maps the donor's **current world coordinates** to the candidate; applying it to an already fitted donor again would double-transform the preview. `previous_matrix` optionally displays an earlier fit instead of the untouched donor in the Before row.

Set `view_axes` as orthonormal world-space right/depth/up rows and `view_origin` on the recipient's symmetry plane: the profile intersects that frame's X=0 plane. Both eyes, chin and occiput need corresponding world landmarks and readable labels. Optional vertex subsets restrict plots to inspected skin components rather than dense expression overlays. The model chooses these inputs by inspection; no landmark is inferred from object names.

Render using standard Python, not Blender's Python:

```text
uv run --with numpy --with matplotlib python <skill>/scripts/render_alignment_comparison.py <absolute-preview.json> --output <absolute-Head_Alignment_Comparison.png>
```

The PNG has shared front/profile scales, reference/donor colors, Before/Candidate rows, landmark positions and per-axis/error measurements in millimeters. A `.metrics.json` sidecar records measurements. Inspect the actual generated image when using this diagnostic. This is a wire/cross-section placement review, not a substitute for shaded neck inspection after joining. Regenerate it when landmarks or the fit change. Include placement context in the native Blender candidates; no separate image approval is required.

## Optional neck proposal diagnostics

`export_seam_review(body, body_loop, head, head_loop, output_json, targets=None, rings=4, notes=None, view_origin=(0,0,0), view_axes=((1,0,0),(0,1,0),(0,0,1)))` exports a read-only proposal from paired draft boundaries. `targets={mesh_name: {vertex_id: world_coordinate}}` adds the reviewed surrounding adjustments. Seam targets must remain the exact pair midpoints; missing seam coordinates are populated with these midpoints. Prepare topology on independent copies first and retain provenance/ID maps. Defaults show a midpoint-only discussion draft, not a complete artistic solution.

```text
uv run --with numpy --with matplotlib python <skill>/scripts/render_seam_review.py <absolute-seam.json> --output <absolute-Seam_Review.png>
```

The six-panel PNG shows current Basis boundaries/pair movements and proposed surfaces in front, side and oblique views; poses are not evaluated. Colors and pair numbers support intuitive feedback. A stable `review_id` identifies the content; changing geometry/targets changes the ID. Exporting or rendering leaves `approval_status` pending. Neither is user approval. These diagnostics do not replace the completed native Blender sample review.

## Validation

```text
<blender executable> --background --factory-startup --python <skill>/scripts/test_avatar_tools.py
```

The Blender fixture suite tests open/interior/section distinctions, nonseparating cuts, dry-run trimming, surviving key/UV/weight remapping, preview export, unequal loops, twisted pairing, pentagons, transformed midpoints, pose restoration and normal transfer. Plane-coplanar face IDs are reported for ambiguous sections; choose another plane/region or explicitly review that geometry.

Run the standalone renderer tests with `uv run --with numpy --with matplotlib python <skill>/scripts/test_alignment_renderer.py`. No commercial avatar assets are bundled. Also audit and visually inspect real copies when available. Passing helper tests does not establish universal transplant success.
