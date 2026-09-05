"""blender --background --factory-startup --python test_steps.py"""
import os, sys, bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retopo_kit
retopo_kit.register()

failures, checks = [], 0
def check(ok, msg):
    global checks
    checks += 1
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    if not ok: failures.append(msg)

def sculpt(name="Sculpt"):
    # Resetting the file replaces the scene, so any settings reference held from
    # before this call is pointing at a dead datablock. Always re-fetch after.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=64, ring_count=32)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.modifier_add(type="SUBSURF")
    obj.modifiers["Subdivision"].levels = 2
    bpy.ops.object.modifier_apply(modifier="Subdivision")
    return obj

# --- step 1 ---------------------------------------------------------------
src = sculpt()
before = len(src.data.polygons)
s = bpy.context.scene.retopo
s.preset = "PROP"
s.auto_unwrap = False
check(bpy.ops.retopo.remesh() == {"FINISHED"}, "remesh finished")
low = bpy.data.objects.get("LP_Sculpt")
check(low is not None, "LP_Sculpt was created")
check(len(low.data.polygons) < before / 5, "face count dropped a lot (%s to %s)"
      % (f"{before:,}", f"{len(low.data.polygons):,}"))
quads = sum(1 for p in low.data.polygons if len(p.vertices) == 4)
check(quads / len(low.data.polygons) > 0.95, "result is quads (%.0f%%)"
      % (100 * quads / len(low.data.polygons)))
check(len(bpy.data.objects["Sculpt"].data.polygons) == before, "sculpt untouched")

# quad size actually controls density
sculpt()
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap = "BACKGROUND", False
bpy.ops.retopo.remesh()
coarse = len(bpy.data.objects["LP_Sculpt"].data.polygons)
sculpt()
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap = "HERO", False
bpy.ops.retopo.remesh()
fine = len(bpy.data.objects["LP_Sculpt"].data.polygons)
check(fine > coarse * 3, "smaller quads give more faces (hero %s vs background %s)"
      % (f"{fine:,}", f"{coarse:,}"))

# --- step 2 ---------------------------------------------------------------
sculpt()
s = bpy.context.scene.retopo
s.preset = "PROP"
s.auto_unwrap = True
s.texture_size = "2048"
bpy.ops.retopo.remesh()
low = bpy.data.objects["LP_Sculpt"]
check(len(low.data.uv_layers) > 0, "remesh produced UVs automatically")
coverage = retopo_kit.uv_coverage(low.data)
check(coverage > 30.0, "UV islands fill the map (%.0f%%)" % coverage)
check(coverage <= 100.0, "coverage cannot exceed 100%% (%.1f)" % coverage)
check(any(e.use_seam for e in low.data.edges), "seams are marked so they can be edited")

# unwrapping on its own
sculpt("Plain")
s = bpy.context.scene.retopo
bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.active_object
bpy.context.view_layer.objects.active = cube
check(bpy.ops.retopo.unwrap() == {"FINISHED"}, "unwrap runs on its own")
check(len(cube.data.uv_layers) > 0, "cube got UVs")

# refuses a mesh that has not been remeshed
sculpt("Dense")
s = bpy.context.scene.retopo
bpy.ops.object.modifier_add(type="SUBSURF")
bpy.context.active_object.modifiers["Subdivision"].levels = 2
bpy.ops.object.modifier_apply(modifier="Subdivision")
try:
    result = bpy.ops.retopo.unwrap()
    refused = result == {"CANCELLED"}
except RuntimeError as exc:
    refused = "remesh it before" in str(exc)
check(refused, "refuses to unwrap a mesh that is still dense")

print("\n%d check(s), %d failure(s)" % (checks, len(failures)))
if failures:
    sys.exit(1)
print("ALL CHECKS PASSED")
