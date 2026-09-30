# VS Code / GitHub Copilot Handoff
## Repository: `jeedee23/DXF2FREECAD2STEP`

## 1. Objective
Build a reliable Windows/FreeCAD conversion workflow that takes an offered DXF file, interprets its layers as components, creates the corresponding FreeCAD model, assigns/preserves material information, and exports the complete result to STEP.

The intended flow is:

`DXF -> inspect/analyse -> layer/component mapping -> FreeCAD document -> assign material + appearance -> STEP export -> round-trip verification`

The repository is currently effectively greenfield, so establish a clean project structure rather than placing everything in one macro.

---

## 2. Core user requirement
For each supplied DXF:

1. Read the DXF without modifying the source file.
2. Every DXF **layer becomes a FreeCAD component** (`App::Part` is preferred unless another FreeCAD container is demonstrably better for STEP export).
3. Geometry belonging to a layer must remain under that component.
4. Convert the geometry into valid FreeCAD BRep/Part geometry wherever possible.
5. Preserve exact layer/component names.
6. Preserve or explicitly map **materials**.
7. Preserve useful appearance information, especially color.
8. Save an `.FCStd` file.
9. Export one complete `.step` / `.stp` file.
10. Re-import the exported STEP into a fresh FreeCAD document and verify the result.

Do not report success merely because a STEP file was written. Success means the STEP can be re-opened and the expected geometry and component identity are still present.

---

## 3. Important distinction: material vs color
A DXF layer normally gives us layer identity and often color/line properties, but **does not guarantee physical material metadata**.

Therefore:

- Never silently assume that an AutoCAD color means aluminium, steel, stainless steel, etc.
- If material information is explicitly present in DXF metadata/XDATA/block attributes/layer naming, extract it.
- Otherwise use an explicit sidecar job/config file mapping layer -> material.
- In FreeCAD assign both:
  - the physical material designation/properties where the installed FreeCAD version supports them;
  - the visual color/appearance separately.

STEP material serialization must be tested against the installed FreeCAD/OCCT version. AP242 should be preferred if supported because product structure, names and presentation data are more suitable for this workflow.

**Critical acceptance rule:** if FreeCAD can preserve names and colors in STEP but cannot reliably serialize/re-import physical material properties, do not hide this limitation. Export a companion material manifest and mark the STEP material test as failed/partial. The program must never equate color preservation with material preservation.

---

## 4. Recommended repository structure

```text
DXF2FREECAD2STEP/
|-- README.md
|-- pyproject.toml
|-- requirements-dev.txt
|-- src/
|   `-- dxf2freecad2step/
|       |-- __init__.py
|       |-- cli.py
|       |-- dxf_inspector.py
|       |-- layer_mapper.py
|       |-- geometry_builder.py
|       |-- material_mapper.py
|       |-- freecad_builder.py
|       |-- step_exporter.py
|       |-- verifier.py
|       `-- reporting.py
|-- scripts/
|   |-- convert_dxf.py
|   |-- inspect_dxf.py
|   `-- verify_step.py
|-- jobs/
|   |-- README.md
|   `-- example_job.json
|-- tests/
|   |-- test_dxf_inspector.py
|   |-- test_layer_mapping.py
|   |-- test_material_mapping.py
|   `-- fixtures/
|-- output/
`-- docs/
    `-- DESIGN.md
```

Use `ezdxf` for DXF inspection because it gives much better access to layers, blocks, entity types, true color, XDATA, INSERTs, Z coordinates, etc. Use FreeCAD/Part for actual solid/BRep construction and STEP export.

Keep DXF parsing logic testable outside FreeCAD whenever possible.

---

## 5. Two-stage workflow

### Stage A - Inspect the offered DXF
Create an inspector that produces a JSON report before conversion.

Report at minimum:

- file path and SHA-256;
- DXF version;
- `$INSUNITS`;
- modelspace extents/bounding box;
- all layer names;
- layer visibility/frozen state;
- ACI color and true color if present;
- lineweight/linetype where useful;
- entity count per layer and per entity type;
- blocks and INSERT references;
- whether geometry is 2D or contains meaningful Z values;
- number of open versus closed polylines;
- 3DFACE / MESH / POLYFACE / ACIS/3DSOLID entities if present;
- XDATA and block attributes that may contain material/thickness information;
- warnings for unsupported entities.

Do not continue blindly when the DXF is ambiguous.

### Stage B - Convert according to a job specification
The job file contains the DXF-specific decisions instead of hardcoding them into the core converter.

Example:

```json
{
  "input_dxf": "D:/path/example.dxf",
  "output_directory": "D:/path/output",
  "units": "mm",
  "step_schema": "AP242",
  "layers": {
    "FRAME_ALU": {
      "material": "EN AW-6082 T6",
      "density_kg_m3": 2700,
      "extrusion_mm": 5.0,
      "color_rgb": [0.78, 0.80, 0.82]
    },
    "PLATE_SS": {
      "material": "AISI 304",
      "density_kg_m3": 7930,
      "extrusion_mm": 3.0,
      "color_rgb": [0.72, 0.72, 0.75]
    }
  }
}
```

`extrusion_mm` must be optional. Never invent a thickness when the DXF does not define one and no job mapping exists.

---

## 6. Geometry rules

### 6.1 Existing 3D DXF geometry
If the DXF already contains usable 3D geometry, preserve it rather than forcing a 2D extrusion workflow.

Investigate and support, in priority order:

- 3DSOLID / ACIS data if FreeCAD/available libraries can import it reliably;
- 3DFACE;
- POLYFACE / MESH;
- 3D POLYLINE;
- planar closed outlines.

### 6.2 2D closed outlines
For planar closed geometry:

1. convert lines/arcs/polyline segments into wires;
2. validate closure within a configurable tolerance;
3. create faces;
4. detect inner loops/holes;
5. extrude only when thickness is known from DXF metadata or the job config;
6. validate resulting solids (`Shape.isValid()` or equivalent checks).

### 6.3 Open geometry
Do not create arbitrary solids from open geometry.

Keep it as reference geometry or report it as unresolved according to the job configuration.

### 6.4 Text, dimensions and hatches
Text, DIMENSION and HATCH objects are not mechanical solids by default.

- ignore or retain them as non-export construction/reference objects;
- log the decision;
- never turn annotations into STEP solids unless explicitly requested.

### 6.5 Blocks
Preserve block structure when practical, but the primary grouping requirement remains **DXF layer -> FreeCAD component**.

If an INSERT references geometry on multiple layers, document and implement one deterministic rule. Do not duplicate solids accidentally.

---

## 7. FreeCAD object model
For each DXF layer:

```text
Document
`-- App::Part  [Label = exact DXF layer name]
    |-- Part::Feature / solids
    |-- Part::Feature / solids
    `-- ...
```

Each component should receive custom properties such as:

- `SourceDXFLayer`
- `SourceDXFFile`
- `MaterialName`
- `MaterialStandard`
- `DensityKgM3`
- `DXFColor`
- `ConversionNotes`

Where FreeCAD has a native material framework/API available in the installed version, use it in addition to these traceability properties.

Avoid creating thousands of unnecessary FreeCAD document objects when a single layer can be represented as a sensible compound or fused set. Preserve meaningful part boundaries, but optimise document size and export speed.

---

## 8. Material handling
Implement material resolution with a strict precedence order:

1. explicit per-layer job configuration;
2. explicit DXF XDATA / block attribute / embedded material metadata;
3. explicit, documented layer-name mapping table;
4. otherwise `UNRESOLVED`.

Do not use heuristic guessing unless a job explicitly enables it.

Create a machine-readable output such as:

`output/<drawing>.materials.json`

containing:

```json
{
  "components": [
    {
      "name": "FRAME_ALU",
      "material": "EN AW-6082 T6",
      "density_kg_m3": 2700,
      "source": "job-config",
      "step_material_verified": true
    }
  ]
}
```

If STEP cannot carry the physical material in a round-trip test, set `step_material_verified` to `false` and keep the sidecar manifest as the authoritative material record.

---

## 9. STEP export
Prefer a STEP schema capable of retaining product structure and presentation data, ideally **AP242**, if the installed FreeCAD build supports it correctly.

Do not hardcode undocumented FreeCAD preference keys without verifying them against the installed version.

The exporter must try to preserve:

- component/product names;
- hierarchy where FreeCAD's STEP exporter supports it;
- body/solid geometry;
- colors;
- physical material metadata if supported;
- coordinate placement.

Use the FreeCAD export mechanism that best preserves names/colors/assembly metadata. Compare `Import.export` and other available STEP export routes in the installed FreeCAD version rather than assuming that `Part.export` is sufficient.

Output both:

- `<basename>.FCStd`
- `<basename>.step`

Optionally also output one STEP per layer/component when `--split-step` is requested.

---

## 10. Mandatory STEP round-trip verification
After export:

1. open a new blank FreeCAD document;
2. import the generated STEP;
3. count solids/components;
4. compare overall bounding box against the source FreeCAD model;
5. compare volume per component where applicable;
6. verify component names;
7. verify colors;
8. verify material designation/properties if the importer exposes them;
9. report differences.

Suggested tolerances:

- bbox/linear: configurable, default around `0.01 mm` for ordinary machine parts;
- volume: relative tolerance around `1e-5` unless the source geometry warrants otherwise.

Produce a report:

`output/<basename>.verification.json`

and a human-readable `.md` report.

The CLI exits non-zero when required acceptance criteria fail.

---

## 11. Units
DXF unit handling must be explicit.

- Read `$INSUNITS`.
- If units are defined, convert consistently to FreeCAD's mm-based working convention as appropriate.
- If `$INSUNITS` is missing or unitless, do not silently assume mm unless the job config explicitly states `units: mm`.
- Record the chosen scale factor in the conversion report.

This is a hard requirement because a geometrically correct STEP at the wrong scale is a failed conversion.

---

## 12. CLI target
Aim for commands similar to:

```powershell
FreeCADCmd.exe scripts/inspect_dxf.py "D:\drawings\part.dxf"

FreeCADCmd.exe scripts/convert_dxf.py `
  --input "D:\drawings\part.dxf" `
  --job "jobs\part.json" `
  --output "output\part.step"

FreeCADCmd.exe scripts/verify_step.py `
  --fcstd "output\part.FCStd" `
  --step "output\part.step"
```

If `ezdxf` inspection does not require FreeCAD, also provide a normal CPython entry point for inspection.

Do not rely on the FreeCAD GUI. Everything must be executable headlessly through `FreeCADCmd.exe` for repeatable batch conversion.

---

## 13. Logging and diagnostics
Every conversion should print and save a concise summary:

```text
DXF: example.dxf
Units: mm
Layers found: 8
Layers converted: 7
Components created: 7
Solids created: 23
Material mappings: 6 resolved / 1 unresolved
Unsupported entities: 2 SPLINE, 1 HATCH
STEP schema: AP242
STEP round-trip geometry: PASS
STEP names: PASS
STEP colors: PASS
STEP materials: PARTIAL / PASS / FAIL
```

Never swallow geometry exceptions. Include layer name, entity handle, entity type and reason in the error log.

---

## 14. Tests
Create synthetic DXF fixtures using `ezdxf` so tests do not depend only on customer drawings.

At minimum test:

1. two layers -> two FreeCAD components;
2. exact layer names retained;
3. closed polyline with a hole -> valid extruded solid;
4. arcs + lines forming a closed wire;
5. missing thickness -> fail or unresolved, never invented;
6. mm versus inch scaling;
7. material mapping from JSON;
8. layer color preservation;
9. unsupported entity reporting;
10. STEP export and re-import;
11. name retention after STEP round trip;
12. color retention after STEP round trip;
13. physical material retention test where supported;
14. repeated block INSERTs do not create accidental duplicates;
15. source DXF remains byte-for-byte unchanged.

---

## 15. Performance rules
Mechanical DXFs can contain many repeated lines/segments.

- Do not create a FreeCAD object for every raw DXF line unless necessary.
- Build wires/faces/shapes in memory first.
- Create document objects at meaningful component/body level.
- Use compounds or fusions when they preserve design intent.
- Recompute the document deliberately, not after every single entity.
- Keep enough traceability to identify source layer/entity handles when something fails.

---

## 16. First implementation milestone
Do not attempt every DXF entity type immediately.

Milestone 1 should support:

- LINE
- ARC
- CIRCLE
- LWPOLYLINE
- POLYLINE where practical
- layer grouping
- closed planar profile detection
- extrusion from explicit job thickness
- material mapping from JSON
- FreeCAD `.FCStd`
- STEP AP242/AP214 export as supported
- round-trip geometry/name/color verification

Then add SPLINE, ELLIPSE, blocks, 3D entity families, ACIS solids, etc. incrementally.

---

## 17. Suggested implementation strategy for Copilot
Proceed in this order:

1. Inspect the repository and create the project skeleton.
2. Detect the local FreeCAD version/API and `FreeCADCmd.exe` path; document it, but do not hardcode the user's machine path into library code.
3. Implement `dxf_inspector.py` with `ezdxf`.
4. Implement and test the job/config schema.
5. Implement layer/component creation.
6. Implement basic planar geometry conversion.
7. Implement material assignment inside FreeCAD.
8. Implement STEP export.
9. Implement round-trip verification.
10. Add synthetic tests.
11. Only then test against the first real supplied DXF.
12. For each unsupported/ambiguous real-DXF feature, extend the generic converter rather than patching the customer file destructively.

Keep the core generic. Per-DXF decisions belong in `jobs/<drawing>.json` or a similarly explicit mapping file.

---

## 18. Definition of done
A real job is complete only when all of the following are true:

- [ ] DXF source unchanged.
- [ ] Units confirmed.
- [ ] Every intended DXF layer appears as a named FreeCAD component.
- [ ] Expected geometry converted to valid solids/surfaces.
- [ ] No unexplained missing entities.
- [ ] Materials resolved or clearly flagged unresolved.
- [ ] FreeCAD model saves successfully.
- [ ] STEP exports successfully.
- [ ] STEP re-import succeeds.
- [ ] Geometry/bounding boxes survive round trip within tolerance.
- [ ] Component names survive or limitations are explicitly reported.
- [ ] Colors survive or limitations are explicitly reported.
- [ ] Physical materials survive STEP round trip, **or** the limitation is explicitly reported and the material manifest is delivered.
- [ ] Conversion + verification reports are written.

---

## 19. Important instructions to Copilot
- Do not fabricate material information.
- Do not assume mm when units are unknown.
- Do not invent extrusion thickness.
- Do not flatten all layers into one anonymous solid merely to obtain a STEP file.
- Do not claim that material preservation works until it has been verified by STEP re-import.
- Do not modify the input DXF.
- Prefer deterministic, auditable conversion over GUI automation.
- Preserve source layer names exactly unless STEP naming restrictions force a change; if so, maintain a mapping report.
- Keep scripts usable from VS Code and from `FreeCADCmd.exe`.

The end goal is not merely `DXF -> STEP`; it is a repeatable, traceable conversion where DXF layer structure becomes FreeCAD component structure and where material identity is preserved as far as the FreeCAD/STEP toolchain genuinely supports it.
