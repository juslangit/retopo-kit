# SPDX-License-Identifier: GPL-3.0-or-later
"""Retopo Kit — sculpt to game-ready.

Step 1, remesh: Blender's own Quadriflow asks for a target face count, which nobody
knows in advance. This asks how big each quad should be in centimetres, which is a
question an artist can answer, and works the count out from the surface area.

Step 2, unwrap: the low-poly gets UVs immediately, sized for the texture it will be
baked into, because nothing further in the chain can happen without them.

The sculpt is never modified. The result is a new object named LP_<name>.
"""

bl_info = {
    "name": "Retopo Kit",
    "author": "Luqman Hakeem",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar (N) > Retopo",
    "description": "Sculpt to game-ready: remesh and unwrap, with baking and LODs to come.",
    "category": "Mesh",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup


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
# Step 1 — the remesh operator
# --------------------------------------------------------------------------- #

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
        source = context.active_object
        depsgraph = context.evaluated_depsgraph_get()

        area = surface_area(source, depsgraph)
        if area <= 0.0:
            self.report({"ERROR"}, "That mesh has no surface area")
            return {"CANCELLED"}

        quad_size = effective_quad_size(settings)
        target = faces_for_quad_size(area, quad_size)
        before = len(source.data.polygons)

        # Work on a copy so the sculpt is never damaged.
        low = source.copy()
        low.data = source.data.copy()
        low.name = "LP_" + source.name
        low.data.name = "LP_" + source.name
        for collection in source.users_collection:
            collection.objects.link(low)

        for obj in context.view_layer.objects:
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
            source.select_set(True)
            context.view_layer.objects.active = source
            self.report({"ERROR"}, "Remesh failed: %s" % exc)
            return {"CANCELLED"}

        after = len(low.data.polygons)

        unwrapped = ""
        if settings.auto_unwrap:
            try:
                _seams, coverage = unwrap_object(low, settings)
                unwrapped = ", UVs %.0f%% packed" % coverage
            except RuntimeError as exc:
                self.report({"WARNING"}, "Remeshed, but the unwrap failed: %s" % exc)

        if settings.keep_original:
            source.hide_set(True)
        else:
            bpy.data.objects.remove(source, do_unlink=True)

        self.report(
            {"INFO"},
            "%s: %s faces to %s (%.1f cm quads, %.2f m2)%s"
            % (low.name, f"{before:,}", f"{after:,}", quad_size, area, unwrapped))
        return {"FINISHED"}


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

        big = layout.column()
        big.scale_y = 1.5
        big.operator("retopo.remesh", icon="MOD_REMESH")


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


CLASSES = (RETOPO_Settings, RETOPO_OT_remesh, RETOPO_OT_unwrap,
           RETOPO_PT_main, RETOPO_PT_unwrap)


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
