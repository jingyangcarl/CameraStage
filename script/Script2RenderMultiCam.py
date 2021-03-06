import bpy
import os
from mathutils import Matrix, Vector
import numpy
import time
import argparse
import sys

# blender 2.8+

#---------------------------------------------------------------
# 3x4 P matrix from Blender camera
#---------------------------------------------------------------

# Build intrinsic camera parameters from Blender camera data
#
# See notes on this in 
# blender.stackexchange.com/questions/15102/what-is-blenders-camera-projection-matrix-model
def get_K_from_blender(camd):
    f_in_mm = camd.lens
    scene = bpy.context.scene
    resolution_x_in_px = scene.render.resolution_x
    resolution_y_in_px = scene.render.resolution_y
    scale = scene.render.resolution_percentage / 100
    sensor_width_in_mm = camd.sensor_width
    sensor_height_in_mm = camd.sensor_height
    pixel_aspect_ratio = scene.render.pixel_aspect_x / scene.render.pixel_aspect_y
    if (camd.sensor_fit == 'VERTICAL'):
        # the sensor height is fixed (sensor fit is horizontal), 
        # the sensor width is effectively changed with the pixel aspect ratio
        s_u = resolution_x_in_px * scale / sensor_width_in_mm / pixel_aspect_ratio 
        s_v = resolution_y_in_px * scale / sensor_height_in_mm
    else: # 'HORIZONTAL' and 'AUTO'
        # the sensor width is fixed (sensor fit is horizontal), 
        # the sensor height is effectively changed with the pixel aspect ratio
        pixel_aspect_ratio = scene.render.pixel_aspect_x / scene.render.pixel_aspect_y
        s_u = resolution_x_in_px * scale / sensor_width_in_mm
        s_v = resolution_y_in_px * scale * pixel_aspect_ratio / sensor_height_in_mm


    # Parameters of intrinsic calibration matrix K
    alpha_u = f_in_mm * s_u
    alpha_v = f_in_mm * s_v
    u_0 = resolution_x_in_px * scale / 2
    v_0 = resolution_y_in_px * scale / 2
    skew = 0 # only use rectangular pixels

    K = Matrix(
        ((alpha_u, skew,    u_0),
        (    0  , alpha_v, v_0),
        (    0  , 0,        1 )))
    return K

# Returns camera rotation and translation matrices from Blender.
def get_RT_from_blender(cam):
    T, R = cam.matrix_world.decompose()[0:2]
    return T, R

def get_3x4_P_matrix_from_blender(cam):
    K = get_K_from_blender(cam.data)
    T, R = get_RT_from_blender(cam)
    return K, T, R

def render_depth_color(out_dir, out_mode, out_form='png'):

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    
    cameras_RT = {}
    cameras_K = {}
    cameras = bpy.data.cameras

    # loop through each camera
    for i, camera in enumerate(cameras) :
        
        # get current camera
        camera = bpy.context.scene.objects[camera.name]
        print('Render using camera: ' + camera.name)
        
        # set path to save rendered results
        outpath_image = out_dir + camera.name + '.' + out_form
        outpath_K = out_dir+camera.name+'_K.txt'
        outpath_RT = out_dir+camera.name+'_RT.txt'
        
        # deselect all objects
        bpy.ops.object.select_all(action='DESELECT')
        # Make the current camera an active object
        bpy.context.view_layer.objects.active = camera
        # select the current camera
        camera.select_set(True)
        
        # set active object as cameratype
        bpy.context.scene.camera = camera
        
        # define renderer
        def render_image():
            ## render image
            print('Rendering model ' + camera.name)
            tic = time.perf_counter()
            bpy.ops.render.render()
            toc = time.perf_counter()
            print('Rendering completed in ', toc - tic, ' seconds')
            # save rendered image
            bpy.data.images['Render Result'].save_render(outpath_image)
        
        # render based on the outmode
        if out_mode == 'all':
            render_image()
        elif out_mode.upper() in camera.name:
            # remember to change compositing nodes
            render_image();
        else: pass
        
        # get K, R, T and print
        K, T, R = get_3x4_P_matrix_from_blender(camera)
        print(K)
        print(T)
        print(R)
        
        # save Ks, and RTs
        cameras_K[camera.name] = numpy.matrix(K).A1.tolist()
        cameras_RT[camera.name] = numpy.concatenate((R, T))[None].flatten()
        
        # save K, R, T
        numpy.savetxt(outpath_K, cameras_K[camera.name])
        print('intrinsic parameter saved at '+outpath_K)
        numpy.savetxt(outpath_RT, cameras_RT[camera.name])
        print('extrinsic parameter saved at '+outpath_RT)
        
        print('')
        
    # save RTs and Ks
    numpy.savetxt(out_dir+'intrinsic.txt', list(cameras_K.values()))
    numpy.savetxt(out_dir+'extrinsic.txt', list(cameras_RT.values()))
    print('')
    
    return 0

#---------------------------------------------------------------
# ArgumentParserForBlender
# refer to https://blender.stackexchange.com/questions/6817/how-to-pass-command-line-arguments-to-a-blender-python-script
#---------------------------------------------------------------
class ArgumentParserForBlender(argparse.ArgumentParser):
    """
    This class is identical to its superclass, except for the parse_args
    method (see docstring). It resolves the ambiguity generated when calling
    Blender from the CLI with a python script, and both Blender and the script
    have arguments. E.g., the following call will make Blender crash because
    it will try to process the script's -a and -b flags:
    >>> blender --python my_script.py -a 1 -b 2

    To bypass this issue this class uses the fact that Blender will ignore all
    arguments given after a double-dash ('--'). The approach is that all
    arguments before '--' go to Blender, arguments after go to the script.
    The following calls work fine:
    >>> blender --python my_script.py -- -a 1 -b 2
    >>> blender --python my_script.py --
    """

    def _get_argv_after_doubledash(self):
        """
        Given the sys.argv as a list of strings, this method returns the
        sublist right after the '--' element (if present, otherwise returns
        an empty list).
        """
        try:
            idx = sys.argv.index("--")
            return sys.argv[idx+1:] # the list after '--'
        except ValueError as e: # '--' not in the list:
            return []

    # overrides superclass
    def parse_args(self):
        """
        This method is expected to behave identically as in the superclass,
        except that the sys.argv list will be pre-processed using
        _get_argv_after_doubledash before. See the docstring of the class for
        usage examples and details.
        """
        return super().parse_args(args=self._get_argv_after_doubledash())

#---------------------------------------------------------------
# main
# the following command will run in background
# ./blender 
#   --background ~/Documents/Project/CameraStage/CameraStage.blend 
#   --python ~/Documents/Project/CameraStage/script/Script2RenderMultiCam.py 
#   -- 
#     -i /mount/ForCarl/Data/MIXAMO/generated_frames_textured/ 
#     -o /mount/ForCarl/Data/MIXAMO/generated_frames_rendered/
#     -m rgb
#---------------------------------------------------------------
in_dir_root = '/home/ICT2000/jyang/Documents/Data/MIXAMO/generated_frames_textured/'
out_dir_root = '/home/ICT2000/jyang/Documents/Data/MIXAMO/generated_frames_rendered/'
out_mode = 'rgb'
out_form = 'exr'
resolution_x = 640
resolution_y = 480

parser = ArgumentParserForBlender()
parser.add_argument('-i', '--in_dir_root', type=str, default=in_dir_root)
parser.add_argument('-o', '--out_dir_root', type=str, default=out_dir_root)
parser.add_argument('-x', '--resolution_x', type=int, default=640)
parser.add_argument('-y', '--resolution_y', type=int, default=480)
parser.add_argument('-m', '--out_mode', type=str, default=out_mode)
parser.add_argument('-f', '--out_form', type=str, default='png')
args = parser.parse_args() 

in_dir_root = args.in_dir_root
out_dir_root = args.out_dir_root
out_mode = args.out_mode
out_form = args.out_form

bpy.context.scene.render.resolution_x = args.resolution_x
bpy.context.scene.render.resolution_y = args.resolution_y
bpy.context.scene.cycles.device = 'GPU'

for r, d, f in os.walk(in_dir_root):
    for file in f:
        if '.obj' in file:
            # find mesh
            filepath = os.path.join(r, file)
            filename, _ = os.path.splitext(file)
            
            # load obj to the current scene
            bpy.ops.import_scene.obj(filepath=filepath)
            
            # select the current object and set it to active
            imported_obj = bpy.context.selected_objects[0]
            bpy.context.view_layer.objects.active = imported_obj
            imported_obj.select_set(True)
            
            # set transformation
            pi = 3.141592653589793
            bpy.data.objects[imported_obj.name].location = (0, 0, 0.20)
            bpy.data.objects[imported_obj.name].scale = (0.005, 0.005, 0.005)
            bpy.data.objects[imported_obj.name].rotation_mode = 'XYZ'
            bpy.data.objects[imported_obj.name].rotation_euler = (0.5*pi, 0, 0.125*pi) # 90 0 22.5
            
            # loop through the material slots related and set blend_mode to OPAQUE
            for index, material in enumerate(bpy.data.objects[imported_obj.name].material_slots):
                bpy.data.objects[imported_obj.name].active_material_index = index
                bpy.context.object.active_material.blend_method = 'OPAQUE'
            
            # set output path
            path_relative = os.path.dirname(filepath)[len(in_dir_root):]
            out_dir = out_dir_root + os.path.splitext(path_relative)[0] + '/'
            
            # render
            render_depth_color(out_dir, out_mode, out_form)
            
            # clean up material
            for material in bpy.data.materials:
                material.user_clear()
                bpy.data.materials.remove(material)
            
            # select back to the imported_obj
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = imported_obj
            imported_obj.select_set(True)
            
            # clean up object
            bpy.ops.object.delete()