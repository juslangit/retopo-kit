# SPDX-License-Identifier: GPL-3.0-or-later
"""Retopo Kit — sculpt to game-ready.

Step 1, remesh: Blender's own Quadriflow asks for a target face count, which nobody
knows in advance. This asks how big each quad should be in centimetres, which is a
question an artist can answer, and works the count out from the surface area.

Step 2, unwrap: the low-poly gets UVs immediately, sized for the texture it will be
baked into, because nothing further in the chain can happen without them.

Step 3, bake: the sculpt's detail is projected onto the low-poly as a normal map,
with the ray distance worked out from the model's own size rather than left as a
number to guess at.

Step 4, batch: the whole chain runs over every selected sculpt, and one bad object
reports itself instead of stopping the rest.

The sculpt is never modified. The result is a new object named LP_<name>.
"""

bl_info = {
    "name": "Retopo Kit",
    "author": "Luqman Hakeem",
    "version": (0, 4, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar (N) > Retopo",
    "description": "Sculpt to game-ready: remesh, unwrap, bake, over a whole selection.",
    "category": "Mesh",
}

import time

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       PointerProperty, StringProperty)
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector


# --------------------------------------------------------------------------- #
# Working out how many faces to ask for
# --------------------------------------------------------------------------- #

def surface_area(obj, depsgraph):
    """Total area of the object in square metres, with modifiers applied."""
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    # Polygon areas are in the object's local space, so scale has to be folded in.
    scale = obj.matrix_world.to_scale()
    factor = abs(scale.x * scale.y * scale.z) ** (2.0 / 3.0)
    area = sum(polygon.area for polygon in mesh.polygons) * factor
    evaluated.to_mesh_clear()
    return area


def faces_for_quad_size(area, quad_size_cm):
    """How many quads of that size it takes to cover this much surface.

    A quad `s` metres across covers s * s square metres, so the count is simply
    the area divided by that. Clamped to a range Quadriflow can actually work in.
    """
    side = max(quad_size_cm, 0.01) / 100.0        # centimetres to metres
    count = int(area / (side * side))
    return max(20, min(count, 500000))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

class RETOPO_Settings(PropertyGroup):
    quad_size: FloatProperty(
        name="Quad Size (cm)",
        description="Roughly how wide each quad should be, in centimetres",
        default=2.0, min=0.05, max=100.0, soft_max=20.0, unit="NONE")
    preset: EnumProperty(
        name="Preset", default="CUSTOM",
        items=[
            ("HERO", "Hero prop (0.8 cm)", "Fine quads for something the camera gets close to"),
            ("PROP", "Game prop (2 cm)", "A sensible middle for most props"),
            ("BACKGROUND", "Background (6 cm)", "Coarse quads for things seen from far away"),
            ("CUSTOM", "Custom", "Set the quad size by hand"),
        ])
    use_symmetry: BoolProperty(
        name="Symmetry", default=True,
        description="Keep the result mirrored across X, for characters and most props")
    preserve_sharp: BoolProperty(
        name="Keep Sharp Edges", default=True,
        description="Try to follow hard edges rather than rounding them off")
    keep_original: BoolProperty(
        name="Keep the Sculpt", default=True,
        description="Hide the original rather than replacing it. Leave this on")

    # --- step 2: unwrap ---
    auto_unwrap: BoolProperty(
        name="Unwrap After Remesh", default=True,
        description="Give the new low-poly UVs straight away. Nothing further in "
                    "the chain can happen without them")
    texture_size: EnumProperty(
        name="Texture Size", default="2048",
        description="The texture these UVs will be baked into. It sets how much "
                    "space to leave between islands so the bake does not bleed",
        items=[("1024", "1K", "1024 x 1024"),
               ("2048", "2K", "2048 x 2048"),
               ("4096", "4K", "4096 x 4096")])
    # --- step 3: bake ---
    auto_bake: BoolProperty(
        name="Bake After Unwrap", default=False,
        description="Project the sculpt's detail onto the low-poly straight away. "
                    "Off by default because baking is the slow step")
    cage_auto: BoolProperty(
        name="Work Out Ray Distance", default=True,
        description="Derive how far the rays travel from the model's own size. "
                    "Turn this off only if the bake comes out wrong")
    cage_distance: FloatProperty(
        name="Ray Distance (cm)",
        description="How far outside the low-poly to search for the sculpt. Too "
                    "short and you get black patches; too long and rays hit the "
                    "far side of the model",
        default=2.0, min=0.01, max=100.0, soft_max=20.0)

    last_report: StringProperty(default="")

    seam_angle: FloatProperty(
        name="Seam Angle",
        description="How sharp a bend has to be before the UVs are cut there. "
                    "Lower cuts more often and distorts less",
        default=66.0, min=1.0, max=89.0, subtype="ANGLE_UNSIGNED" if False else "NONE")


PRESET_SIZES = {"HERO": 0.8, "PROP": 2.0, "BACKGROUND": 6.0}


def effective_quad_size(settings):
    return PRESET_SIZES.get(settings.preset, settings.quad_size)


# --------------------------------------------------------------------------- #
# Step 2 — unwrapping
# --------------------------------------------------------------------------- #

def uv_coverage(mesh):
    """How much of the 0-1 UV square the islands actually fill, as a percentage.

    Wasted space here is wasted texture resolution later, so it is worth showing.
    """
    layer = mesh.uv_layers.active
    if layer is None:
        return 0.0
    total = 0.0
    for polygon in mesh.polygons:
        loops = [layer.data[i].uv for i in polygon.loop_indices]
        # Shoelace formula: the area of any polygon from its corner coordinates.
        area = 0.0
        for i in range(len(loops)):
            a, b = loops[i], loops[(i + 1) % len(loops)]
            area += a.x * b.y - b.x * a.y
        total += abs(area) * 0.5
    return min(total * 100.0, 100.0)


def unwrap_object(obj, settings):
    """Cut and lay out UVs on obj. Returns (island count, coverage percent)."""
    import math

    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")

    texture_pixels = int(settings.texture_size)
    # Leave a few pixels between islands, expressed as a fraction of the texture,
    # so the normal bake cannot bleed from one island into its neighbour.
    margin = 4.0 / texture_pixels

    previous_mode = obj.mode
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")

    bpy.ops.uv.smart_project(
        angle_limit=math.radians(settings.seam_angle),
        island_margin=margin,
        area_weight=0.0,
        correct_aspect=True,
        scale_to_bounds=False,
    )
    # Record where Smart Project chose to cut, as real seams, so the artist can
    # see and adjust them instead of the cuts being invisible.
    bpy.ops.uv.seams_from_islands()
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin, rotate=True)

    bpy.ops.object.mode_set(mode=previous_mode)

    islands = sum(1 for edge in mesh.edges if edge.use_seam)
    return islands, uv_coverage(mesh)


class RETOPO_OT_unwrap(Operator):
    bl_idname = "retopo.unwrap"
    bl_label = "Unwrap"
    bl_description = "Cut and lay out UVs on the selected mesh, sized for the bake"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.retopo

        if len(obj.data.polygons) > 200000:
            self.report({"ERROR"},
                        "That mesh has %s faces — remesh it before unwrapping"
                        % f"{len(obj.data.polygons):,}")
            return {"CANCELLED"}

        _seams, coverage = unwrap_object(obj, settings)
        self.report({"INFO"}, "%s unwrapped — %.0f%% of the %s map used"
                    % (obj.name, coverage, settings.texture_size))
        return {"FINISHED"}


# --------------------------------------------------------------------------- #
# Step 3 — baking the detail down
# --------------------------------------------------------------------------- #

def diagonal_cm(obj):
    """Length of the object's bounding box diagonal, in centimetres."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    low = Vector((min(c[i] for c in corners) for i in range(3)))
    high = Vector((max(c[i] for c in corners) for i in range(3)))
    return (high - low).length * 100.0


def ray_distance_cm(obj, settings):
    """How far the bake rays should travel, in centimetres.

    Two percent of the model's diagonal catches the sculpt's detail without the
    rays reaching far enough to hit the opposite side of the model.
    """
    if not settings.cage_auto:
        return settings.cage_distance
    return max(0.2, diagonal_cm(obj) * 0.02)


def ensure_material(obj, name):
    """Give the object a material with nodes, reusing one if it already has it."""
    if obj.data.materials and obj.data.materials[0] is not None:
        material = obj.data.materials[0]
    else:
        material = bpy.data.materials.new(name)
        obj.data.materials.append(material)
    material.use_nodes = True
    return material


def wire_normal_map(material, image):
    """Plug the baked image into the shader so the detail is actually visible.

    Without this the bake produces a picture nobody ever sees.
    """
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    texture = next((n for n in nodes
                    if n.type == "TEX_IMAGE" and n.image is image), None)
    if texture is None:
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.location = (-700, -200)
    texture.image.colorspace_settings.name = "Non-Color"

    normal_map = next((n for n in nodes if n.type == "NORMAL_MAP"), None)
    if normal_map is None:
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-420, -200)

    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)

    links.new(texture.outputs["Color"], normal_map.inputs["Color"])
    if principled is not None:
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    nodes.active = texture       # the bake writes into whichever node is active
    return texture


def bake_normal(context, low, high, settings):
    """Project high's surface detail onto low as a normal map. Returns the image."""
    scene = context.scene
    size = int(settings.texture_size)

    image_name = low.name + "_Normal"
    image = bpy.data.images.get(image_name)
    if image is None or tuple(image.size) != (size, size):
        if image is not None:
            bpy.data.images.remove(image)
        image = bpy.data.images.new(image_name, size, size, alpha=False,
                                    float_buffer=False, is_data=True)

    material = ensure_material(low, low.name + "_Material")
    wire_normal_map(material, image)

    # Baking is Cycles-only, so borrow the engine and hand it back afterwards.
    previous_engine = scene.render.engine
    previous_samples = getattr(scene.cycles, "samples", None) if hasattr(scene, "cycles") else None
    if scene.render.engine != "CYCLES":
        try:
            scene.render.engine = "CYCLES"
        except TypeError:
            raise RuntimeError("Cycles is not enabled — baking needs it")
    if hasattr(scene, "cycles"):
        scene.cycles.samples = 1      # a normal bake reads geometry, not light

    was_hidden = high.hide_get()
    high.hide_set(False)
    high.hide_render = False

    for obj in context.view_layer.objects:
        obj.select_set(False)
    high.select_set(True)
    low.select_set(True)
    context.view_layer.objects.active = low

    distance = ray_distance_cm(low, settings) / 100.0     # centimetres to metres
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.use_cage = False
    bake.cage_extrusion = distance
    bake.max_ray_distance = distance * 2.0
    bake.margin = max(2, size // 512)
    bake.use_clear = True

    try:
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
    finally:
        high.hide_set(was_hidden)
        scene.render.engine = previous_engine
        if previous_samples is not None:
            scene.cycles.samples = previous_samples

    image.pack()      # keep it inside the .blend so it cannot be lost
    return image


class RETOPO_OT_bake(Operator):
    bl_idname = "retopo.bake"
    bl_label = "Bake Detail"
    bl_description = "Project the sculpt's detail onto the low-poly as a normal map"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def execute(self, context):
        low = context.active_object
        settings = context.scene.retopo

        high = find_source(context, low)
        if high is None:
            self.report({"ERROR"},
                        "Cannot tell which sculpt to bake from. Select the sculpt "
                        "as well, with the low-poly active")
            return {"CANCELLED"}
        if not low.data.uv_layers:
            self.report({"ERROR"}, "%s has no UVs — unwrap it first" % low.name)
            return {"CANCELLED"}

        started = time.time()
        try:
            image = bake_normal(context, low, high, settings)
        except RuntimeError as exc:
            self.report({"ERROR"}, "Bake failed: %s" % exc)
            return {"CANCELLED"}

        self.report({"INFO"}, "%s baked from %s in %.1fs (%d px, %.1f cm rays)"
                    % (image.name, high.name, time.time() - started,
                       image.size[0], ray_distance_cm(low, settings)))
        return {"FINISHED"}


def find_source(context, low):
    """Work out which object is the sculpt this low-poly came from.

    The remesh records it on the object, so the usual case needs no selection at
    all. Failing that, fall back to whatever else the artist has selected.
    """
    recorded = low.get("retopo_source")
    if recorded and recorded in bpy.data.objects:
        return bpy.data.objects[recorded]
    others = [o for o in context.selected_objects if o is not low and o.type == "MESH"]
    return others[0] if len(others) == 1 else None


# --------------------------------------------------------------------------- #
# Step 1 — the remesh operator
# --------------------------------------------------------------------------- #

class Result:
    """What happened to one sculpt, so a batch can report on all of them."""

    __slots__ = ("source", "low", "before", "after", "coverage", "baked", "problem")

    def __init__(self, source):
        self.source = source
        self.low = None
        self.before = len(source.data.polygons)
        self.after = 0
        self.coverage = None
        self.baked = False
        self.problem = None

    @property
    def ok(self):
        return self.low is not None and self.problem is None


def process(context, source, settings, report=None):
    """Run the whole chain on one sculpt: remesh, then unwrap, then bake.

    Everything the buttons do goes through here, so the single-object button and
    the batch cannot drift apart. Never raises — failures land on the Result.
    """
    result = Result(source)

    area = surface_area(source, context.evaluated_depsgraph_get())
    if area <= 0.0:
        result.problem = "no surface area"
        return result

    target = faces_for_quad_size(area, effective_quad_size(settings))

    # Work on a copy so the sculpt is never damaged.
    low = source.copy()
    low.data = source.data.copy()
    low.name = "LP_" + source.name
    low.data.name = "LP_" + source.name
    low["retopo_source"] = source.name      # step 3 reads this to find the sculpt
    for collection in source.users_collection:
        collection.objects.link(low)

    for obj in context.selected_objects:
        obj.select_set(False)
    low.select_set(True)
    context.view_layer.objects.active = low

    try:
        bpy.ops.object.quadriflow_remesh(
            mode="FACES",
            target_faces=target,
            use_mesh_symmetry=settings.use_symmetry,
            use_preserve_sharp=settings.preserve_sharp,
            use_preserve_boundary=True,
            smooth_normals=True,
        )
    except RuntimeError as exc:
        bpy.data.objects.remove(low, do_unlink=True)
        result.problem = "remesh failed (%s)" % exc
        return result

    result.low = low
    result.after = len(low.data.polygons)

    if settings.auto_unwrap:
        try:
            _seams, result.coverage = unwrap_object(low, settings)
        except RuntimeError as exc:
            result.problem = "unwrap failed (%s)" % exc
            return result

        if settings.auto_bake:
            try:
                bake_normal(context, low, source, settings)
                result.baked = True
            except RuntimeError as exc:
                result.problem = "bake failed (%s)" % exc
                return result

    if settings.keep_original:
        source.hide_set(True)
    else:
        bpy.data.objects.remove(source, do_unlink=True)

    return result


def describe(result):
    """One line an artist can read, for the status bar or the batch summary."""
    if not result.ok:
        return "%s: %s" % (result.source.name, result.problem)
    parts = ["%s to %s faces" % (f"{result.before:,}", f"{result.after:,}")]
    if result.coverage is not None:
        parts.append("UVs %.0f%%" % result.coverage)
    if result.baked:
        parts.append("baked")
    return "%s: %s" % (result.low.name, ", ".join(parts))


class RETOPO_OT_remesh(Operator):
    bl_idname = "retopo.remesh"
    bl_label = "Make Low Poly"
    bl_description = "Build a clean quad mesh from the selected sculpt"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def execute(self, context):
        settings = context.scene.retopo
        result = process(context, context.active_object, settings)

        settings.last_report = describe(result)
        if not result.ok:
            self.report({"ERROR"}, settings.last_report)
            return {"CANCELLED"}

        self.report({"INFO"}, settings.last_report)
        return {"FINISHED"}


class RETOPO_OT_batch(Operator):
    bl_idname = "retopo.batch"
    bl_label = "Do All Selected"
    bl_description = ("Run the whole chain over every selected sculpt, one after "
                      "another")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(
            o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        settings = context.scene.retopo
        window = context.window_manager

        # Take the list now: the loop creates new objects and changes selection.
        sculpts = [o for o in context.selected_objects
                   if o.type == "MESH" and not o.name.startswith("LP_")]
        if not sculpts:
            self.report({"WARNING"},
                        "Nothing to do — select the sculpts, not the low-polys")
            return {"CANCELLED"}

        started = time.time()
        results = []
        window.progress_begin(0, len(sculpts))
        try:
            for index, source in enumerate(sculpts):
                window.progress_update(index)
                results.append(process(context, source, settings))
        finally:
            window.progress_end()

        done = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]

        for result in failed:
            self.report({"WARNING"}, describe(result))
        for result in results:
            print("[Retopo Kit] " + describe(result))

        settings.last_report = "%d of %d done in %.0fs" % (
            len(done), len(results), time.time() - started)
        if failed:
            settings.last_report += " — %d failed" % len(failed)

        self.report({"INFO"}, settings.last_report)
        return {"FINISHED"} if done else {"CANCELLED"}


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

class RETOPO_PT_main(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Retopo"
    bl_label = "Retopo Kit"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.retopo
        obj = context.active_object

        layout.prop(settings, "preset")
        row = layout.row()
        row.enabled = settings.preset == "CUSTOM"
        row.prop(settings, "quad_size")

        column = layout.column(align=True)
        column.prop(settings, "use_symmetry")
        column.prop(settings, "preserve_sharp")
        column.prop(settings, "keep_original")

        layout.separator()

        # Show the estimate before they commit to it.
        if obj is not None and obj.type == "MESH":
            depsgraph = context.evaluated_depsgraph_get()
            area = surface_area(obj, depsgraph)
            target = faces_for_quad_size(area, effective_quad_size(settings))
            box = layout.box()
            box.label(text="Surface area: %.2f m2" % area)
            box.label(text="Faces now: %s" % f"{len(obj.data.polygons):,}")
            box.label(text="Aiming for: %s" % f"{target:,}")

        big = layout.column(align=True)
        big.scale_y = 1.5
        big.operator("retopo.remesh", icon="MOD_REMESH")

        selected = sum(1 for o in context.selected_objects
                       if o.type == "MESH" and not o.name.startswith("LP_"))
        row = layout.row()
        row.scale_y = 1.2
        row.enabled = selected > 1
        row.operator("retopo.batch",
                     text="Do All Selected (%d)" % selected if selected > 1
                     else "Do All Selected",
                     icon="DUPLICATE")

        if settings.last_report:
            layout.label(text=settings.last_report, icon="INFO")


class RETOPO_PT_unwrap(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Retopo"
    bl_label = "UVs"
    bl_parent_id = "RETOPO_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.retopo
        obj = context.active_object

        layout.prop(settings, "auto_unwrap")
        row = layout.row(align=True)
        row.prop(settings, "texture_size", expand=True)
        layout.prop(settings, "seam_angle")

        if obj is not None and obj.type == "MESH" and obj.data.uv_layers:
            box = layout.box()
            box.label(text="Map used: %.0f%%" % uv_coverage(obj.data), icon="UV")

        layout.operator("retopo.unwrap", icon="MOD_UVPROJECT")


class RETOPO_PT_bake(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Retopo"
    bl_label = "Detail"
    bl_parent_id = "RETOPO_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.retopo
        obj = context.active_object

        layout.prop(settings, "auto_bake")
        layout.prop(settings, "cage_auto")
        row = layout.row()
        row.enabled = not settings.cage_auto
        row.prop(settings, "cage_distance")

        if obj is not None and obj.type == "MESH":
            source = find_source(context, obj)
            box = layout.box()
            box.label(text="Sculpt: %s" % (source.name if source else "not found"),
                      icon="OUTLINER_OB_MESH" if source else "ERROR")
            box.label(text="Rays travel: %.1f cm" % ray_distance_cm(obj, settings))

        layout.operator("retopo.bake", icon="RENDER_STILL")


CLASSES = (RETOPO_Settings,
           RETOPO_OT_remesh, RETOPO_OT_batch, RETOPO_OT_unwrap, RETOPO_OT_bake,
           RETOPO_PT_main, RETOPO_PT_unwrap, RETOPO_PT_bake)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.retopo = PointerProperty(type=RETOPO_Settings)


def unregister():
    del bpy.types.Scene.retopo
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
