"""Explicit Blender avatar tools; scene edits and preview exports are separate."""
import json
import hashlib
from pathlib import Path
import math
import statistics
import uuid
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def create_review_scene(label, source_scene=None):
    """Branch a native editable candidate, without saving or granting approval."""
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Use object mode before branching a review')
    source = bpy.data.scenes[source_scene] if source_scene else bpy.context.scene
    if label in bpy.data.scenes:
        raise ValueError('Use a new candidate version name')
    tag = '_avatar_copy_' + uuid.uuid4().hex
    original = list(source.objects)
    bpy.context.window.scene = source
    candidate = None
    try:
        for i, obj in enumerate(original):
            obj[tag] = i
        bpy.ops.scene.new(type='FULL_COPY')
        candidate = bpy.context.scene
        candidate.name = label
        candidate['_avatar_review_candidate'] = True
        candidate['_avatar_review_source'] = source.name
        candidate['_avatar_review_status'] = 'pending'
        copies = {obj[tag]: obj for obj in candidate.objects if tag in obj}
        mapping = {obj: copies[i] for i, obj in enumerate(original)}
        for obj, clone in list(mapping.items()):
            if obj.data:
                if obj.data == clone.data:
                    clone.data = obj.data.copy()
                mapping[obj.data] = clone.data
                if obj.type == 'MESH' and obj.data.shape_keys:
                    mapping[obj.data.shape_keys] = clone.data.shape_keys
        # FULL_COPY handles parents, modifiers and constraints; also remap Key drivers.
        actions = {}
        external = set()
        for obj in original:
            clone = mapping[obj]
            holders = [clone, *clone.modifiers, *clone.constraints]
            if clone.type == 'ARMATURE':
                holders += [c for bone in clone.pose.bones for c in bone.constraints]
            for holder in holders:
                for prop in holder.bl_rna.properties:
                    if prop.type != 'POINTER' or prop.is_readonly:
                        continue
                    value = getattr(holder, prop.identifier)
                    if isinstance(value, bpy.types.Object):
                        if value in mapping:
                            setattr(holder, prop.identifier, mapping[value])
                        elif value not in mapping.values():
                            external.add(value.name)
        for clone in set(mapping.values()):
            anim = clone.animation_data
            if not anim:
                continue
            holders = [anim] + [strip for track in anim.nla_tracks for strip in track.strips]
            for holder in holders:
                action = getattr(holder, 'action', None)
                if action:
                    if action not in actions:
                        actions[action] = action.copy()
                    holder.action = actions[action]
            for curve in anim.drivers:
                for variable in curve.driver.variables:
                    for target in variable.targets:
                        if target.id in mapping:
                            target.id = mapping[target.id]
                        elif isinstance(target.id, (bpy.types.Object, bpy.types.Key)) and target.id not in mapping.values():
                            external.add(target.id.name)
        return {'scene': candidate.name, 'source_scene': source.name,
                'objects': {obj.name: mapping[obj].name for obj in original},
                'external_rig_dependencies': sorted(external), 'approval_status': 'pending'}
    except Exception:
        if candidate:
            discard_review_scene(candidate.name)
            candidate = None
        bpy.context.window.scene = source
        raise
    finally:
        for obj in list(original) + (list(candidate.objects) if candidate and candidate.name in bpy.data.scenes else []):
            if tag in obj:
                del obj[tag]


def save_review_checkpoint(filepath, scene_name=None):
    """Write an immutable scene snapshot; never changes the active deliverable path."""
    path = Path(filepath)
    if not path.is_absolute() or path.suffix.lower() != '.blend':
        raise ValueError('Checkpoint requires an absolute .blend path')
    if path.exists():
        raise ValueError('Checkpoint already exists; use a new version')
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Use object mode before saving a checkpoint')
    scene = bpy.data.scenes[scene_name] if scene_name else bpy.context.scene
    bpy.data.libraries.write(str(path), {scene}, path_remap='ABSOLUTE', fake_user=True, compress=True)
    return {'checkpoint': str(path), 'scene': scene.name, 'finalized': False}


def create_review_comparison(label, scene_names, spacing):
    """Build independently editable side-by-side copies, preserving candidate coordinates."""
    if bpy.context.mode != 'OBJECT' or label in bpy.data.scenes or len(scene_names)<2 or spacing<=0:
        raise ValueError('Use object mode, a new label, at least two candidates and positive world spacing')
    sources=[bpy.data.scenes[n] for n in scene_names]
    comparison=bpy.data.scenes.new(label)
    comparison['_avatar_review_candidate']=True
    comparison['_avatar_review_source']=sources[0].name
    comparison['_avatar_review_status']='comparison_only'
    records=[]
    try:
        for i,source in enumerate(sources):
            report=create_review_scene(label+'_'+str(i+1),source.name)
            copy=bpy.data.scenes[report['scene']]
            if report['external_rig_dependencies']:
                discard_review_scene(copy.name)
                raise ValueError('Resolve external rig dependencies before offsetting comparison copies')
            objects=list(copy.objects)
            for col in copy.collection.children:comparison.collection.children.link(col)
            for obj in copy.collection.objects:comparison.collection.objects.link(obj)
            offset=(i-(len(sources)-1)/2)*spacing
            for obj in objects:
                if obj.parent is None:obj.matrix_world=Matrix.Translation((offset,0,0))@obj.matrix_world
            text_data=bpy.data.curves.new(source.name+'_Label','FONT');text_data.body=source.name;text_data.size=spacing*.09
            text_obj=bpy.data.objects.new(source.name+'_Label',text_data);comparison.collection.objects.link(text_obj)
            text_obj.location=(offset,0,0);text_obj.rotation_euler=(math.pi/2,0,0)
            bpy.context.window.scene=comparison
            bpy.data.scenes.remove(copy)
            records.append({'source_scene':source.name,'display_offset_x':offset,'objects':report['objects']})
        comparison['_avatar_review_layout']=json.dumps(records)
        bpy.context.window.scene=comparison
        return {'scene':comparison.name,'candidates':records,'final_export_allowed':False}
    except Exception:
        discard_review_scene(comparison.name)
        raise


def discard_review_scene(scene_name):
    """Remove only a marked candidate, leaving its source and disk checkpoints intact."""
    scene = bpy.data.scenes[scene_name]
    if not scene.get('_avatar_review_candidate'):
        raise ValueError('Only marked review candidates may be discarded')
    alternatives = [s for s in bpy.data.scenes if s != scene]
    if not alternatives:
        raise ValueError('Keep a baseline scene before discarding a candidate')
    source = bpy.data.scenes.get(scene.get('_avatar_review_source', '')) or alternatives[0]
    if source == scene:
        source = alternatives[0]
    objects = list(scene.objects)
    for window in bpy.context.window_manager.windows:
        if window.scene == scene:
            window.scene = source
    bpy.data.scenes.remove(scene)
    for obj in objects:
        if not obj.users_scene:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                bpy.data.batch_remove(ids=(data,))
    return {'discarded': scene_name, 'active_scene': bpy.context.scene.name}


def _mesh(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != 'MESH':
        raise ValueError(f'Mesh object not found: {name}')
    return obj


def copy_head_bones(source, target, bone_map, parent_map, transform=None):
    """Copy explicitly retained donor bones using the same world fit as donor meshes.

    bone_map contains newly created bones; parent_map maps shared existing parents.
    Complex pose constraints/drivers require an explicit mapping before this operation.
    """
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Use object mode before copying bones')
    src, dst = bpy.data.objects[source], bpy.data.objects[target]
    if src.type != 'ARMATURE' or dst.type != 'ARMATURE' or src == dst:
        raise ValueError('Use two distinct armatures')
    fit = Matrix(transform) if transform is not None else Matrix.Identity(4)
    M = dst.matrix_world.inverted() @ fit @ src.matrix_world
    scale = M.to_scale()
    if M.determinant() <= 0 or max(scale)-min(scale)>max(scale)*1e-5:
        raise ValueError('Bone copying requires a positive uniform transform')
    if len(set(bone_map.values())) != len(bone_map) or any(n in dst.data.bones for n in bone_map.values()):
        raise ValueError('New bone names must be unique and unused')
    if src.animation_data and (src.animation_data.drivers or src.animation_data.action or src.animation_data.nla_tracks):
        raise ValueError('Map donor animation/drivers explicitly before copying bones')
    specs = {}
    mapping = dict(parent_map, **bone_map)
    for name,new in bone_map.items():
        bone = src.data.bones[name]
        if src.pose.bones[name].constraints:
            raise ValueError('Map donor bone constraints explicitly before copying bones')
        parent = mapping.get(bone.parent.name) if bone.parent else None
        if bone.parent and (parent is None or (parent not in bone_map.values() and parent not in dst.data.bones)):
            raise ValueError(f'Missing retained parent mapping: {name}')
        specs[new] = {'head': M@bone.head_local, 'tail': M@bone.tail_local,
                      'z': (M.to_3x3()@bone.matrix_local.to_3x3().col[2]).normalized(),
                      'parent': parent, 'connected': bone.use_connect,
                      'properties': {key:getattr(bone,key) for key in ('use_deform','inherit_scale','use_inherit_rotation','use_local_location')}}
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    hidden = dst.hide_get()
    created = []
    try:
        bpy.ops.object.select_all(action='DESELECT')
        dst.hide_set(False); dst.select_set(True)
        bpy.context.view_layer.objects.active = dst
        bpy.ops.object.mode_set(mode='EDIT')
        for name,spec in specs.items():
            bone = dst.data.edit_bones.new(name); created.append(name)
            bone.head = spec['head']; bone.tail = spec['tail']; bone.align_roll(spec['z'])
            for key,value in spec['properties'].items():
                setattr(bone,key,value)
        for name,spec in specs.items():
            bone = dst.data.edit_bones[name]
            bone.parent = dst.data.edit_bones.get(spec['parent']) if spec['parent'] else None
            if spec['connected'] and bone.parent and (bone.head-bone.parent.tail).length<1e-7:
                bone.use_connect = True
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()
        report = audit_bone_fit(source,target,bone_map,transform)
        return {'created': created, 'fit':report, 'mesh_fit_must_match':True}
    except Exception:
        if bpy.context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        for name in created:
            bone = dst.data.edit_bones.get(name)
            if bone: dst.data.edit_bones.remove(bone)
        raise
    finally:
        if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        dst.hide_set(hidden)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected: obj.select_set(True)
        bpy.context.view_layer.objects.active = active


def audit_bone_fit(source, target, bone_map, transform=None):
    src,dst = bpy.data.objects[source],bpy.data.objects[target]
    fit = Matrix(transform) if transform is not None else Matrix.Identity(4)
    M = fit @ src.matrix_world
    rows = []
    for old,new in bone_map.items():
        a,b = src.data.bones[old],dst.data.bones[new]
        expected = M.to_3x3()@a.matrix_local.to_3x3()
        actual = dst.matrix_world.to_3x3()@b.matrix_local.to_3x3()
        rows.append({'source':old,'target':new,
                     'head_error_world':(M@a.head_local-dst.matrix_world@b.head_local).length,
                     'tail_error_world':(M@a.tail_local-dst.matrix_world@b.tail_local).length,
                     'axis_errors_degrees':[math.degrees(expected.col[i].angle(actual.col[i])) for i in range(3)]})
    return rows


def compare_deformation(source, target, vertex_map, transform=None):
    """Compare evaluated vertices in already configured matching source/target poses."""
    src,dst = _mesh(source),_mesh(target)
    fit = Matrix(transform) if transform is not None else Matrix.Identity(4)
    scene = bpy.context.scene
    try:
        bpy.context.window.scene = src.users_scene[0]; bpy.context.view_layer.update()
        a = _evaluated(src)
        bpy.context.window.scene = dst.users_scene[0]; bpy.context.view_layer.update()
        b = _evaluated(dst)
        errors = [(fit@a[int(i)]-b[int(j)]).length for i,j in vertex_map.items()]
        if not errors: raise ValueError('Select actual influenced vertices to compare')
        return {'vertices':len(errors),'max_error_world':max(errors),'mean_error_world':statistics.mean(errors)}
    finally:
        bpy.context.window.scene = scene; bpy.context.view_layer.update()


def snapshot_shading(name):
    obj = _mesh(name)
    return {'normals':[list(n.vector) for n in obj.data.corner_normals],
            'smooth':[p.use_smooth for p in obj.data.polygons]}


def compare_shading(name, snapshot, corner_map, face_map):
    """Compare explicitly mapped unaffected corners/faces to a pre-edit snapshot."""
    obj = _mesh(name)
    errors = [math.degrees(Vector(snapshot['normals'][int(a)]).angle(obj.data.corner_normals[int(b)].vector)) for a,b in corner_map.items()]
    if not errors or not face_map: raise ValueError('Supply unaffected corner and face correspondence')
    return {'corners':len(errors), 'max_normal_angle_degrees':max(errors),
            'changed_smooth_faces':[int(b) for a,b in face_map.items() if snapshot['smooth'][int(a)] != obj.data.polygons[int(b)].use_smooth]}


def _editable(obj):
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Use object mode; flush edit data explicitly first')
    if obj.data.users != 1:
        raise ValueError('Mesh has multiple users; make an intentional independent copy first')
    keys = obj.data.shape_keys
    if keys and any(abs(k.value) > 1e-8 for k in keys.key_blocks[1:]):
        raise ValueError('Reset expressions to Basis before editing')


def _bm(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    return bm


def _key_names(mesh):
    return [k.name for k in mesh.shape_keys.key_blocks] if mesh.shape_keys else []


def _weighted(obj):
    groups = {g.index: g.name for g in obj.vertex_groups}
    used = set()
    unbound = []
    rigs = [m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object]
    bones = set().union(*(set(r.data.bones.keys()) for r in rigs)) if rigs else set()
    for v in obj.data.vertices:
        names = {groups[g.group] for g in v.groups if g.weight > 0 and g.group in groups}
        used.update(names)
        if not names.intersection(bones):
            unbound.append(v.index)
    return {'weighted_groups': sorted(used), 'groups_without_bones': sorted(used - bones),
            'unbound_count': len(unbound), 'unbound_sample': unbound[:20]}


def inspect_scene():
    objects = []
    for obj in bpy.context.scene.objects:
        row = {'name': obj.name, 'type': obj.type, 'parent': obj.parent.name if obj.parent else None,
               'world_matrix': [list(r) for r in obj.matrix_world]}
        if obj.type == 'MESH':
            obj.data.calc_loop_triangles()
            row.update(vertices=len(obj.data.vertices), triangles=len(obj.data.loop_triangles),
                       shape_keys=len(_key_names(obj.data)), uv_layers=list(obj.data.uv_layers.keys()),
                       armatures=[m.object.name if m.object else None for m in obj.modifiers if m.type == 'ARMATURE'],
                       **_weighted(obj))
        elif obj.type == 'ARMATURE':
            row['bones'] = [{'name': b.name, 'parent': b.parent.name if b.parent else None,
                             'head_world': list(obj.matrix_world @ b.head_local),
                             'tail_world': list(obj.matrix_world @ b.tail_local)} for b in obj.data.bones]
        objects.append(row)
    return {'file': bpy.data.filepath, 'mode': bpy.context.mode, 'objects': objects}


def _graph_components(adj):
    unseen, rows = set(adj), []
    while unseen:
        start = min(unseen)
        todo, component = [start], set()
        while todo:
            i = todo.pop()
            if i in component:
                continue
            component.add(i)
            todo.extend(adj[i] - component)
        unseen -= component
        closed = all(len(adj[i]) == 2 for i in component)
        ordered = sorted(component)
        if closed:
            ordered = [start]
            previous, current = start, min(adj[start])
            while current != start:
                ordered.append(current)
                following = next(i for i in adj[current] if i != previous)
                previous, current = current, following
        rows.append((ordered, closed, any(len(adj[i]) > 2 for i in component)))
    return rows


def boundary_loops(name, mode='OPEN', *, edge_indices=None, plane_origin=None,
                   plane_normal=None, face_indices=None, tolerance=None):
    """Inspect holes, explicit interior edge cycles, or proposed surface sections.

    SECTION bisects only a temporary BMesh. None vertex IDs mean that real cuts
    must be constructed; a section is never passed off as an existing boundary.
    """
    obj = _mesh(name)
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Flush edit data and use object mode before inspecting mesh topology')
    bm = _bm(obj)
    try:
        bm.edges.ensure_lookup_table()
        original_vertices = {v: v.index for v in bm.verts}
        original_pairs = {frozenset(v.index for v in e.verts): e.index for e in bm.edges}
        mode = mode.upper()
        coplanar = []
        if mode == 'OPEN':
            chosen = [e for e in bm.edges if e.is_boundary]
        elif mode == 'EDGES':
            if not edge_indices or any(not isinstance(i, int) or i < 0 or i >= len(bm.edges) for i in edge_indices):
                raise ValueError('EDGES mode needs inspected existing edge indices')
            chosen = [bm.edges[i] for i in sorted(set(edge_indices))]
        elif mode == 'SECTION':
            if plane_origin is None or plane_normal is None:
                raise ValueError('SECTION mode needs a world-space plane origin and normal')
            origin, normal = Vector(plane_origin), Vector(plane_normal)
            if normal.length == 0 or not all(math.isfinite(x) for x in [*origin, *normal]):
                raise ValueError('Invalid section plane')
            normal.normalize()
            for v in bm.verts:
                v.co = obj.matrix_world @ v.co
            if face_indices is None:
                faces = list(bm.faces)
            else:
                if any(not isinstance(i, int) or i < 0 or i >= len(bm.faces) for i in face_indices):
                    raise ValueError('Invalid section face indices')
                faces = [bm.faces[i] for i in sorted(set(face_indices))]
            edges = {e for f in faces for e in f.edges}
            vertices = {v for f in faces for v in f.verts}
            lengths = [e.calc_length() for e in edges if e.calc_length() > 0]
            if not lengths:
                raise ValueError('Section region has no usable geometry')
            epsilon = tolerance if tolerance is not None else statistics.median(lengths) * 1e-6
            if not math.isfinite(epsilon) or epsilon <= 0:
                raise ValueError('Section tolerance must be finite and positive')
            coplanar = [f.index for f in faces if all(abs((v.co-origin).dot(normal)) <= epsilon for v in f.verts)]
            cut = bmesh.ops.bisect_plane(bm, geom=list(vertices)+list(edges)+faces,
                                        plane_co=origin, plane_no=normal, dist=epsilon,
                                        clear_inner=False, clear_outer=False)
            bm.verts.index_update()
            chosen = [e for e in cut['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
        else:
            raise ValueError('Choose OPEN, EDGES or SECTION mode')
        adj = {}
        for e in chosen:
            a, b = [v.index for v in e.verts]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        bm.verts.ensure_lookup_table()
        rows = []
        for ordered, closed, branched in _graph_components(adj):
            ids = [original_vertices.get(bm.verts[i]) for i in ordered]
            subset = [e for e in chosen if all(v.index in ordered for v in e.verts)]
            open_boundary = mode != 'SECTION' and all(e.is_boundary for e in subset)
            kind = 'section_candidate' if mode == 'SECTION' else ('open_boundary' if open_boundary else 'internal_edge_candidate')
            pairs = [frozenset((a,b)) for a,b in zip(ids, ids[1:]+ids[:1])] if closed and None not in ids else []
            rows.append({'kind': kind, 'vertices': ids, 'closed': closed, 'branched': branched,
                         'existing_edge_indices': [original_pairs.get(p) for p in pairs],
                         'requires_cut': mode == 'SECTION' and (not pairs or any(original_pairs.get(p) is None for p in pairs)),
                         'coplanar_face_indices': coplanar,
                         'world_coordinates': [list(bm.verts[i].co if mode == 'SECTION' else obj.matrix_world @ bm.verts[i].co) for i in ordered]})
        return rows
    finally:
        bm.free()


def _cycle(name, ids):
    ids = list(ids)
    if len(ids) < 3 or len(set(ids)) != len(ids):
        raise ValueError('A boundary cycle needs unique vertex IDs')
    bm = _bm(_mesh(name))
    try:
        for a, b in zip(ids, ids[1:] + ids[:1]):
            if min(a,b) < 0 or max(a,b) >= len(bm.verts):
                raise ValueError('Loop vertex index out of range')
            edge = bm.edges.get((bm.verts[a], bm.verts[b]))
            if edge is None:
                raise ValueError(f'{name}: order must cover a complete cycle of actual edges')
            if len(edge.link_faces) not in (1,2):
                raise ValueError('Joining loop requires manifold surface edges')
    finally:
        bm.free()
    return ids


def _pair(body, body_loop, head, head_loop):
    if body == head:
        raise ValueError('Head and body must be separate objects')
    br, hr = _cycle(body, body_loop), _cycle(head, head_loop)
    if len(br) != len(hr):
        raise ValueError('Loop counts differ; construct topology before pairing')
    return _mesh(body), br, _mesh(head), hr


def _epsilon(obj, ring, tolerance):
    if tolerance is not None:
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError('Tolerance must be finite and positive')
        return tolerance
    p = [obj.matrix_world @ obj.data.vertices[i].co for i in ring]
    scale = statistics.median((a - b).length for a, b in zip(p, p[1:] + p[:1]))
    if scale <= 0:
        raise ValueError('Degenerate boundary scale')
    return scale * 1e-5


def fit_landmarks(source, target, weights=None):
    x, y = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 3 or len(x) < 3:
        raise ValueError('Need matching Nx3 arrays of at least three points')
    w = np.ones(len(x)) if weights is None else np.asarray(weights, dtype=float)
    if w.shape != (len(x),) or np.any(w <= 0) or not all(np.isfinite(a).all() for a in [x, y, w]):
        raise ValueError('Finite landmarks and positive per-landmark weights required')
    w /= w.sum()
    cx, cy = w @ x, w @ y
    xx, yy = x - cx, y - cy
    if np.linalg.matrix_rank(xx) < 2 or np.linalg.matrix_rank(yy) < 2:
        raise ValueError('Collinear landmarks do not determine a head orientation')
    u, singular, vt = np.linalg.svd((yy * w[:, None]).T @ xx)
    sign = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        sign[-1] = -1
    rotation = u @ np.diag(sign) @ vt
    scale = float((singular * sign).sum() / (w[:, None] * xx * xx).sum())
    if scale <= 0:
        raise ValueError('No positive proper similarity fit')
    translation = cy - scale * rotation @ cx
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = scale * rotation, translation
    residuals = np.linalg.norm(x @ (scale * rotation).T + translation - y, axis=1)
    return {'matrix': matrix.tolist(), 'uniform_scale': scale,
            'residuals_world': residuals.tolist(), 'weighted_rms_world': float(np.sqrt(w @ residuals**2))}


def midpoint_targets(body, body_loop, head, head_loop):
    b, br, h, hr = _pair(body, body_loop, head, head_loop)
    points = [(b.matrix_world @ b.data.vertices[i].co + h.matrix_world @ h.data.vertices[j].co) / 2
              for i, j in zip(br, hr)]
    return {body: {i: list(p) for i, p in zip(br, points)}, head: {i: list(p) for i, p in zip(hr, points)}}


def symmetry_report(name, vertex_ids, plane_origin, plane_normal, tolerance):
    """Measure mirrored counterparts without choosing or moving topology."""
    obj = _mesh(name)
    ids = list(vertex_ids)
    normal, origin = Vector(plane_normal), Vector(plane_origin)
    if not ids or normal.length == 0 or not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Vertices, a nonzero plane normal and positive tolerance required')
    normal.normalize()
    coords = {i: obj.matrix_world @ obj.data.vertices[i].co for i in ids}
    kd = KDTree(len(ids))
    for i, co in coords.items():
        kd.insert(co, i)
    kd.balance()
    partners, errors = {}, {}
    for i, co in coords.items():
        mirrored = co - 2 * normal * (co-origin).dot(normal)
        _, j, distance = kd.find(mirrored)
        partners[i], errors[i] = j, distance
    bijective = all(partners.get(j) == i for i, j in partners.items())
    return {'max_error_world': max(errors.values()), 'bijective': bijective,
            'within_tolerance': bijective and max(errors.values()) <= tolerance,
            'candidate_partners': partners, 'outside_tolerance': [i for i, d in errors.items() if d > tolerance]}


def apply_vertex_targets(name, targets):
    obj = _mesh(name)
    _editable(obj)
    if not math.isfinite(obj.matrix_world.determinant()) or abs(obj.matrix_world.determinant()) < 1e-15:
        raise ValueError('Singular object transform')
    inv = obj.matrix_world.inverted()
    moves = {}
    for index, value in targets.items():
        i = int(index)
        if i < 0 or i >= len(obj.data.vertices) or len(value) != 3 or not all(math.isfinite(x) for x in value):
            raise ValueError('Invalid vertex target')
        moves[i] = inv @ Vector(value) - obj.data.vertices[i].co
    for key in obj.data.shape_keys.key_blocks if obj.data.shape_keys else []:
        for i, delta in moves.items():
            key.data[i].co += delta
    for i, delta in moves.items():
        obj.data.vertices[i].co += delta
    obj.data.update()
    return {'moved_vertices': len(moves), 'max_local_displacement': max((d.length for d in moves.values()), default=0)}


def apply_topology_plan(name, splits, connections):
    obj = _mesh(name)
    _editable(obj)
    original = obj.data
    candidate = original.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(candidate)
        bm.verts.ensure_lookup_table()
        old = list(bm.verts)
        allowed_ngons = {frozenset(f.verts) for f in bm.faces if len(f.verts) > 4}
        refs = {i: v for i, v in enumerate(old)}
        new = {}
        for operation in splits:
            a, b, tag = operation['a'], operation['b'], operation['tag']
            fraction = operation.get('factor', .5)
            if not isinstance(tag, str) or tag in refs or not 0 < fraction < 1:
                raise ValueError('Unique string tags and interior split fractions required')
            if a not in refs or b not in refs:
                raise ValueError('Unknown split endpoint')
            va, vb = refs[a], refs[b]
            edge = bm.edges.get((va, vb))
            if edge is None:
                raise ValueError('Requested split edge does not exist')
            shape_values = {layer: va[layer].lerp(vb[layer], fraction) for layer in bm.verts.layers.shape.values()}
            deform = bm.verts.layers.deform.active
            weights = {}
            if deform:
                for group in set(va[deform].keys()) | set(vb[deform].keys()):
                    weights[group] = va[deform].get(group, 0) * (1 - fraction) + vb[deform].get(group, 0) * fraction
            _, vertex = bmesh.utils.edge_split(edge, va, fraction)
            for layer, value in shape_values.items():
                vertex[layer] = value
            if deform:
                vertex[deform].clear()
                for group, weight in weights.items():
                    vertex[deform][group] = weight
            refs[tag] = new[tag] = vertex
        for a, b in connections:
            if a not in refs or b not in refs or a == b:
                raise ValueError('Invalid connection endpoints')
            va, vb = refs[a], refs[b]
            if bm.edges.get((va, vb)) is not None:
                raise ValueError('Connection already exists')
            faces = [f for f in va.link_faces if vb in f.verts]
            if len(faces) != 1:
                raise ValueError('A diagonal must identify exactly one containing face')
            bmesh.utils.face_split(faces[0], va, vb)
        bm.verts.index_update()
        bm.faces.index_update()
        if any(v.index != i for i, v in enumerate(old)):
            raise ValueError('Operation changed original vertex indices; explicit remapping required')
        bad = [f.index for f in bm.faces if len(f.verts) > 4 and frozenset(f.verts) not in allowed_ngons]
        if bad:
            raise ValueError(f'Split plan leaves new/touched n-gons: {bad}')
        if any(f.calc_area() == 0 for f in bm.faces):
            raise ValueError('Candidate contains zero-area faces')
        mapping = {tag: vertex.index for tag, vertex in new.items()}
        bm.to_mesh(candidate)
        candidate.update()
        if _key_names(candidate) != _key_names(original):
            raise ValueError('Shape-key contract changed')
        if list(candidate.uv_layers.keys()) != list(original.uv_layers.keys()):
            raise ValueError('UV layers changed')
        candidate.calc_loop_triangles()
        original.calc_loop_triangles()
        report = {'new_vertices': mapping, 'old_vertex_map': {i: i for i in range(len(old))},
                'added_vertices': len(candidate.vertices) - len(original.vertices),
                'added_triangles': len(candidate.loop_triangles) - len(original.loop_triangles)}
        # Commit validated geometry to the existing datablock so external drivers
        # targeting its Key ID continue controlling this object, not a stale copy.
        bm.to_mesh(original)
        original.update()
        return report
    finally:
        bm.free()
        if candidate.users == 0:
            bpy.data.meshes.remove(candidate)


def open_neck_loop(name, loop, remove_seed_face, dry_run=True):
    """Expose an explicitly chosen separating interior loop by removing one side.

    Only the face-connected component on the seed side is removed. Disconnected
    eyes/teeth/overlays survive. Returns remapping; old cached IDs must be updated.
    """
    obj = _mesh(name)
    _editable(obj)
    ids = list(loop)
    if len(ids) < 3 or len(set(ids)) != len(ids):
        raise ValueError('Need one ordered simple internal loop')
    candidate = obj.data.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(candidate)
        layer = bm.verts.layers.int.new('_avatar_original_vertex')
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        for v in bm.verts:
            v[layer] = v.index + 1
        if any(not isinstance(i, int) or i < 0 or i >= len(bm.verts) for i in ids):
            raise ValueError('Loop requires existing vertex IDs, not section-preview points')
        if not isinstance(remove_seed_face, int) or not 0 <= remove_seed_face < len(bm.faces):
            raise ValueError('Choose a face on the side to remove')
        edges = []
        for a,b in zip(ids, ids[1:]+ids[:1]):
            edge = bm.edges.get((bm.verts[a], bm.verts[b]))
            if edge is None or len(edge.link_faces) != 2:
                raise ValueError('Every selected loop edge must be interior manifold geometry')
            edges.append(edge)
        blocked = set(edges)
        removed, todo = set(), [bm.faces[remove_seed_face]]
        while todo:
            face = todo.pop()
            if face in removed:
                continue
            removed.add(face)
            todo.extend(other for e in face.edges if e not in blocked for other in e.link_faces if other not in removed)
        if any(sum(f in removed for f in e.link_faces) != 1 for e in edges):
            raise ValueError('Loop is not separating, or the seed belongs to a different component')
        old_count = len(bm.verts)
        removed_faces = sorted(f.index for f in removed)
        affected_edges = {e for f in removed for e in f.edges}
        affected_vertices = {v for f in removed for v in f.verts}
        bmesh.ops.delete(bm, geom=list(removed), context='FACES_ONLY')
        loose_edges = [e for e in affected_edges if e.is_valid and not e.link_faces]
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
        loose_vertices = [v for v in affected_vertices if v.is_valid and not v.link_edges]
        if loose_vertices:
            bmesh.ops.delete(bm, geom=loose_vertices, context='VERTS')
        bm.verts.index_update()
        mapping = {v[layer]-1: v.index for v in bm.verts}
        if any(i not in mapping for i in ids) or not all(e.is_valid and e.is_boundary for e in edges):
            raise ValueError('Cut did not expose exactly the intended loop')
        bm.verts.layers.int.remove(layer)
        bm.to_mesh(candidate)
        if _key_names(candidate) != _key_names(obj.data):
            raise ValueError('Cut changed the shape-key contract')
        if candidate.shape_keys and any(len(k.data) != len(mapping) for k in candidate.shape_keys.key_blocks):
            raise ValueError('Cut failed to remap all shape keys')
        if not dry_run:
            bm.to_mesh(obj.data)
            obj.data.update()
        return {'loop': [mapping[i] for i in ids], 'old_vertex_map': mapping,
                'removed_vertices': sorted(set(range(old_count))-set(mapping)),
                'removed_faces': removed_faces, 'committed': not dry_run,
                'cached_vertex_ids_require_remapping': True}
    finally:
        bm.free()
        if candidate.users == 0:
            bpy.data.meshes.remove(candidate)


def export_alignment_comparison(reference_head, donor_head, fit_matrix, output_json,
                                source_landmarks, target_landmarks, labels=None,
                                reference_vertices=None, donor_vertices=None,
                                previous_matrix=None, view_origin=(0,0,0),
                                view_axes=((1,0,0),(0,1,0),(0,0,1))):
    """Export immutable Basis geometry for front/profile before-after review.

    Matrix maps the donor's CURRENT world coordinates to candidate coordinates.
    Do not pass an already transformed donor with its original fit matrix again.
    """
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Flush edits and use object mode before exporting preview geometry')
    matrix = np.asarray(fit_matrix, dtype=float)
    previous = np.eye(4) if previous_matrix is None else np.asarray(previous_matrix, dtype=float)
    axes = np.asarray(view_axes, dtype=float)
    origin = np.asarray(view_origin, dtype=float)
    points, targets = np.asarray(source_landmarks, dtype=float), np.asarray(target_landmarks, dtype=float)
    for transform in [matrix, previous]:
        if transform.shape != (4,4) or not np.isfinite(transform).all() or not np.allclose(transform[3],[0,0,0,1]):
            raise ValueError('Preview needs finite affine world-space matrices')
        gram = transform[:3,:3].T @ transform[:3,:3]
        if np.linalg.det(transform[:3,:3]) <= 0 or not np.allclose(gram, np.eye(3)*np.trace(gram)/3, rtol=1e-5, atol=1e-10):
            raise ValueError('Preview candidates must use a proper uniform similarity transform')
    if axes.shape != (3,3) or not np.allclose(axes @ axes.T,np.eye(3),atol=1e-6) or origin.shape != (3,):
        raise ValueError('View frame needs orthonormal right/depth/up rows and a 3D origin')
    if points.shape != targets.shape or points.ndim != 2 or points.shape[1] != 3 or len(points)<3:
        raise ValueError('Need matching landmark arrays')
    if not all(np.isfinite(x).all() for x in [points,targets,axes,origin]):
        raise ValueError('Preview coordinates must be finite')
    if labels is None:
        labels = [f'Landmark {i+1}' for i in range(len(points))]
    if len(labels) != len(points):
        raise ValueError('One label per landmark required')
    def geometry(name, selected):
        obj = _mesh(name)
        ids = list(range(len(obj.data.vertices))) if selected is None else sorted(set(selected))
        if not ids or any(not isinstance(i,int) or not 0<=i<len(obj.data.vertices) for i in ids):
            raise ValueError('Invalid preview geometry subset')
        remap = {i:j for j,i in enumerate(ids)}
        # Explicit Basis rather than evaluated pose/expression/modifiers.
        basis = obj.data.shape_keys.key_blocks[0].data if obj.data.shape_keys else obj.data.vertices
        obj.data.calc_loop_triangles()
        return {'name':name, 'original_vertex_ids':ids,
                'vertices':[list(obj.matrix_world @ basis[i].co) for i in ids],
                'edges':[[remap[i] for i in e.vertices] for e in obj.data.edges if all(i in remap for i in e.vertices)],
                'triangles':[[remap[i] for i in t.vertices] for t in obj.data.loop_triangles if all(i in remap for i in t.vertices)]}
    data = {'schema':1, 'geometry_state':'Basis; no pose or modifier evaluation',
            'reference':geometry(reference_head,reference_vertices), 'donor':geometry(donor_head,donor_vertices),
            'fit_matrix':matrix.tolist(), 'previous_matrix':previous.tolist(),
            'source_landmarks':points.tolist(), 'target_landmarks':targets.tolist(), 'labels':list(labels),
            'view_origin':origin.tolist(), 'view_axes':axes.tolist(),
            'meters_per_world_unit':float(bpy.context.scene.unit_settings.scale_length)}
    path = Path(output_json)
    if not path.is_absolute() or path.suffix.lower() != '.json':
        raise ValueError('Specify an absolute .json diagnostic output path')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False),encoding='utf8')
    return {'preview_json':str(path),'scene_modified':False,'geometry_state':data['geometry_state']}


def export_seam_review(body, body_loop, head, head_loop, output_json, targets=None,
                       rings=4, notes=None, view_origin=(0,0,0),
                       view_axes=((1,0,0),(0,1,0),(0,0,1))):
    """Read-only geometry proposal: current patches, pairs, midpoints and targets.

    Use independent draft copies for planned cuts/topology before exporting.
    An export or review_id never grants approval to mutate the deliverable.
    """
    b, br, h, hr = _pair(body, body_loop, head, head_loop)
    if rings < 1:
        raise ValueError('Show surrounding rows, not just isolated boundary points')
    axes, origin = np.asarray(view_axes,float), np.asarray(view_origin,float)
    if axes.shape != (3,3) or origin.shape != (3,) or not np.allclose(axes@axes.T,np.eye(3),atol=1e-6):
        raise ValueError('Supply an orthonormal view frame and 3D origin')
    if not np.isfinite(axes).all() or not np.isfinite(origin).all():
        raise ValueError('View frame must be finite')
    proposal = midpoint_targets(body, br, head, hr)
    explicit = bool(targets) and any(bool(values) for values in targets.values())
    if explicit:
        if set(targets)-{body,head}:
            raise ValueError('Targets must refer to these two draft meshes')
        for name, values in targets.items():
            for i, p in values.items():
                if not 0 <= int(i) < len(_mesh(name).data.vertices) or len(p)!=3 or not all(math.isfinite(v) for v in p):
                    raise ValueError('Invalid proposed vertex target')
                proposal[name][int(i)] = list(p)
    epsilon = _epsilon(b,br,None)
    original_midpoints = midpoint_targets(body,br,head,hr)
    for i,j in zip(br,hr):
        if (Vector(proposal[body][i])-Vector(proposal[head][j])).length>epsilon:
            raise ValueError('Proposed seam partners must coincide')
        if (Vector(proposal[body][i])-Vector(original_midpoints[body][i])).length>epsilon:
            raise ValueError('Proposed common boundary must use the reviewed pair midpoints')
    patches={}
    for obj,ring in [(b,br),(h,hr)]:
        ids=sorted(set(_region(obj,ring,rings))|set(proposal[obj.name]))
        mapping={i:j for j,i in enumerate(ids)}
        current=[list(obj.matrix_world@obj.data.vertices[i].co) for i in ids]
        proposed=[proposal[obj.name].get(i,current[j]) for j,i in enumerate(ids)]
        patches[obj.name]={'vertex_ids':ids,'current':current,'proposed':proposed,
                          'edges':[[mapping[i] for i in e.vertices] for e in obj.data.edges if all(i in mapping for i in e.vertices)],
                          'faces':[[mapping[i] for i in p.vertices] for p in obj.data.polygons if all(i in mapping for i in p.vertices)]}
    pairs=[{'id':k+1,'body_vertex':i,'head_vertex':j,
            'body':list(b.matrix_world@b.data.vertices[i].co),
            'head':list(h.matrix_world@h.data.vertices[j].co),
            'target':proposal[body][i]} for k,(i,j) in enumerate(zip(br,hr))]
    data={'schema':1,'stage':'geometry','geometry_state':'Basis coordinates; pose not evaluated',
          'body':body,'head':head,'patches':patches,'pairs':pairs,
          'explicit_local_targets_supplied':explicit,'notes':list(notes or []),
          'view_origin':origin.tolist(),'view_axes':axes.tolist(),
          'meters_per_world_unit':float(bpy.context.scene.unit_settings.scale_length),
          'final_meshes_remain_separate':True,'approval_status':'pending'}
    data['review_id']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    path=Path(output_json)
    if not path.is_absolute() or path.suffix.lower()!='.json':
        raise ValueError('Specify an absolute diagnostic .json path')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
    return {'review_json':str(path),'review_id':data['review_id'],'approval_status':'pending',
            'scene_modified':False,'pair_count':len(pairs),'midpoint_only':not explicit}


def _region(obj, ring, depth):
    adj = [set() for _ in obj.data.vertices]
    for e in obj.data.edges:
        a, b = e.vertices
        adj[a].add(b)
        adj[b].add(a)
    distance = {i: 0 for i in ring}
    front = set(ring)
    for step in range(1, depth + 1):
        following = set().union(*(adj[i] for i in front)) - set(distance) if front else set()
        distance.update({i: step for i in following})
        front = following
    return distance


def _evaluated(obj):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    try:
        if len(mesh.vertices) != len(obj.data.vertices):
            raise ValueError('Topology-changing modifier invalidates evaluated vertex correspondence')
        return [ev.matrix_world @ v.co for v in mesh.vertices]
    finally:
        ev.to_mesh_clear()


def audit_seam(body, body_loop, head, head_loop, rings=4, tolerance=None):
    try:
        b, br, h, hr = _pair(body, body_loop, head, head_loop)
    except ValueError as error:
        return {'structural_errors': [str(error)], 'visual_review_required': True}
    if rings < 1:
        raise ValueError('Inspect at least one surrounding row')
    epsilon = _epsilon(b, br, tolerance)
    errors = []
    data, bms, tris, trees = {}, [], [], []
    try:
        for obj, ring in [(b, br), (h, hr)]:
            bm = _bm(obj)
            bms.append(bm)
            world = [obj.matrix_world @ v.co for v in bm.verts]
            for v, co in zip(bm.verts, world):
                v.co = co
            bm.normal_update()
            region = _region(obj, ring, rings)
            faces = [f for f in bm.faces if any(v.index in region for v in f.verts)]
            ngons = [f.index for f in faces if len(f.verts) > 4]
            degenerate = [f.index for f in faces if f.calc_area() < epsilon**2]
            if ngons:
                errors.append(f'{obj.name}: neck region contains n-gons {ngons}')
            if degenerate:
                errors.append(f'{obj.name}: degenerate local faces {degenerate}')
            row_lengths = {}
            for e in bm.edges:
                a, c = [v.index for v in e.verts]
                if a in region and c in region and region[a] != region[c]:
                    row = min(region[a], region[c])
                    row_lengths.setdefault(row, []).append(e.calc_length())
            local_angles = [math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal))
                            for e in bm.edges if len(e.link_faces) == 2 and all(v.index in region for v in e.verts)]
            data[obj.name] = {'local_ngons': ngons, 'degenerate_faces': degenerate,
                             'row_edge_lengths_world': {k: {'min': min(v), 'median': statistics.median(v), 'max': max(v)} for k, v in row_lengths.items()},
                             'max_local_adjacent_face_angle_degrees': max(local_angles, default=0), **_weighted(obj)}
            if data[obj.name]['unbound_count']:
                errors.append(f'{obj.name}: vertices have no positive influence from an assigned armature')
            obj.data.calc_loop_triangles()
            ts = [tuple(t.vertices) for t in obj.data.loop_triangles if all(i in region for i in t.vertices)]
            tris.append(ts)
            trees.append(BVHTree.FromPolygons(world, ts, all_triangles=True, epsilon=0))
        angles = []
        for k, (i, j) in enumerate(zip(br, hr)):
            be = bms[0].edges.get((bms[0].verts[i], bms[0].verts[br[(k+1) % len(br)]]))
            he = bms[1].edges.get((bms[1].verts[j], bms[1].verts[hr[(k+1) % len(hr)]]))
            angles.append(max(math.degrees(bf.normal.angle(hf.normal)) for bf in be.link_faces for hf in he.link_faces))
        basis_gap = max((b.matrix_world @ b.data.vertices[i].co - h.matrix_world @ h.data.vertices[j].co).length for i, j in zip(br, hr))
        bc, hc = _evaluated(b), _evaluated(h)
        evaluated_gap = max((bc[i] - hc[j]).length for i, j in zip(br, hr))
        if max(basis_gap, evaluated_gap) > epsilon:
            errors.append('Neck boundary positions differ')
        normals = []
        for obj, ring in [(b, br), (h, hr)]:
            nmat = obj.matrix_world.to_3x3().inverted().transposed()
            mapping = {i: [] for i in ring}
            for loop, normal in zip(obj.data.loops, obj.data.corner_normals):
                if loop.vertex_index in mapping:
                    mapping[loop.vertex_index].append((nmat @ normal.vector).normalized())
            normals.append(mapping)
        corner_angle = max(math.degrees(x.angle(y)) for i, j in zip(br, hr) for x in normals[0][i] for y in normals[1][j])
        assigned = [{m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object} for obj in [b, h]]
        if len(assigned[0]) != 1 or assigned[0] != assigned[1]:
            errors.append('Head and body must use the same single armature')
        correspondence = dict(zip(br, hr))
        contacts = trees[0].overlap(trees[1])
        nonborder = [(i, j) for i, j in contacts if not any(correspondence.get(v) in tris[1][j] for v in tris[0][i])]
        return {'structural_errors': errors, 'visual_review_required': True, 'tolerance_world': epsilon,
                'basis_gap_world': basis_gap, 'evaluated_gap_world': evaluated_gap,
                'seam_geometric_angles_degrees': angles, 'max_corner_normal_angle_degrees': corner_angle,
                'meshes': data, 'contact_candidates': {'total': len(contacts), 'nonborder': nonborder,
                    'shared_border_count': len(contacts)-len(nonborder), 'requires_geometric_review': True}}
    finally:
        for bm in bms:
            bm.free()


def _rig_rest(rig):
    anim = rig.animation_data
    if anim and (anim.action or len(anim.nla_tracks) or len(anim.drivers)):
        raise ValueError('Active rig animation/drivers need an explicit evaluation plan')
    if rig.data.pose_position != 'REST':
        for p in rig.pose.bones:
            if max(abs(p.matrix_basis[r][c] - (1 if r == c else 0)) for r in range(4) for c in range(4)) > 1e-5:
                raise ValueError('Reset the armature to rest before normal transfer')
            if p.constraints:
                raise ValueError('Constrained pose requires an explicit rest evaluation plan')


def pose_probe(body, body_loop, head, head_loop, armature, cases, tolerance=None):
    b, br, h, hr = _pair(body, body_loop, head, head_loop)
    rig = bpy.data.objects[armature]
    if rig.type != 'ARMATURE':
        raise ValueError('Not an armature')
    anim = rig.animation_data
    if anim and (anim.action or len(anim.nla_tracks) or len(anim.drivers)):
        raise ValueError('Pose channels are animated/driven; choose an explicit probe strategy')
    epsilon = _epsilon(b, br, tolerance)
    state = {p.name: (p.matrix_basis.copy(), p.rotation_mode) for p in rig.pose.bones}
    key_state = {o.name: [k.value for k in o.data.shape_keys.key_blocks] if o.data.shape_keys else [] for o in [b, h]}
    position = rig.data.pose_position
    rows = []
    try:
        rig.data.pose_position = 'POSE'
        for p in rig.pose.bones:
            p.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        base = [_evaluated(o) for o in [b, h]]
        for case in cases:
            for p in rig.pose.bones:
                p.matrix_basis = Matrix.Identity(4)
            for obj in [b, h]:
                if obj.data.shape_keys:
                    for k, value in zip(obj.data.shape_keys.key_blocks, key_state[obj.name]):
                        k.value = value
            for name, rotation in case.get('rotations', {}).items():
                p = rig.pose.bones[name]
                p.rotation_mode = 'XYZ'
                p.rotation_euler = rotation
            for name, values in case.get('keys', {}).items():
                if name not in key_state:
                    raise ValueError('Probe keys must belong to the head or body')
                keys = _mesh(name).data.shape_keys
                driven = {fc.data_path for fc in keys.animation_data.drivers} if keys.animation_data else set()
                for key, value in values.items():
                    if keys.key_blocks[key].path_from_id('value') in driven:
                        raise ValueError('Set the source control, not a driven counterpart key')
                    keys.key_blocks[key].value = value
            bpy.context.view_layer.update()
            coords = [_evaluated(o) for o in [b, h]]
            gap = max((coords[0][i] - coords[1][j]).length for i, j in zip(br, hr))
            rows.append({'name': case['name'], 'gap_world': gap, 'continuous': gap <= epsilon,
                         'max_movement_world': {o.name: max((u-v).length for u, v in zip(before, after)) for o, before, after in zip([b, h], base, coords)}})
        return rows
    finally:
        rig.data.pose_position = position
        for p in rig.pose.bones:
            matrix, mode = state[p.name]
            p.rotation_mode = mode
            p.matrix_basis = matrix
        for obj in [b, h]:
            if obj.data.shape_keys:
                for k, value in zip(obj.data.shape_keys.key_blocks, key_state[obj.name]):
                    k.value = value
        bpy.context.view_layer.update()


def bake_seam_normals(body, body_loop, head, head_loop, regions=None, expand=3, factor=.5, donor_keep_faces=None, tolerance=None):
    b, br, h, hr = _pair(body, body_loop, head, head_loop)
    epsilon = _epsilon(b, br, tolerance)
    if expand not in (2,3) or not 0 <= factor <= 1:
        raise ValueError('Invalid expansion/smoothing parameters')
    structural = audit_seam(body, body_loop, head, head_loop, rings=max(1, expand), tolerance=epsilon)
    if structural['structural_errors']:
        raise ValueError('Geometry/binding gate failed: ' + '; '.join(structural['structural_errors']))
    allowed = {o.name: _region(o, ring, expand) for o, ring in [(b,br),(h,hr)]}
    if regions is None:
        regions = {name: {i: 1-depth/(expand+1) for i,depth in depths.items()} for name,depths in allowed.items()}
    regions = {name: {int(i): float(w) for i, w in values.items()} for name, values in regions.items()}
    for obj, ring in [(b, br), (h, hr)]:
        _editable(obj)
        scale = obj.matrix_world.to_scale()
        if obj.matrix_world.determinant() <= 0 or max(scale)-min(scale) > max(scale)*1e-5:
            raise ValueError('Normal donor requires positive uniform world scale')
        if any(float(regions[obj.name].get(i, 0)) != 1 for i in ring):
            raise ValueError('Every seam vertex needs full transfer weight')
        if any(int(i) < 0 or int(i) >= len(obj.data.vertices) or not math.isfinite(w) or not 0 <= w <= 1 for i, w in regions[obj.name].items()):
            raise ValueError('Invalid transfer region')
        if any(w > 0 and i not in allowed[obj.name] for i,w in regions[obj.name].items()):
            raise ValueError('Transfer mask exceeds the selected 2–3 ring region')
        bm = _bm(obj)
        internal = any(len(bm.edges.get((bm.verts[a], bm.verts[c])).link_faces)==2 for a,c in zip(ring,ring[1:]+ring[:1]))
        bm.free()
        if internal and (not donor_keep_faces or obj.name not in donor_keep_faces):
            raise ValueError('Internal loops require explicit donor_keep_faces; preserve original overlap faces')
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object:
                _rig_rest(modifier.object)
    if max((b.matrix_world @ b.data.vertices[i].co-h.matrix_world @ h.data.vertices[j].co).length for i, j in zip(br, hr)) > epsilon:
        raise ValueError('Coincide seam positions before normal transfer')
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    copies, temporary_mods, groups, created_meshes = [], [], [], []
    old_select_mode = tuple(bpy.context.tool_settings.mesh_select_mode)
    visibility = [(m, m.show_viewport) for o in [b, h] for m in o.modifiers]
    normals_to_commit = {}
    old_normals = {o.name: [n.vector.copy() for n in o.data.corner_normals] for o in [b,h]}
    old_smooth = {o.name: [p.use_smooth for p in o.data.polygons] for o in [b,h]}
    committed = False
    clone_rings = []
    try:
        for obj, ring in [(b,br),(h,hr)]:
            for p in obj.data.polygons:
                if any(regions[obj.name].get(i,0)>0 for i in p.vertices):
                    p.use_smooth = True
            # Changing smoothing flags can reinterpret custom-normal storage.
            obj.data.normals_split_custom_set(old_normals[obj.name])
            clone = obj.copy()
            clone.data = obj.data.copy()
            created_meshes.append(clone.data)
            bpy.context.collection.objects.link(clone)
            copies.append(clone)
            clone.shape_key_clear()
            world = obj.matrix_world.copy()
            clone.parent = None
            clone.data.transform(world)
            clone.matrix_world = Matrix.Identity(4)
            for mod in list(clone.modifiers):
                clone.modifiers.remove(mod)
            clone.hide_set(False)
            clone.hide_viewport = False
            clone.hide_select = False
            copied_ring = list(ring)
            if donor_keep_faces and obj.name in donor_keep_faces:
                bm = _bm(clone)
                layer = bm.verts.layers.int.new('_source_vertex')
                for v in bm.verts:
                    v[layer] = v.index
                keep = set(donor_keep_faces[obj.name])
                if not keep or min(keep)<0 or max(keep)>=len(bm.faces):
                    bm.free()
                    raise ValueError('Invalid donor face selection')
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
                bm.verts.index_update()
                remap = {v[layer]:v.index for v in bm.verts}
                copied_ring = [remap[i] for i in ring]
                bm.to_mesh(clone.data)
                bm.free()
            clone_rings.append(_cycle(clone.name, copied_ring))
            bm = _bm(clone)
            boundary_ok = all(len(bm.edges.get((bm.verts[a],bm.verts[c])).link_faces)==1 for a,c in zip(copied_ring,copied_ring[1:]+copied_ring[:1]))
            bm.free()
            if not boundary_ok:
                raise ValueError('Donor face selection must expose the chosen loop on the temporary copy')
        donor_body_count = len(copies[0].data.vertices)
        donor_total_count = sum(len(o.data.vertices) for o in copies)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in copies:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = copies[0]
        bpy.ops.object.join()
        donor = copies[0]
        copies = [donor]
        bm = _bm(donor)
        tag = bm.verts.layers.int.new('_avatar_seam')
        bm.verts.ensure_lookup_table()
        seam = [bm.verts[i] for i in clone_rings[0]] + [bm.verts[i+donor_body_count] for i in clone_rings[1]]
        for v in seam:
            v[tag] = 1
        bmesh.ops.remove_doubles(bm, verts=seam, dist=epsilon)
        if len(bm.verts) != donor_total_count-len(br):
            bm.free()
            raise ValueError('Weld merged more than the approved pairs')
        for v in bm.verts:
            v.select = bool(v[tag])
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            e.smooth = True
        bm.to_mesh(donor.data)
        bm.free()
        if donor.data.has_custom_normals:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.tool_settings.mesh_select_mode = (True, False, False)
        for _ in range(expand):
            bpy.ops.mesh.select_more()
        for _ in range(3):
            bpy.ops.mesh.smooth_normals(factor=factor)
        bpy.ops.object.mode_set(mode='OBJECT')
        for mod, _ in visibility:
            mod.show_viewport = False
        for obj in [b, h]:
            group = obj.vertex_groups.new(name='_avatar_normal_transfer')
            groups.append((obj, group))
            for index, weight in regions[obj.name].items():
                group.add([int(index)], weight, 'REPLACE')
            modifier = obj.modifiers.new('_avatar_normal_transfer', 'DATA_TRANSFER')
            temporary_mods.append((obj, modifier))
            modifier.object = donor
            modifier.use_loop_data = True
            modifier.data_types_loops = {'CUSTOM_NORMAL'}
            modifier.loop_mapping = 'POLYINTERP_NEAREST'
            modifier.vertex_group = group.name
            bpy.context.view_layer.update()
            ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = ev.to_mesh()
            try:
                normals_to_commit[obj.name] = [n.vector.copy() for n in mesh.corner_normals]
                for loop in obj.data.loops:
                    if regions[obj.name].get(loop.vertex_index,0)==0:
                        normals_to_commit[obj.name][loop.index] = old_normals[obj.name][loop.index]
            finally:
                ev.to_mesh_clear()
        for obj in [b, h]:
            obj.data.normals_split_custom_set(normals_to_commit[obj.name])
        committed = True
        return {'transferred_to': [body, head], 'expanded_steps': expand, 'smooth_iterations': 3, 'smooth_factor': factor, 'donor_removed': True}
    finally:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        if not committed:
            for obj in [b,h]:
                for p, smooth in zip(obj.data.polygons,old_smooth[obj.name]):
                    p.use_smooth = smooth
                obj.data.normals_split_custom_set(old_normals[obj.name])
        for obj, modifier in temporary_mods:
            obj.modifiers.remove(modifier)
        for obj, group in groups:
            obj.vertex_groups.remove(group)
        for mod, visible in visibility:
            mod.show_viewport = visible
        for obj in copies:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in created_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.context.tool_settings.mesh_select_mode = old_select_mode
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = active
        bpy.context.view_layer.update()
