import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import matplotlib.image as mpimg

spec=importlib.util.spec_from_file_location('renderer',Path(__file__).with_name('render_alignment_comparison.py'))
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)


class AlignmentRendererTests(unittest.TestCase):
    def test_profile_intersects_face_interiors(self):
        segments=renderer.section_segments([[-1,0,0],[1,0,0],[1,0,2]],[[0,1,2]])
        self.assertEqual(segments.shape,(1,2,3))
        self.assertTrue(np.allclose(segments[:,:,0],0))
        self.assertEqual(sorted(segments[0,:,2].tolist()),[0,1])

    def test_png_and_metric_errors_describe_the_same_fit(self):
        vertices=[[0,0,0],[.02,0,0],[0,0,.02]]
        geometry={'vertices':vertices,'edges':[[0,1],[1,2],[2,0]],'triangles':[[0,1,2]]}
        matrix=np.eye(4);matrix[0,3]=.01
        targets=renderer.transform(vertices,matrix).tolist()
        data={'schema':1,'reference':dict(geometry,vertices=targets),'donor':geometry,
              'fit_matrix':matrix.tolist(),'previous_matrix':np.eye(4).tolist(),
              'source_landmarks':vertices,'target_landmarks':targets,'labels':['A','B','C'],
              'view_origin':[0,0,0],'view_axes':np.eye(3).tolist(),'meters_per_world_unit':1,'geometry_state':'Basis'}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'preview.json';output=Path(folder)/'preview.png'
            source.write_text(json.dumps(data),encoding='utf8')
            result=renderer.render_comparison(source,output)
            metrics=json.loads(Path(result['metrics']).read_text())
            self.assertTrue(all(abs(p['before_distance_mm']-10)<1e-8 for p in metrics['landmarks']))
            self.assertTrue(all(p['after_distance_mm']<1e-8 for p in metrics['landmarks']))
            raster=mpimg.imread(result['image'])
            self.assertGreater(raster.shape[0],500)
            self.assertGreater(float(np.std(raster)),.01)


if __name__=='__main__':unittest.main()
