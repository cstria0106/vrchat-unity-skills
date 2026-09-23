"""Run only with Blender --background --factory-startup. No commercial fixtures."""
import bpy
import sys
import math
import json
import tempfile
import unittest
import importlib.util
from pathlib import Path
from mathutils import Matrix, Vector

if not bpy.app.background:
    raise RuntimeError('Fixture tests must not run in an interactive Blender scene')
spec = importlib.util.spec_from_file_location('avatar_tools', Path(__file__).with_name('avatar_tools.py'))
av = importlib.util.module_from_spec(spec)
spec.loader.exec_module(av)


def mesh(name, verts, faces):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    for p in data.polygons:
        p.use_smooth = True
    return obj


def tube(name, levels, count=8, taper=0):
    verts = [((1+taper*z)*math.cos(2*math.pi*i/count), (1+taper*z)*math.sin(2*math.pi*i/count), z)
             for z in levels for i in range(count)]
    faces = [(r*count+i, r*count+(i+1)%count, (r+1)*count+(i+1)%count, (r+1)*count+i)
             for r in range(len(levels)-1) for i in range(count)]
    return mesh(name, verts, faces)


def rig_objects(*objects):
    rig = bpy.data.objects.new('Rig', bpy.data.armatures.new('Rig'))
    bpy.context.collection.objects.link(rig)
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    bone = rig.data.edit_bones.new('Head')
    bone.head = (0,0,0)
    bone.tail = (0,0,1)
    bpy.ops.object.mode_set(mode='OBJECT')
    for obj in objects:
        vg = obj.vertex_groups.new(name='Head')
        vg.add(list(range(len(obj.data.vertices))),1,'REPLACE')
        obj.modifiers.new('Armature','ARMATURE').object = rig
    bpy.context.view_layer.update()
    return rig


class AvatarToolsTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def pair(self):
        b = tube('Body',[-3,-2,-1,0])
        h = tube('Head',[0,1,2,3],taper=.15)
        return b,list(range(24,32)),h,list(range(8))

    def test_review_branch_is_independent_and_remaps_rig_and_key_drivers(self):
        b,br,h,hr = self.pair()
        rig = rig_objects(b,h)
        h.parent = rig
        for obj in (b,h):
            obj.shape_key_add(name='Basis')
            obj.shape_key_add(name='Expression').value = 0
        fc = h.data.shape_keys.key_blocks[1].driver_add('value')
        variable = fc.driver.variables.new()
        variable.type = 'SINGLE_PROP'
        variable.targets[0].id_type = 'KEY'
        variable.targets[0].id = b.data.shape_keys
        variable.targets[0].data_path = 'key_blocks["Expression"].value'
        baseline = bpy.context.scene
        result = av.create_review_scene('Review_Test_v1')
        clone = bpy.data.objects[result['objects'][h.name]]
        cb = bpy.data.objects[result['objects'][b.name]]
        cr = bpy.data.objects[result['objects'][rig.name]]
        self.assertIsNot(clone.data, h.data)
        self.assertIsNot(clone.data.shape_keys, h.data.shape_keys)
        self.assertIsNot(cr.data, rig.data)
        self.assertEqual(clone.parent, cr)
        self.assertEqual(clone.modifiers[0].object, cr)
        self.assertEqual(clone.data.shape_keys.animation_data.drivers[0].driver.variables[0].targets[0].id, cb.data.shape_keys)
        clone.data.vertices[0].co.x += 5
        self.assertNotEqual(clone.data.vertices[0].co.x, h.data.vertices[0].co.x)
        cr.pose.bones['Head'].rotation_euler.x = .3
        self.assertEqual(rig.pose.bones['Head'].rotation_euler.x, 0)
        av.discard_review_scene(result['scene'])
        self.assertEqual(bpy.context.scene, baseline)
        self.assertIn(h.name, baseline.objects)
        with self.assertRaisesRegex(ValueError, 'Only marked'):
            av.discard_review_scene(baseline.name)

    def test_review_checkpoint_reloads_without_overwriting_active_file(self):
        b,br,h,hr = self.pair()
        active_path = bpy.data.filepath
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'baseline.blend')
            av.save_review_checkpoint(path)
            self.assertEqual(bpy.data.filepath, active_path)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                av.save_review_checkpoint(path)
            with bpy.data.libraries.load(path) as (source, target):
                target.scenes = source.scenes
            restored = target.scenes[0]
            self.assertEqual(len(restored.objects), 2)
            restored_body = next(o for o in restored.objects if o.name.startswith('Body'))
            self.assertEqual(len(restored_body.data.vertices), len(b.data.vertices))
            bpy.data.scenes.remove(restored)

    def test_native_comparison_offsets_only_independent_copies(self):
        b,br,h,hr=self.pair();rig=rig_objects(b,h);b.parent=rig;h.parent=rig
        source=bpy.context.scene
        candidate=av.create_review_scene('ComparisonCandidate',source.name)
        report=av.create_review_comparison('CompareTogether',[source.name,candidate['scene']],4)
        first=bpy.data.objects[report['candidates'][0]['objects'][b.name]]
        second_source=candidate['objects'][b.name]
        second=bpy.data.objects[report['candidates'][1]['objects'][second_source]]
        bpy.context.view_layer.update()
        self.assertAlmostEqual(second.matrix_world.translation.x-first.matrix_world.translation.x,4)
        self.assertEqual(b.matrix_world.translation.x,0)
        self.assertIsNot(first.data,b.data)
        first.data.vertices[0].co.x+=1
        self.assertNotEqual(first.data.vertices[0].co.x,second.data.vertices[0].co.x)
        av.discard_review_scene(report['scene']);av.discard_review_scene(candidate['scene'])

    def test_complete_boundaries_and_unequal_counts(self):
        b,br,h,hr=self.pair()
        self.assertEqual(sorted(len(c['vertices']) for c in av.boundary_loops(b.name)),[8,8])
        with self.assertRaisesRegex(ValueError,'complete'):
            av.midpoint_targets(b.name,br[:-1],h.name,hr[:-1])
        other=tube('Different',[0,1],count=10)
        with self.assertRaisesRegex(ValueError,'counts'):
            av.midpoint_targets(b.name,br,other.name,list(range(10)))
        bad=hr.copy();bad[1],bad[2]=bad[2],bad[1]
        with self.assertRaisesRegex(ValueError,'order'):
            av.midpoint_targets(b.name,br,h.name,bad)

    def test_internal_loop_is_distinct_from_an_open_boundary(self):
        obj=tube('Tube',[-1,0,1]);ring=set(range(8,16))
        edges=[e.index for e in obj.data.edges if all(i in ring for i in e.vertices)]
        result=av.boundary_loops(obj.name,mode='EDGES',edge_indices=edges)
        self.assertEqual(result[0]['kind'],'internal_edge_candidate')
        self.assertTrue(result[0]['closed'])
        self.assertFalse(result[0]['requires_cut'])
        self.assertFalse(any(set(c['vertices'])==ring for c in av.boundary_loops(obj.name)))
        targets=av.midpoint_targets(obj.name,list(range(8,16)),tube('Other',[0,1]).name,list(range(8)))
        self.assertEqual(len(targets[obj.name]),8)

    def test_surface_section_finds_a_middle_cut_without_editing(self):
        obj=tube('Tube',[-1,1]);obj.location.z=4;bpy.context.view_layer.update()
        before=[v.co[:] for v in obj.data.vertices]
        cuts=av.boundary_loops(obj.name,mode='SECTION',plane_origin=[0,0,4],plane_normal=[0,0,1])
        self.assertEqual(len(cuts),1)
        self.assertTrue(cuts[0]['closed'])
        self.assertEqual(cuts[0]['kind'],'section_candidate')
        self.assertTrue(all(i is None for i in cuts[0]['vertices']))
        self.assertLess(max(abs(p[2]-4) for p in cuts[0]['world_coordinates']),1e-6)
        self.assertEqual([v.co[:] for v in obj.data.vertices],before)

    def test_open_internal_loop_preserves_kept_data_and_disconnected_parts(self):
        obj=tube('Tube',[-1,0,1]);obj.shape_key_add(name='Basis');key=obj.shape_key_add(name='Flex');key.value=0
        for i,p in enumerate(key.data):p.co.x+=i*.01
        original_key=obj.data.shape_keys
        before=[p.co.copy() for p in key.data]
        group=obj.vertex_groups.new(name='Bone')
        for i in range(24):group.add([i],(i+1)/24,'REPLACE')
        uv=obj.data.uv_layers.new(name='UV')
        for loop in obj.data.loops:uv.data[loop.index].uv=(loop.vertex_index*.1,loop.index*.01)
        keep_uv=sorted(tuple(uv.data[i].uv) for p in obj.data.polygons if p.index>=8 for i in p.loop_indices)
        preview=av.open_neck_loop(obj.name,list(range(8,16)),remove_seed_face=0)
        self.assertFalse(preview['committed'])
        self.assertEqual(len(obj.data.vertices),24)
        report=av.open_neck_loop(obj.name,list(range(8,16)),remove_seed_face=0,dry_run=False)
        self.assertEqual(report['removed_vertices'],list(range(8)))
        self.assertIs(obj.data.shape_keys,original_key)
        self.assertTrue(any(set(c['vertices'])==set(report['loop']) and c['closed'] for c in av.boundary_loops(obj.name)))
        self.assertEqual(sorted(tuple(v.uv) for v in obj.data.uv_layers['UV'].data),keep_uv)
        for old,new in report['old_vertex_map'].items():
            self.assertEqual(obj.data.shape_keys.key_blocks['Flex'].data[new].co,before[old])
            self.assertAlmostEqual(obj.vertex_groups['Bone'].weight(new),(old+1)/24,places=6)

    def test_open_loop_rejects_unrelated_seed_without_editing(self):
        obj=tube('Tube',[-1,0,1])
        verts=[v.co[:] for v in obj.data.vertices]+[(4,0,0),(5,0,0),(4,1,0)]
        faces=[list(p.vertices) for p in obj.data.polygons]+[[24,25,26]]
        obj.data.clear_geometry();obj.data.from_pydata(verts,[],faces);obj.data.update()
        with self.assertRaisesRegex(ValueError,'seed'):
            av.open_neck_loop(obj.name,list(range(8,16)),remove_seed_face=16)
        self.assertEqual(len(obj.data.vertices),27)
        report=av.open_neck_loop(obj.name,list(range(8,16)),remove_seed_face=0,dry_run=False)
        self.assertTrue(all(i in report['old_vertex_map'] for i in [24,25,26]))

    def test_nonseparating_torus_loop_is_rejected(self):
        verts=[((2+.5*math.cos(v*math.tau/6))*math.cos(u*math.tau/8),
                (2+.5*math.cos(v*math.tau/6))*math.sin(u*math.tau/8),
                .5*math.sin(v*math.tau/6)) for u in range(8) for v in range(6)]
        faces=[(u*6+v,((u+1)%8)*6+v,((u+1)%8)*6+(v+1)%6,u*6+(v+1)%6) for u in range(8) for v in range(6)]
        obj=mesh('Torus',verts,faces)
        with self.assertRaisesRegex(ValueError,'not separating'):
            av.open_neck_loop(obj.name,list(range(6)),0,dry_run=False)
        self.assertEqual(len(obj.data.polygons),48)

    def test_alignment_preview_export_is_read_only_and_world_aware(self):
        reference=tube('Reference',[0,1]);donor=tube('Donor',[0,1])
        reference.location.x=2;bpy.context.view_layer.update()
        source=[[0,0,0],[1,0,0],[0,0,1]];target=[[2,0,0],[3,0,0],[2,0,1]]
        matrix=Matrix.Translation((2,0,0))
        before=[v.co[:] for v in donor.data.vertices]
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'preview.json')
            av.export_alignment_comparison(reference.name,donor.name,matrix,path,source,target,labels=['A','B','C'])
            data=json.loads(Path(path).read_text())
            self.assertAlmostEqual(data['reference']['vertices'][0][0],3)
            self.assertEqual(data['fit_matrix'][0][3],2)
            self.assertEqual([v.co[:] for v in donor.data.vertices],before)
            with self.assertRaisesRegex(ValueError,'uniform'):
                av.export_alignment_comparison(reference.name,donor.name,Matrix.Diagonal((2,1,1,1)),path,source,target)

    def test_seam_review_is_pending_read_only_and_invalidated_by_geometry(self):
        b,br,h,hr=self.pair();h.location.z=.2;bpy.context.view_layer.update()
        before=[v.co[:] for v in h.data.vertices]
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'seam.json')
            first=av.export_seam_review(b.name,br,h.name,hr,path)
            data=json.loads(Path(path).read_text())
            self.assertEqual(data['approval_status'],'pending')
            self.assertAlmostEqual(data['pairs'][0]['target'][2],.1,places=6)
            self.assertEqual([v.co[:] for v in h.data.vertices],before)
            same=av.export_seam_review(b.name,br,h.name,hr,path)
            self.assertEqual(first['review_id'],same['review_id'])
            h.data.vertices[0].co.z+=.01
            changed=av.export_seam_review(b.name,br,h.name,hr,path)
            self.assertNotEqual(first['review_id'],changed['review_id'])

    def test_similarity_and_collinear_rejection(self):
        source=[[-1,0,0],[1,0,0],[0,-1,-1],[0,2,1]]
        expected=Matrix.Translation((3,4,5))@Matrix.Rotation(.3,4,'X')@Matrix.Scale(1.7,4)
        target=[list(expected@Vector(p)) for p in source]
        out=av.fit_landmarks(source,target)
        self.assertAlmostEqual(out['uniform_scale'],1.7,places=6)
        self.assertLess(max(out['residuals_world']),1e-6)
        self.assertGreater(Matrix(out['matrix']).to_3x3().determinant(),0)
        with self.assertRaisesRegex(ValueError,'Collinear'):
            av.fit_landmarks([[0,0,0],[1,0,0],[2,0,0]],[[0,0,0],[1,0,0],[2,0,0]])

    def test_world_midpoints_preserve_morph_delta(self):
        b,br,h,hr=self.pair()
        b.location=(2,0,0);h.location=(4,0,0)
        h.shape_key_add(name='Basis');key=h.shape_key_add(name='Expression');key.value=0
        key.data[hr[0]].co.z+=.2
        bpy.context.view_layer.update()
        targets=av.midpoint_targets(b.name,br,h.name,hr)
        self.assertAlmostEqual(targets[h.name][hr[0]][0],4,places=6)
        av.apply_vertex_targets(b.name,targets[b.name]);av.apply_vertex_targets(h.name,targets[h.name])
        self.assertLess(max((b.matrix_world@b.data.vertices[i].co-h.matrix_world@h.data.vertices[j].co).length for i,j in zip(br,hr)),1e-6)
        self.assertAlmostEqual((key.data[hr[0]].co-h.data.shape_keys.key_blocks[0].data[hr[0]].co).z,.2,places=6)

    def test_stranded_pentagon_is_transactionally_rejected(self):
        o=mesh('Quad',[(0,0,0),(2,0,0),(2,2,0),(0,2,0)],[(0,1,2,3)])
        old=o.data
        with self.assertRaisesRegex(ValueError,'n-gons'):
            av.apply_topology_plan(o.name,[{'a':0,'b':1,'tag':'s'}],[])
        self.assertIs(o.data,old)
        self.assertEqual(len(o.data.vertices),4)

    def test_symmetry_uses_world_plane_and_detects_asymmetry(self):
        o=mesh('Symmetric',[(-1,0,0),(1,0,0),(0,1,0)],[(0,1,2)])
        o.location.x=3;bpy.context.view_layer.update()
        good=av.symmetry_report(o.name,[0,1,2],[3,0,0],[1,0,0],1e-5)
        self.assertTrue(good['within_tolerance'])
        o.data.vertices[1].co.x+=.1
        bad=av.symmetry_report(o.name,[0,1,2],[3,0,0],[1,0,0],1e-5)
        self.assertFalse(bad['within_tolerance'])

    def test_split_connect_preserves_keys_uv_seam_and_weights(self):
        o=mesh('Patch',[(0,0,0),(2,0,0),(2,2,0),(0,2,0),(0,-2,0),(2,-2,0)],[(0,1,2,3),(1,0,4,5)])
        uv=o.data.uv_layers.new(name='UV')
        for p in o.data.polygons:
            for li in p.loop_indices:
                i=o.data.loops[li].vertex_index
                uv.data[li].uv=(o.data.vertices[i].co.x+(10 if p.index else 0),o.data.vertices[i].co.y)
        o.shape_key_add(name='Basis');key=o.shape_key_add(name='Flex');key.value=0
        key.data[0].co.z=1;key.data[1].co.z=3
        original_key_id=o.data.shape_keys
        g=o.vertex_groups.new(name='Bone');g.add([0],.2,'REPLACE');g.add([1],.8,'REPLACE')
        result=av.apply_topology_plan(o.name,[{'a':0,'b':1,'tag':'s'}],[['s',2],['s',4]])
        i=result['new_vertices']['s']
        self.assertEqual(sorted(len(p.vertices) for p in o.data.polygons),[3,3,4,4])
        self.assertAlmostEqual(o.data.shape_keys.key_blocks['Flex'].data[i].co.z,2,places=6)
        self.assertAlmostEqual(o.vertex_groups['Bone'].weight(i),.5,places=6)
        self.assertEqual({round(o.data.uv_layers['UV'].data[l.index].uv.x,5) for l in o.data.loops if l.vertex_index==i},{1.0,11.0})
        self.assertEqual(result['old_vertex_map'],{i:i for i in range(6)})
        self.assertIs(o.data.shape_keys,original_key_id)

    def test_audit_detects_ngon_even_with_zero_gap(self):
        b,br,h,hr=self.pair();rig_objects(b,h)
        # Split an internal vertical edge without connections: two pentagons,
        # but unchanged, perfectly coincident eight-vertex neck boundaries.
        coords=[v.co[:] for v in b.data.vertices];faces=[list(p.vertices) for p in b.data.polygons]
        a,c=8,16;coords.append(tuple((Vector(coords[a])+Vector(coords[c]))/2));new_id=len(coords)-1
        for fi,face in enumerate(faces):
            rebuilt=[]
            for i,j in zip(face,face[1:]+face[:1]):
                rebuilt.append(i)
                if {i,j}=={a,c}:rebuilt.append(new_id)
            faces[fi]=rebuilt
        b.data.clear_geometry();b.data.from_pydata(coords,[],faces);b.data.update()
        b.vertex_groups.new(name='Head').add(list(range(len(coords))),1,'REPLACE')
        out=av.audit_seam(b.name,br,h.name,hr)
        self.assertEqual(out['basis_gap_world'],0)
        self.assertEqual(len(out['meshes'][b.name]['local_ngons']),2)
        with self.assertRaisesRegex(ValueError,'n-gons'):
            av.bake_seam_normals(b.name,br,h.name,hr,{b.name:{i:1 for i in br},h.name:{i:1 for i in hr}})

    def test_equal_corner_normals_do_not_hide_a_geometric_fold(self):
        b=tube('Body',[-1,0]);h=tube('Head',[0,-.01,1]);br=list(range(8,16));hr=list(range(8))
        for i in range(8,16):
            h.data.vertices[i].co.x*=1.02;h.data.vertices[i].co.y*=1.02
        h.data.update();rig_objects(b,h)
        for o in [b,h]:
            normals=[]
            for loop in o.data.loops:
                p=o.data.vertices[loop.vertex_index].co
                normals.append(Vector((p.x,p.y,0)).normalized())
            o.data.normals_split_custom_set(normals)
        report=av.audit_seam(b.name,br,h.name,hr)
        self.assertLess(report['max_corner_normal_angle_degrees'],.1)
        self.assertGreater(max(report['seam_geometric_angles_degrees']),90)

    def test_pose_measurement_and_restoration_on_error(self):
        b,br,h,hr=self.pair();rig=rig_objects(b,h)
        rig.pose.bones['Head'].rotation_mode='QUATERNION'
        original=rig.pose.bones['Head'].matrix_basis.copy()
        out=av.pose_probe(b.name,br,h.name,hr,rig.name,[{'name':'yaw','rotations':{'Head':[0,.3,0]}}])
        self.assertTrue(out[0]['continuous'])
        self.assertGreater(out[0]['max_movement_world'][h.name],.1)
        with self.assertRaises(KeyError):
            av.pose_probe(b.name,br,h.name,hr,rig.name,[{'name':'invalid','rotations':{'Head':[0,.4,0],'missing':[0,0,0]}}])
        self.assertEqual(rig.pose.bones['Head'].rotation_mode,'QUATERNION')
        self.assertEqual(rig.pose.bones['Head'].matrix_basis,original)

    def test_masked_normal_transfer_preserves_rig_keys_and_helpers(self):
        b,br,h,hr=self.pair()
        for o in [b,h]:o.matrix_world=Matrix.Translation((2,3,4))@Matrix.Rotation(.4,4,'Z')@Matrix.Scale(2,4)
        rig_objects(b,h)
        h.shape_key_add(name='Basis');h.shape_key_add(name='Smile').value=0
        original_objects=set(bpy.data.objects)
        original_groups=[g.name for g in h.vertex_groups]
        regions={b.name:{i:1 for i in range(16,32)},h.name:{i:1 for i in range(16)}}
        far_before=[n.vector.copy() for l,n in zip(h.data.loops,h.data.corner_normals) if l.vertex_index>=24]
        av.bake_seam_normals(b.name,br,h.name,hr,regions)
        report=av.audit_seam(b.name,br,h.name,hr)
        self.assertLess(report['max_corner_normal_angle_degrees'],.15)
        self.assertEqual(set(bpy.data.objects),original_objects)
        self.assertEqual([g.name for g in h.vertex_groups],original_groups)
        self.assertEqual([k.name for k in h.data.shape_keys.key_blocks],['Basis','Smile'])
        self.assertTrue(h.modifiers[0].show_viewport)
        far_after=[n.vector.copy() for l,n in zip(h.data.loops,h.data.corner_normals) if l.vertex_index>=24]
        self.assertLess(max((a-b).length for a,b in zip(far_before,far_after)),1e-4)

    def test_internal_join_normals_keep_overlap_and_distant_flat_shading(self):
        b=tube('Body',[-5,-4,-3,-2,-1,0,1]);h=tube('Head',[-1,0,1,2,3,4,5])
        br=list(range(40,48));hr=list(range(8,16));rig_objects(b,h)
        for o in [b,h]:
            for p in o.data.polygons:p.use_smooth=False
            o.shape_key_add(name='Basis');o.shape_key_add(name='Expression').value=0
        before={o.name:av.snapshot_shading(o.name) for o in [b,h]}
        coords={o.name:[tuple(v.co) for v in o.data.vertices] for o in [b,h]}
        with self.assertRaisesRegex(ValueError,'donor_keep_faces'):
            av.bake_seam_normals(b.name,br,h.name,hr)
        av.bake_seam_normals(b.name,br,h.name,hr,expand=2,
                            donor_keep_faces={b.name:list(range(40)),h.name:list(range(8,48))})
        for o,faces in [(b,list(range(8))),(h,list(range(40,48)))]:
            self.assertEqual([tuple(v.co) for v in o.data.vertices],coords[o.name])
            self.assertEqual(len(o.data.polygons),48)
            corners={i:i for fi in faces for i in o.data.polygons[fi].loop_indices}
            report=av.compare_shading(o.name,before[o.name],corners,{i:i for i in faces})
            self.assertEqual(report['changed_smooth_faces'],[])
            self.assertLess(report['max_normal_angle_degrees'],.1)
        self.assertFalse(av.audit_seam(b.name,br,h.name,hr)['structural_errors'])

    def test_head_bone_fit_and_actual_deformation_preserve_source(self):
        srcmesh=tube('Source',[-1,0,1]);src=rig_objects(srcmesh)
        dstmesh=srcmesh.copy();dstmesh.data=srcmesh.data.copy();bpy.context.collection.objects.link(dstmesh)
        dst=bpy.data.objects.new('TargetRig',bpy.data.armatures.new('TargetRig'));bpy.context.collection.objects.link(dst)
        fit=Matrix.Translation((2,3,4))@Matrix.Rotation(.5,4,'Y')@Matrix.Scale(1.4,4)
        dstmesh.matrix_world=fit@srcmesh.matrix_world
        report=av.copy_head_bones(src.name,dst.name,{'Head':'EyeCopy'},{},fit)
        dstmesh.vertex_groups['Head'].name='EyeCopy';dstmesh.modifiers[0].object=dst
        self.assertLess(report['fit'][0]['tail_error_world'],1e-6)
        self.assertLess(max(report['fit'][0]['axis_errors_degrees']),.1)
        for rig,bone in [(src,'Head'),(dst,'EyeCopy')]:
            rig.pose.bones[bone].rotation_mode='XYZ';rig.pose.bones[bone].rotation_euler=(.2,.3,.1)
        mapping={i:i for i in range(len(srcmesh.data.vertices))}
        self.assertLess(av.compare_deformation(srcmesh.name,dstmesh.name,mapping,fit)['max_error_world'],2e-6)
        dst.pose.bones['EyeCopy'].rotation_euler=(.7,0,0)
        self.assertGreater(av.compare_deformation(srcmesh.name,dstmesh.name,mapping,fit)['max_error_world'],.1)


suite=unittest.defaultTestLoader.loadTestsFromTestCase(AvatarToolsTests)
out=unittest.TextTestRunner(verbosity=2).run(suite)
if not out.wasSuccessful():
    sys.exit(1)
