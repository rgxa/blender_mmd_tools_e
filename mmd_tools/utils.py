# -*- coding: utf-8 -*-
import re
import os

import bpy
from mmd_tools.bpyutils import SceneOp

def getAObject():
    """現在のアクティブオブジェクトを取得する

    Args:
        obj:

    Returns:
        現在のアクティブオブジェクト

    """
    if bpy.app.version < (2, 80, 0):
        return bpy.context.scene.objects.active
    else:
        return bpy.context.view_layer.objects.active

def setAObject(obj):
    """引数をアクティブオブジェクトに設定して、元のアクティブオブジェクトを返す

    Args:
        obj:
            ブレンダーのオブジェクト

    Returns:
        元のアクティブオブジェクト

    """
    if bpy.app.version < (2, 80, 0):
        old = bpy.context.scene.objects.active
        bpy.context.scene.objects.active = obj
    else:
        old = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = obj
    return old

## 指定したオブジェクトのみを選択状態かつアクティブにする
def selectAObject(obj):
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass
    bpy.ops.object.select_all(action='DESELECT')
    SceneOp(bpy.context).active_object = obj

## 現在のモードを指定したオブジェクトのEdit Modeに変更する
def enterEditMode(obj):
    selectAObject(obj)
    if obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')

def setParentToBone(obj, parent, bone_name):
    selectAObject(obj)
    SceneOp(bpy.context).active_object = parent
    bpy.ops.object.mode_set(mode='POSE')
    parent.data.bones.active = parent.data.bones[bone_name]
    bpy.ops.object.parent_set(type='BONE', xmirror=False, keep_transform=False)
    bpy.ops.object.mode_set(mode='OBJECT')

def selectSingleBone(context, armature, bone_name, reset_pose=False):
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except:
        pass
    for i in context.selected_objects:
        i.select = False
    SceneOp(context).active_object = armature
    bpy.ops.object.mode_set(mode='POSE')
    if reset_pose:
        for p_bone in armature.pose.bones:
            p_bone.matrix_basis.identity()
    armature_bones = armature.data.bones
    for i in armature_bones:
        i.select = (i.name == bone_name)
        i.select_head = i.select_tail = i.select
        if i.select:
            armature_bones.active = i
            i.hide = False
            #armature.data.layers[list(i.layers).index(True)] = True


__CONVERT_NAME_TO_L_REGEXP = re.compile('^(.*)左(.*)$')
__CONVERT_NAME_TO_R_REGEXP = re.compile('^(.*)右(.*)$')
## 日本語で左右を命名されている名前をblender方式のL(R)に変更する
def convertNameToLR(name, use_underscore=False):
    m = __CONVERT_NAME_TO_L_REGEXP.match(name)
    delimiter = '_' if use_underscore else '.'
    if m:
        name = m.group(1) + m.group(2) + delimiter + 'L'
    m = __CONVERT_NAME_TO_R_REGEXP.match(name)
    if m:
        name = m.group(1) + m.group(2) + delimiter + 'R'
    return name

__CONVERT_L_TO_NAME_REGEXP = re.compile(r'(?P<lr>(?P<separator>[._])[lL])(?P<after>($|(?P=separator)))')
__CONVERT_R_TO_NAME_REGEXP = re.compile(r'(?P<lr>(?P<separator>[._])[rR])(?P<after>($|(?P=separator)))')
def convertLRToName(name):
    match = __CONVERT_L_TO_NAME_REGEXP.search(name)
    if match:
        return f"左{name[0:match.start()]}{match['after']}{name[match.end():]}"

    match = __CONVERT_R_TO_NAME_REGEXP.search(name)
    if match:
        return f"右{name[0:match.start()]}{match['after']}{name[match.end():]}"

    return name

## src_vertex_groupのWeightをdest_vertex_groupにaddする
def mergeVertexGroup(meshObj, src_vertex_group_name, dest_vertex_group_name):
    mesh = meshObj.data
    src_vertex_group = meshObj.vertex_groups[src_vertex_group_name]
    dest_vertex_group = meshObj.vertex_groups[dest_vertex_group_name]

    vtxIndex = src_vertex_group.index
    for v in mesh.vertices:
        try:
            gi = [i.group for i in v.groups].index(vtxIndex)
            dest_vertex_group.add([v.index], v.groups[gi].weight, 'ADD')
        except ValueError:
            pass

def __getCustomNormalKeeper(mesh):
    if hasattr(mesh, 'has_custom_normals') and mesh.use_auto_smooth:
        class _CustomNormalKeeper:
            def __init__(self, mesh):
                mesh.calc_normals_split()
                self.__normals = tuple(zip((l.normal.copy() for l in mesh.loops), (p.material_index for p in mesh.polygons for v in p.vertices)))
                mesh.free_normals_split()
                self.__material_map = {}
                materials = mesh.materials
                for i, m in enumerate(materials):
                    if m is None or m.name in self.__material_map:
                        materials[i] = bpy.data.materials.new('_mmd_tmp_')
                    self.__material_map[materials[i].name] = (i, getattr(m, 'name', ''))

            def restore_custom_normals(self, mesh):
                materials = mesh.materials
                for i, m in enumerate(materials):
                    mat_id, mat_name_orig = self.__material_map[m.name]
                    if m.name != mat_name_orig:
                        materials[i] = bpy.data.materials.get(mat_name_orig, None)
                        m.user_clear()
                        bpy.data.materials.remove(m)
                if len(materials) == 1:
                    mesh.normals_split_custom_set([n for n, x in self.__normals if x == mat_id])
                    mesh.update()
        return _CustomNormalKeeper(mesh) # This fixes the issue that "SeparateByMaterials" could break custom normals
    return None

def separateByMaterials(meshObj):
    if len(meshObj.data.materials) < 2:
        selectAObject(meshObj)
        return
    custom_normal_keeper = __getCustomNormalKeeper(meshObj.data)
    matrix_parent_inverse = meshObj.matrix_parent_inverse.copy()
    prev_parent = meshObj.parent
    dummy_parent = bpy.data.objects.new(name='tmp', object_data=None)
    meshObj.parent = dummy_parent
    meshObj.active_shape_key_index = 0
    try:
        enterEditMode(meshObj)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
        for i in dummy_parent.children:
            if custom_normal_keeper:
                custom_normal_keeper.restore_custom_normals(i.data)
            materials = i.data.materials
            i.name = getattr(materials[0], 'name', 'None') if len(materials) else 'None'
            i.parent = prev_parent
            i.matrix_parent_inverse = matrix_parent_inverse
        bpy.data.objects.remove(dummy_parent)

def clearUnusedMeshes():
    meshes_to_delete = []
    for mesh in bpy.data.meshes:
        if mesh.users == 0:
            meshes_to_delete.append(mesh)

    for mesh in meshes_to_delete:
        bpy.data.meshes.remove(mesh)


## Boneのカスタムプロパティにname_jが存在する場合、name_jの値を
# それ以外の場合は通常のbone名をキーとしたpose_boneへの辞書を作成
def makePmxBoneMap(armObj):
    # Maintain backward compatibility with mmd_tools v0.4.x or older.
    return {(i.mmd_bone.name_j or i.get('mmd_bone_name_j', i.get('name_j', i.name))):i for i in armObj.pose.bones}

def uniqueName(name, used_names):
    if name not in used_names:
        return name
    count = 1
    new_name = orig_name = re.sub(r'\.\d{1,}$', '', name)
    while new_name in used_names:
        new_name = '%s.%03d'%(orig_name, count)
        count += 1
    return new_name

def int2base(x, base, width=0):
    """
    Method to convert an int to a base
    Source: http://stackoverflow.com/questions/2267362
    """
    import string
    digs = string.digits + string.ascii_uppercase
    assert(2 <= base <= len(digs))
    digits, negtive = '', False
    if x <= 0:
        if x == 0:
            return '0'*max(1, width)
        x, negtive, width = -x, True, width-1
    while x:
        digits = digs[x % base] + digits
        x //= base
    digits = '0'*(width-len(digits)) + digits
    if negtive:
        digits = '-' + digits
    return digits

def saferelpath(path, start, strategy='inside'):
    """
    On Windows relpath will raise a ValueError
    when trying to calculate the relative path to a
    different drive.
    This method will behave different depending on the strategy
    choosen to handle the different drive issue.
    Strategies:
    - inside: this will just return the basename of the path given
    - outside: this will prepend '..' to the basename
    - absolute: this will return the absolute path instead of a relative.
    See http://bugs.python.org/issue7195
    """
    result = os.path.basename(path)
    if os.name == 'nt':
        d1 = os.path.splitdrive(path)[0]
        d2 = os.path.splitdrive(start)[0]
        if d1 != d2:
            if strategy == 'outside':
                result = '..'+os.sep+os.path.basename(path)
            elif strategy == 'absolute':
                result = os.path.abspath(path)
        else:
            result = os.path.relpath(path, start)
    else:
        result = os.path.relpath(path, start)
    return result

def object_filter(lst, mode, *args, filters=(), **kwargs):
    """Filter objects using a set of test functions.
    New options can be added easily by adding a pair of property and test function to object_filters.

    Args:
        mode:
            The filter in object_filters to use.
        filters:
            Support for additional filters to be passed as arguments.
            Example: additional_filters = [lambda x: obj.parent is not None] will remove any objects with no parent
                from the selection.
        lst:
            A list of Blender objects.

    Returns:
            Either:
                A list of Blender objects for which all test functions return True
                The original list if no filter options are active

    """
    # Create a set of options and their respective test functions.
    default_filters = dict((
        ("active", lambda ob, *args, **kwargs: ob == getAObject()),
        ("selected", lambda ob, *args, **kwargs: ob.select),
        ("render", lambda ob, *args, **kwargs: not ob.hide_render),
        ("visible", lambda ob, *args, **kwargs: not ob.hide),
        ("none", lambda ob, *args, **kwargs: False),
    ))
    # Get the selected option and its corresponding test function.
    filter_func = default_filters.get(mode, None)
    if filter_func is None:
        raise ValueError("Error in determining mesh filter:  Unknown mesh selection mode:"
                         + str(mode))
    # Make a new filter that runs the default filter and all filters in the "filters" argument.
    def final_filter(ob):
        return all(f(ob, *args, **kwargs) for f in (filter_func, *filters))
    # Exclude objects that fail any filter test.
    return [ob for ob in lst if final_filter(ob)]

def active_filter_code(lst, obj_type="MESH", idx=None):
    """Sensible default method for selecting an object from a set of objects.

        Returns:
            In order of priority:
                Return None if no objects are selected or active.
                Return any active object.
                Return the object at index idx.
                Return the first selected object.
            Also return a code indicating which path was taken.
    """
    obj_type = obj_type.upper()
    sel_objs = object_filter(lst, "selected", filters=(lambda ob: ob.type == obj_type,))
    if len(sel_objs) <= 0:
        return None, 0
    act_obj = object_filter(sel_objs, "active")
    if len(act_obj) > 0:
        return act_obj[0], 1
    if idx is not None:
        return sel_objs[idx], 2
    return sel_objs[0], 3

def active_filter(lst, obj_type="MESH", idx=None):
    """Convenience wrapper for active_filter_code.
    """
    return active_filter_code(lst, obj_type=obj_type, idx=idx)[0]

class ItemOp:
    @staticmethod
    def get_by_index(items, index):
        if 0 <= index < len(items):
            return items[index]
        return None

    @staticmethod
    def resize(items, length):
        count = length - len(items)
        if count > 0:
            for i in range(count):
                items.add()
        elif count < 0:
            for i in range(-count):
                items.remove(length)

    @staticmethod
    def add_after(items, index):
        index_end = len(items)
        index = max(0, min(index_end, index+1))
        items.add()
        items.move(index_end, index)
        return items[index], index

class ItemMoveOp:
    type: bpy.props.EnumProperty(
        name='Type',
        description='Move type',
        items = [
            ('UP', 'Up', '', 0),
            ('DOWN', 'Down', '', 1),
            ('TOP', 'Top', '', 2),
            ('BOTTOM', 'Bottom', '', 3),
            ],
        default='UP',
        )

    @staticmethod
    def move(items, index, move_type, index_min=0, index_max=None):
        if index_max is None:
            index_max = len(items)-1
        else:
            index_max = min(index_max, len(items)-1)
        index_min = min(index_min, index_max)

        if index < index_min:
            items.move(index, index_min)
            return index_min
        elif index > index_max:
            items.move(index, index_max)
            return index_max

        index_new = index
        if move_type == 'UP':
            index_new = max(index_min, index-1)
        elif move_type == 'DOWN':
            index_new = min(index+1, index_max)
        elif move_type == 'TOP':
            index_new = index_min
        elif move_type == 'BOTTOM':
            index_new = index_max

        if index_new != index:
            items.move(index, index_new)
        return index_new

