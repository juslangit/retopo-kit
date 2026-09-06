---
doc: store-listing
project: retopology
updated: 2026-09-06
---

# Store listing — Retopo Kit v1.0.0

Paste-ready copy for Superhive Market (formerly Blender Market). Nothing here
claims anything the add-on has not been observed doing on a real sculpt.

---

## PRODUCT NAME

Retopo Kit

## TAGLINE

One press from sculpt to game-ready.

## SHORT DESCRIPTION

Retopo Kit takes a finished sculpt and gives you back a low-poly with clean quads,
UVs, a baked normal map and LODs — for one object or forty, without leaving Blender
and without touching your sculpt.

---

## FULL DESCRIPTION

### Blender stops after the first step

`Object ▸ Quadriflow Remesh` gives you quads and then abandons you. No UVs, no baked
detail, no LODs, one object at a time — and it asks for a target face count, which
nobody can answer in advance.

So you guess a number, unwrap by hand, set up a bake, get the ray distance wrong,
and do all of it again for the next prop.

### The whole chain, one press

**Remesh.** Retopo Kit asks how wide each quad should be, in centimetres, and works
the face count out from the surface area. "2 cm quads" is a question an artist can
answer. "7,500 faces" is not.

**Unwrap.** UVs immediately, with the island margin set from the texture size you
are baking into, so the bake cannot bleed between islands. The cuts are written back
as real seams, so you can see them and move them.

**Bake.** The sculpt's detail projected onto the low-poly as a normal map. Ray
distance is worked out from the model's own bounding box, because that is the single
setting that produces black patches when too short and punch-through when too long.
The result is packed into your .blend and wired through a Normal Map node, so it is
visible rather than an image nobody hooked up.

**Batch.** Do it to a whole selection. One bad object is reported and the run
continues, so forty props do not die on number seven.

**LODs.** `LP_Rock_LOD0/1/2`, the naming Unreal reads. Each level is reduced from the
one above rather than rebuilt, so every level shares the one baked normal map.

### It works on messy sculpts

Quadriflow refuses any mesh with non-manifold geometry, and real sculpts are full of
it — three bad edges in an 85,000-face character are enough for it to refuse the
whole model. Blender gives you no useful explanation when this happens.

Retopo Kit tells you before you press anything, and falls back to voxel remeshing so
you still get a usable result. It says plainly in the report when it has done so.

### Your sculpt is never touched

Everything happens on a copy named `LP_<name>`. Your sculpt is hidden, not modified,
not renamed, not re-pivoted.

---

## WHAT IT DOES NOT DO

- It does not write a new remeshing algorithm. It drives Blender's Quadriflow, and
  falls back to voxels when Quadriflow refuses. If you need best-in-class quad flow
  on difficult organic shapes, Quad Remesher's algorithm is better than Blender's,
  and costs five times more.
- Blender's Quadriflow is not deterministic — the same sculpt can return different
  face counts run to run. Retopo Kit cannot fix that; it happens inside Blender.
- It does not hand-place edge loops. That is RetopoFlow's job.
- No PBR baking beyond normals in 1.0.

---

## REQUIREMENTS

Blender 3.6 or newer, verified on 5.2.1 LTS. Baking uses Cycles, which ships with
Blender. No external dependencies.

---

## WHY IT COSTS WHAT IT COSTS

| | Does | Price |
|---|---|---|
| Blender's Quadriflow | remesh only | free |
| Quad Remesher | remesh, better algorithm | $139.90 |
| Retopo Kit | remesh, UVs, bake, batch, LODs | $29 |

Quad Remesher does step one better. Retopo Kit does all five.

---

## PRICE

**$29.** At Superhive's default 70% commission that is $20.30 per sale.

Launch at 25% off for two weeks to gather the first reviews.

Do not go below $19 — under that the listing reads as a weekend script. Do not go
above $39 — buyers start expecting Quad Remesher's algorithm quality, which this
does not have and does not claim.

---

## SCREENSHOT SHOT LIST

Shoot all five from `testdata/RESULT_thief.blend`, which already has a real result in
it. Blender's default dark theme, same window size throughout.

1. **The panel beside a finished result.** Low-poly in wireframe next to the sculpt.
   This is the thumbnail — it must say "tool", not "preset pack".
2. **The face count.** Sculpt at 85,319 beside the low-poly at 4,404, both visible.
3. **The normal map doing its job.** Material Preview: the low-poly looking like the
   sculpt. Side by side with the flat-shaded version if you can fit it.
4. **The warning.** The panel showing "open edges — will use voxels" on a messy
   sculpt. This is the differentiator; competitors just fail.
5. **The batch.** Eight props selected, "Do All Selected (8)", and the summary line
   afterwards.

---

## 60-SECOND DEMO SCRIPT

Captions, no voiceover. Store videos are watched with the sound off.

**0:00–0:10** — A finished sculpt rotating. Caption: *"Now make it game-ready."*
**0:10–0:18** — Fast cuts of the manual way: guessing a face count, unwrapping,
setting up a bake. Caption: *"The part nobody enjoys."*
**0:18–0:26** — Open the Retopo tab, choose Game prop, press the button.
**0:26–0:36** — The result appears. Wireframe on. Caption: *"85,319 to 4,404. Quads,
UVs, normal map, three LODs."*
**0:36–0:44** — Material Preview: the low-poly carrying the sculpt's detail.
Caption: *"The detail is baked in."*
**0:44–0:52** — Select eight props, press Do All Selected, show the folder of results.
Caption: *"Or do forty."*
**0:52–1:00** — Back to the sculpt, untouched. Caption: *"Your sculpt never changed."*
End card: name, Blender version, price.

---

## LAUNCH ORDER

1. Shoot the five screenshots and the video from `RESULT_thief.blend`
2. Apply to Superhive as a creator — they review before you can list, so start this
   while editing the video
3. Set up Gumroad or Payhip the same week as a backup storefront
4. Post one place per day, leading with the video every time: Blender Artists
   released-add-ons section, BlenderNation tip, r/blenderhelp and r/unrealengine,
   Unreal Slackers Discord, #b3d on X, LinkedIn, Behance
5. Answer every question within a day — that is most of what converts a viewer

---

## HONESTY NOTE

Two claims in this listing are limits rather than features, and both are stated on
purpose: the algorithm is Blender's, not ours, and it is not deterministic. Saying so
costs a few sales and prevents the refunds and one-star reviews that come from
buyers discovering it themselves.
