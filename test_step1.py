"""Prove step 1 works: blender --background --factory-startup --python test_step1.py"""
import os, sys, bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retopo_kit
retopo_kit.register()

# A stand-in for a sculpt: a dense, bumpy sphere.
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=64, ring_count=32)
sculpt = bpy.context.active_object
sculpt.name = "Sculpt"
bpy.ops.object.modifier_add(type="SUBSURF")
sculpt.modifiers["Subdivision"].levels = 2
bpy.ops.object.modifier_apply(modifier="Subdivision")
print("SOURCE FACES:", len(sculpt.data.polygons))

s = bpy.context.scene.retopo
s.preset = "PROP"          # 2 cm quads
result = bpy.ops.retopo.remesh()
print("RESULT:", result)

low = bpy.data.objects.get("LP_Sculpt")
print("LOW POLY EXISTS:", low is not None)
if low:
    print("LOW POLY FACES:", len(low.data.polygons))
    quads = sum(1 for p in low.data.polygons if len(p.vertices) == 4)
    print("QUAD PERCENT: %.1f" % (100.0 * quads / max(len(low.data.polygons), 1)))
print("SCULPT SURVIVED:", "Sculpt" in bpy.data.objects)
print("SCULPT FACES UNCHANGED:", len(bpy.data.objects["Sculpt"].data.polygons))
