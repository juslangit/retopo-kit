# Retopo Kit

One press from sculpt to game-ready.

Blender ships a good automatic quad remesher (`Object ▸ Quadriflow Remesh`) and then
stops: no UVs, no baked normal map, no LODs, one object at a time — and it asks for
a target face count that nobody knows in advance.

Retopo Kit uses that remesher as its engine and does the rest of the chain.

## Status

**In development.** Steps 1 to 4 of 5 work.

| Step | What it does | Status |
|---|---|---|
| 1 | Remesh, asking for quad size in cm instead of a face count | ✅ done |
| 2 | Automatic UV unwrap on the low-poly | ✅ done |
| 3 | Bake the sculpt's detail into a normal map | ✅ done |
| 4 | Run the whole chain over a selection, not one object | ✅ done |
| 5 | Generate LODs with Unreal's naming | planned |

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
