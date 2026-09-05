# Retopo Kit

One press from sculpt to game-ready.

Blender ships a good automatic quad remesher (`Object ▸ Quadriflow Remesh`) and then
stops: no UVs, no baked normal map, no LODs, one object at a time — and it asks for
a target face count that nobody knows in advance.

Retopo Kit uses that remesher as its engine and does the rest of the chain.

## Status

**All five steps work.** Sculpt to game-ready in one press.

| Step | What it does | Status |
|---|---|---|
| 1 | Remesh, asking for quad size in cm instead of a face count | ✅ done |
| 2 | Automatic UV unwrap on the low-poly | ✅ done |
| 3 | Bake the sculpt's detail into a normal map | ✅ done |
| 4 | Run the whole chain over a selection, not one object | ✅ done |
| 5 | Generate LODs with Unreal's naming | ✅ done |

## Step 1 — remesh by quad size

Blender's remesh asks how many faces you want. This asks **how wide each quad should
be, in centimetres**, and works the face count out from the model's surface area:

```
faces = surface area ÷ (quad size)²
```

3 m² of surface at 2 cm quads is roughly 7,500 faces. The panel shows the estimate
before you commit to it.

Presets: **Hero prop** 0.8 cm · **Game prop** 2 cm · **Background** 6 cm

The sculpt is never modified. You get a new object named `LP_<name>`, and the
original is hidden rather than deleted.

## Step 2 — unwrap for the bake

The low-poly gets UVs the moment it is made, because nothing further in the chain
works without them. You choose the **texture size** it will be baked into — 1K, 2K
or 4K — and that sets how much space is left between islands, so the normal bake
cannot bleed from one island into its neighbour.

The cuts are written back as real seams, so you can see where they landed and move
them if you disagree. The panel reports how much of the map the islands fill;
wasted space there is wasted texture resolution later.

## Step 3 — bake the detail down

Your low-poly is smooth and dumb. The bake fires a ray out from every pixel of its
surface, finds where that ray hits the sculpt, and records which way the sculpt was
facing at that point. Stored as an image, it makes the low-poly *render* as though
it still had all the sculpt's detail.

The thing that goes wrong is ray distance: too short and the rays miss the sculpt,
leaving black patches; too long and they punch through and hit the far side of the
model. Retopo Kit works it out from the model's own size — two percent of its
bounding box diagonal — and shows you the figure in centimetres before you bake.

The result is packed into the .blend so it cannot be lost, and wired into the
material through a Normal Map node, so the detail is visible immediately rather
than being an image nobody ever sees.

Baking needs Cycles. The add-on borrows the render engine for the bake and hands it
back afterwards.

## Step 4 — do a whole selection

Select any number of sculpts and press **Do All Selected**. Each one gets remeshed,
unwrapped and baked in turn, with its own normal map.

One bad object does not stop the run. It is reported and the batch carries on, so
a folder of forty props does not fail on number seven and leave you guessing.
Low-polys are skipped, so running it twice cannot produce `LP_LP_Rock`.

Every button goes through the same code path as the batch, so the single-object
case and the forty-object case cannot behave differently.

## Step 5 — distance versions

`LP_Rock_LOD0`, `LP_Rock_LOD1`, `LP_Rock_LOD2` — the naming Unreal reads.

Each level is **reduced from the one above, not rebuilt from the sculpt.** That is
the whole point: reducing the existing mesh keeps its UVs, so every level shares the
one normal map you already baked. Remeshing each level would give each its own UVs
and need its own texture, which is not how LODs work.

Counts are shown in triangles rather than faces, because decimating turns quads into
triangles — 7,690 quads become 15,380 triangles, and halving that gives 7,690
triangles, the same number in a different unit. Triangles are what the engine draws.

The reduced levels are hidden after building, since they sit exactly on top of LOD0.

## Sculpts that Quadriflow refuses

Quadriflow will not touch a mesh with non-manifold geometry — edges shared by three
or more faces. Real sculpts have these constantly, and it takes only three of them
in an 85,000-face model to make it refuse the lot. Open boundaries are fine; it is
three-face edges it rejects.

When that happens Retopo Kit remeshes with voxels instead, driven by the same quad
size, so you still get a usable low-poly. The quads are laid out less neatly than
Quadriflow would manage, and the report says so plainly:

```
LP_Thief_LOD0: 85,319 to 4,404 faces, UVs 58%, baked, voxels (not watertight), 3 LODs
```

The panel warns you before you press anything, and you can switch the fallback off
if you would rather fix the mesh than accept voxel topology.

## Testing on a real sculpt

Blender publishes free sculpt demo files, which are far better test subjects than
primitives:

```bash
curl -O https://download.blender.org/demo/sculpt_mode/01_sculpt_grab_silhouette.blend
```

Everything on this page was verified against that file's character sculpt, not only
against spheres.

## Install

Build the zip, then install that — **not** the loose `__init__.py`, which Blender
registers under the wrong name and never shows in the sidebar:

```bash
./build.sh          # writes dist/retopo_kit-<version>.zip
```

Blender 4.2+ — Edit ▸ Preferences ▸ Get Extensions ▸ ⌄ ▸ Install from Disk
Blender 3.6–4.1 — Edit ▸ Preferences ▸ Add-ons ▸ Install

Then press **N** in the 3D viewport and open the **Retopo** tab.

Blender 3.6 or newer. Verified installing and enabling on Blender 5.2.1 LTS.

## Test

```bash
blender --background --factory-startup --python test_step1.py
```

`--factory-startup` matters: without it Blender loads your installed copy of the
add-on, which collides with the source being tested.

## Licence

GPL-3.0-or-later, as required for anything that imports `bpy`.
