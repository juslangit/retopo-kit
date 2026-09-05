# Retopo Kit

One press from sculpt to game-ready.

Blender ships a good automatic quad remesher (`Object ▸ Quadriflow Remesh`) and then
stops: no UVs, no baked normal map, no LODs, one object at a time — and it asks for
a target face count that nobody knows in advance.

Retopo Kit uses that remesher as its engine and does the rest of the chain.

## Status

**In development.** Step 1 of 5 works.

| Step | What it does | Status |
|---|---|---|
| 1 | Remesh, asking for quad size in cm instead of a face count | ✅ done |
| 2 | Automatic UV unwrap on the low-poly | planned |
| 3 | Bake the sculpt's detail into a normal map | planned |
| 4 | Run the whole chain over a selection, not one object | planned |
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

## Install

Edit ▸ Preferences ▸ Add-ons ▸ Install, choose `retopo_kit/__init__.py`, enable it.
Press **N** in the 3D viewport and open the **Retopo** tab.

Blender 3.6 or newer. Developed against Blender 5.2.1 LTS.

## Test

```bash
blender --background --factory-startup --python test_step1.py
```

`--factory-startup` matters: without it Blender loads your installed copy of the
add-on, which collides with the source being tested.

## Licence

GPL-3.0-or-later, as required for anything that imports `bpy`.
