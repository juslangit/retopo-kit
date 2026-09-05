# SPDX-License-Identifier: GPL-3.0-or-later
"""Retopo Kit — step 1: remesh with a quad size you can actually reason about.

Blender's own Quadriflow asks you for a target face count, which nobody knows in
advance. This asks how big you want each quad to be in centimetres, which is a
question an artist can answer, and works the face count out from the surface area.

It also never touches your sculpt: the result is a new object named LP_<name>.
"""

bl_info = {
    "name": "Retopo Kit",
    "author": "Luqman Hakeem",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar (N) > Retopo",
    "description": "Sculpt to game-ready: remesh, and later UVs, bakes and LODs.",
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
        name="Quad Size",
        description="Roughly how wide each quad should be, in centimetres",
        default=2.0, min=0.05, max=100.0, soft_max=20.0, unit="NONE")
    preset: EnumProperty(
        name="Preset", default="CUSTOM",
        items=[
            ("HERO", "Hero prop", "Fine quads for something the camera gets close to"),
            ("PROP", "Game prop", "A sensible middle for most props"),
            ("BACKGROUND", "Background", "Coarse quads for things seen from far away"),
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


PRESET_SIZES = {"HERO": 0.8, "PROP": 2.0, "BACKGROUND": 6.0}


def effective_quad_size(settings):
    return PRESET_SIZES.get(settings.preset, settings.quad_size)


# --------------------------------------------------------------------------- #
# The operator
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

        if settings.keep_original:
            source.hide_set(True)
        else:
            bpy.data.objects.remove(source, do_unlink=True)

        self.report(
            {"INFO"},
            "%s: %s faces to %s (%.1f cm quads, %.2f m2)"
            % (low.name, f"{before:,}", f"{after:,}", quad_size, area))
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


CLASSES = (RETOPO_Settings, RETOPO_OT_remesh, RETOPO_PT_main)


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
