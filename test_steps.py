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


# --- step 3: the bake -----------------------------------------------------
import time
bpy.ops.preferences.addon_enable(module="cycles")   # off under --factory-startup

sculpt("Bumpy")
s = bpy.context.scene.retopo
high = bpy.context.active_object
# give the sculpt real surface detail, so a flat bake would be obviously wrong
bpy.ops.object.modifier_add(type="DISPLACE")
tex = bpy.data.textures.new("Bumps", type="CLOUDS")
tex.noise_scale = 0.15
high.modifiers["Displace"].texture = tex
high.modifiers["Displace"].strength = 0.08
bpy.ops.object.modifier_apply(modifier="Displace")

s.preset = "PROP"
s.auto_unwrap = True
s.auto_bake = False
s.texture_size = "1024"
bpy.ops.retopo.remesh()
low = bpy.data.objects["LP_Bumpy"]
check(low.get("retopo_source") == "Bumpy", "low-poly remembers which sculpt it came from")

bpy.context.view_layer.objects.active = low
engine_before = bpy.context.scene.render.engine
started = time.time()
result = bpy.ops.retopo.bake()
check(result == {"FINISHED"}, "bake finished in %.1fs" % (time.time() - started))

img = bpy.data.images.get("LP_Bumpy_Normal")
check(img is not None, "normal map image was created")
if img:
    check(tuple(img.size) == (1024, 1024), "image is the requested size %s" % (tuple(img.size),))
    px = list(img.pixels)
    # A flat normal map is uniform lilac (0.5, 0.5, 1.0). Real detail varies.
    reds = px[0::4]
    spread = max(reds) - min(reds)
    check(spread > 0.05, "the map carries real detail, not a flat surface (spread %.2f)" % spread)
    check(img.colorspace_settings.name == "Non-Color", "image is Non-Color, as a normal map must be")
    check(img.packed_file is not None, "image is packed into the blend")

mat = low.data.materials[0] if low.data.materials else None
check(mat is not None, "low-poly got a material")
if mat:
    kinds = [n.type for n in mat.node_tree.nodes]
    check("NORMAL_MAP" in kinds, "a Normal Map node was created")
    linked = any(l.to_node.type == "BSDF_PRINCIPLED" and l.to_socket.name == "Normal"
                 for l in mat.node_tree.links)
    check(linked, "the normal map is wired into the shader, so it is actually visible")

check(bpy.context.scene.render.engine == engine_before,
      "render engine handed back (%s)" % bpy.context.scene.render.engine)
check(bpy.data.objects["Bumpy"].hide_get(), "the sculpt was hidden again after baking")

# --- step 4: the batch ----------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake = "PROP", True, False

names = ["Rock", "Barrel", "Crate"]
for i, name in enumerate(names):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, segments=32, ring_count=16,
                                         location=(i * 2.0, 0, 0))
    bpy.context.active_object.name = name

for obj in bpy.context.view_layer.objects:
    obj.select_set(obj.name in names)
bpy.context.view_layer.objects.active = bpy.data.objects["Rock"]

result = bpy.ops.retopo.batch()
check(result == {"FINISHED"}, "batch finished")
made = [n for n in names if ("LP_" + n) in bpy.data.objects]
check(len(made) == 3, "all three were processed (%d of 3)" % len(made))
check(all(bpy.data.objects["LP_" + n].data.uv_layers for n in names),
      "every low-poly got UVs")
check(all(bpy.data.objects[n].hide_get() for n in names), "every sculpt was hidden")
check("3 of 3 done" in s.last_report, "summary reads '%s'" % s.last_report)

# a broken object must not stop the rest of the batch
bpy.ops.wm.read_factory_settings(use_empty=True)
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake = "PROP", False, False
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, segments=32, ring_count=16)
bpy.context.active_object.name = "Good"
empty_mesh = bpy.data.meshes.new("Empty")
broken = bpy.data.objects.new("Broken", empty_mesh)   # no faces at all
bpy.context.scene.collection.objects.link(broken)
bpy.context.view_layer.update()      # the new object is not selectable until this
broken.select_set(True)
bpy.data.objects["Good"].select_set(True)
bpy.context.view_layer.objects.active = broken
bpy.ops.retopo.batch()
check("LP_Good" in bpy.data.objects, "a broken object did not stop the batch")
check("failed" in s.last_report, "the failure was reported ('%s')" % s.last_report)

# low-polys are skipped, so running twice does not make LP_LP_
for obj in bpy.context.view_layer.objects:
    obj.select_set(True)
bpy.ops.retopo.batch()
check("LP_LP_Good" not in bpy.data.objects, "low-polys are not re-processed")

# --- step 5: LODs ---------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake, s.auto_lods = "PROP", True, False, False
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=48, ring_count=24)
bpy.context.active_object.name = "Statue"
bpy.ops.retopo.remesh()

low = bpy.data.objects["LP_Statue"]
bpy.context.view_layer.objects.active = low
s.lod_count, s.lod_ratio = "2", 0.5
check(bpy.ops.retopo.lods() == {"FINISHED"}, "LODs built")

names = ["LP_Statue_LOD0", "LP_Statue_LOD1", "LP_Statue_LOD2"]
check(all(n in bpy.data.objects for n in names),
      "named the way Unreal reads them: %s" % ", ".join(names))

def triangles(obj):
    # Decimate turns quads into triangles, so face counts are not comparable
    # across levels. Triangles are what the engine draws, and what LOD ratios
    # are actually measured in.
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)

counts = [triangles(bpy.data.objects[n]) for n in names]
check(counts[0] > counts[1] > counts[2], "each level is lighter (%s tris)" % counts)
check(abs(counts[1] / counts[0] - 0.5) < 0.15,
      "LOD1 is roughly half of LOD0 (%.2f)" % (counts[1] / counts[0]))

check(all(bpy.data.objects[n].data.uv_layers for n in names),
      "every level kept its UVs, so they can share one texture")
mats = [bpy.data.objects[n].data.materials[0] if bpy.data.objects[n].data.materials
        else None for n in names]
check(len(set(id(m) for m in mats)) == 1, "every level shares the same material")
check(all(bpy.data.objects[n].hide_get() for n in names[1:]),
      "the reduced levels are hidden so they do not obscure LOD0")
check(not bpy.data.objects["LP_Statue_LOD0"].modifiers, "no leftover modifier stack")

# running the chain end to end, everything on
bpy.ops.wm.read_factory_settings(use_empty=True)
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake, s.auto_lods = "PROP", True, True, True
s.texture_size, s.lod_count = "1024", "2"
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=48, ring_count=24)
bpy.context.active_object.name = "Whole"
check(bpy.ops.retopo.remesh() == {"FINISHED"}, "the whole chain runs in one press")
check("LP_Whole_LOD0" in bpy.data.objects, "chain produced LOD0")
check("LP_Whole_LOD2" in bpy.data.objects, "chain produced LOD2")
check(bpy.data.images.get("LP_Whole_Normal") is not None, "chain produced the normal map")
check("LODs" in s.last_report, "the summary mentions every stage: '%s'" % s.last_report)

# --- meshes Quadriflow refuses, which real sculpts often are ---------------
def nonmanifold_sphere(name="Messy"):
    """A closed sphere with one extra face welded onto an existing edge.

    That single addition gives three edges with three faces each, which is all
    it takes for Quadriflow to refuse the whole mesh. Deleting faces would not
    do it — Quadriflow tolerates open boundaries, it is three-face edges it
    will not touch. This mirrors what the Blender demo sculpt does.
    """
    import bmesh as _bm
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=96, ring_count=48)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.modifier_add(type="SUBSURF")
    obj.modifiers["Subdivision"].levels = 1
    bpy.ops.object.modifier_apply(modifier="Subdivision")
    bm = _bm.new(); bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table()
    edge = bm.edges[10]
    far = max(bm.verts, key=lambda v: (v.co - edge.verts[0].co).length)
    bm.faces.new((edge.verts[0], edge.verts[1], far))
    bm.to_mesh(obj.data); bm.free(); obj.data.update()
    return obj

obj = nonmanifold_sphere()
bad = retopo_kit.nonmanifold_edges(obj.data)
check(bad > 0, "the test mesh really is non-manifold (%d edges)" % bad)

s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake, s.auto_lods = "BACKGROUND", True, False, False
s.voxel_fallback = True
before = len(obj.data.polygons)
check(bpy.ops.retopo.remesh() == {"FINISHED"},
      "a mesh Quadriflow refuses still produces a low-poly")
low = bpy.data.objects.get("LP_Messy")
check(low is not None and len(low.data.polygons) < before / 2,
      "the fallback reduced it (%s to %s faces)"
      % (f"{before:,}", f"{len(low.data.polygons):,}" if low else "none"))
check("voxels" in s.last_report, "the report says voxels were used: '%s'" % s.last_report)

# with the fallback off it must fail loudly, not silently pass the sculpt through
nonmanifold_sphere("Messy2")
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake, s.auto_lods = "PROP", False, False, False
s.voxel_fallback = False
try:
    outcome = bpy.ops.retopo.remesh()
    refused = outcome == {"CANCELLED"}
except RuntimeError as exc:
    refused = "not watertight" in str(exc)
check(refused, "without the fallback it refuses instead of faking a result")
check("LP_Messy2" not in bpy.data.objects, "and leaves no half-made object behind")

# the bake must not inherit a vertex-colour target from the file
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.bake.target = "VERTEX_COLORS"
s = bpy.context.scene.retopo
s.preset, s.auto_unwrap, s.auto_bake, s.auto_lods = "PROP", True, True, False
s.texture_size, s.voxel_fallback = "1024", True
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=48, ring_count=24)
bpy.context.active_object.name = "VC"
check(bpy.ops.retopo.remesh() == {"FINISHED"},
      "baking works even when the file was set to vertex colours")

print("\n%d check(s), %d failure(s)" % (checks, len(failures)))
if failures:
    for f in failures: print("FAILED: " + f)
    sys.exit(1)
print("ALL CHECKS PASSED")
