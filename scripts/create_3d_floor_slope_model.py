"""Create a FreeCAD reference model from the supplied DXF."""

from __future__ import annotations

import json
from pathlib import Path

import FreeCAD
import Import
import Part


SOURCE_DXF = Path(r"D:\github\DXF2FREECAD2STEP\dxf\Drawing1 - Test Zevekote.dxf")
OUTPUT_FCSTD = Path(
    r"D:\github\DXF2FREECAD2STEP\fcstd\Drawing1 - Test Zevekote_3D_reference.FCStd"
)
OUTPUT_REPORT = OUTPUT_FCSTD.with_suffix(".floor-elevations.json")
FLOOR_THICKNESS_MM = 250.0


def add_string_property(obj, name: str, value: str) -> None:
    obj.addProperty("App::PropertyString", name, "DXF traceability")
    setattr(obj, name, value)


def add_length_property(obj, name: str, value: float) -> None:
    obj.addProperty("App::PropertyLength", name, "Floor elevations")
    setattr(obj, name, value)


def add_elevation_property(obj, name: str, value: float) -> None:
    """Store signed elevations; FreeCAD's PropertyLength cannot be negative."""
    obj.addProperty("App::PropertyFloat", name, "Floor elevations")
    setattr(obj, name, value)


def add_layer_components(document) -> int:
    layer_groups = [
        obj
        for obj in document.Objects
        if obj.Name.startswith("Layer") and hasattr(obj, "Group")
    ]
    for index, layer_group in enumerate(layer_groups, start=1):
        layer_name = layer_group.Label
        layer_group.Label = f"Imported DXF layer source: {layer_name}"
        component = document.addObject("App::Part", f"DXFLayerComponent{index:03d}")
        component.Label = layer_name
        add_string_property(component, "SourceDXFLayer", layer_name)
        add_string_property(component, "SourceDXFFile", str(SOURCE_DXF))
        add_string_property(
            component,
            "ConversionNotes",
            "Native DXF import; physical material and extrusion remain unresolved.",
        )
        for child in layer_group.Group:
            component.addObject(child)
        if layer_group.ViewObject:
            layer_group.ViewObject.Visibility = False
    return len(layer_groups)


def floor_points():
    return (
        FreeCAD.Vector(285.6125547685916, 1274.535760686236, 0.0),
        FreeCAD.Vector(579.361984557639, 1274.535760686236, -20.0),
        FreeCAD.Vector(571.3619845576393, 933.5357606862363, -23.0),
        FreeCAD.Vector(285.6125547685916, 933.5357606862363, 0.0),
    )


def floor_faces(points):
    wall_corner, post_corner, post_middle, wall_middle = points
    return [
        Part.Face(Part.makePolygon([wall_corner, post_corner, post_middle, wall_corner])),
        Part.Face(Part.makePolygon([wall_corner, post_middle, wall_middle, wall_corner])),
    ]


def add_floor_slope_reference(document):
    reference = document.addObject("App::Part", "FloorElevationReference")
    reference.Label = "Floor elevation reference (wall to posts)"
    add_string_property(reference, "SourceDXFLayer", "Dimension / Staal - kolommen")
    add_string_property(reference, "SourceDXFFile", str(SOURCE_DXF))
    add_string_property(
        reference,
        "ConversionNotes",
        "Measured DXF notes: wall baseline 0 mm; corner post -20 mm; "
        "middle post -23 mm. Two faces interpolate between these "
        "documented elevations.",
    )

    points = floor_points()
    wall_corner, post_corner, post_middle, wall_middle = points

    floor_surface = document.addObject("Part::Feature", "SlopedFloorSurface")
    floor_surface.Label = "Sloped floor reference surface (0 / -20 / -23 mm)"
    floor_surface.Shape = Part.makeCompound(floor_faces(points))
    floor_surface.addProperty("App::PropertyString", "Role", "Floor elevations")
    floor_surface.Role = "Reference surface; the floor solid is created separately."
    add_elevation_property(floor_surface, "WallElevationMm", 0.0)
    add_elevation_property(floor_surface, "CornerPostElevationMm", -20.0)
    add_elevation_property(floor_surface, "MiddlePostElevationMm", -23.0)
    if floor_surface.ViewObject:
        floor_surface.ViewObject.ShapeColor = (0.30, 0.65, 1.00)
        floor_surface.ViewObject.Transparency = 55
    reference.addObject(floor_surface)

    slope_lines = document.addObject("Part::Feature", "DocumentedFloorFalls")
    slope_lines.Label = "Documented wall-to-post floor falls"
    slope_lines.Shape = Part.makeCompound(
        [
            Part.makeLine(wall_corner, post_corner),
            Part.makeLine(wall_middle, post_middle),
        ]
    )
    add_length_property(slope_lines, "CornerPostFall", 20.0)
    add_length_property(slope_lines, "MiddlePostFall", 23.0)
    if slope_lines.ViewObject:
        slope_lines.ViewObject.LineColor = (1.00, 0.25, 0.00)
        slope_lines.ViewObject.LineWidth = 4.0
    reference.addObject(slope_lines)

    return points, {
        "wall_baseline_mm": 0.0,
        "corner_post_floor_elevation_mm": -20.0,
        "middle_post_floor_elevation_mm": -23.0,
        "corner_fall_mm": 20.0,
        "middle_fall_mm": 23.0,
        "wall_to_corner_post_run_mm": wall_corner.distanceToPoint(post_corner),
        "wall_to_middle_post_run_mm": wall_middle.distanceToPoint(post_middle),
        "surface_interpolation": (
            "Piecewise-linear interpolation between documented wall baseline and "
            "the two documented post elevations."
        ),
    }


def add_floor_solid(document, reference, points):
    floor_solid = document.addObject("Part::Feature", "SlopedFloorSolid")
    floor_solid.Label = "Sloped floor solid (250 mm thick)"
    floor_solid.Shape = Part.makeCompound(
        [face.extrude(FreeCAD.Vector(0.0, 0.0, -FLOOR_THICKNESS_MM)) for face in floor_faces(points)]
    )
    floor_solid.addProperty("App::PropertyString", "Role", "Floor elevations")
    floor_solid.Role = (
        "Two floor wedges extruded vertically 250 mm below the documented top-floor elevations."
    )
    add_length_property(floor_solid, "Thickness", FLOOR_THICKNESS_MM)
    if floor_solid.ViewObject:
        floor_solid.ViewObject.ShapeColor = (0.65, 0.65, 0.70)
        floor_solid.ViewObject.Transparency = 15
    reference.addObject(floor_solid)

    preview = document.addObject("Part::Feature", "FloorSolidPreview")
    preview.Label = "Floor solid preview (250 mm thick)"
    preview.Shape = floor_solid.Shape
    preview.addProperty("App::PropertyString", "Role", "Floor elevations")
    preview.Role = "Root-level display copy of SlopedFloorSolid."
    if preview.ViewObject:
        preview.ViewObject.ShapeColor = (0.65, 0.65, 0.70)
        preview.ViewObject.Transparency = 15
    return {
        "thickness_mm": FLOOR_THICKNESS_MM,
        "solid_count": len(floor_solid.Shape.Solids),
        "volume_mm3": floor_solid.Shape.Volume,
    }


def place_columns_on_floor(document):
    component = next(
        obj
        for obj in document.Objects
        if obj.TypeId == "App::Part"
        and getattr(obj, "SourceDXFLayer", "") == "Staal - kolommen"
    )
    placements = {
        "Hoekkolom plan": -20.0,
        "Middelkolom plan": -23.0,
    }
    placed = []
    for child in component.Group:
        if child.Label not in placements:
            continue
        placement = child.Placement
        placement.Base.z = placements[child.Label]
        child.Placement = placement
        add_elevation_property(child, "FloorElevationMm", placements[child.Label])
        placed.append(
            {
                "object": child.Name,
                "label": child.Label,
                "elevation_mm": placements[child.Label],
            }
        )
    add_string_property(
        component,
        "FloorPlacementNotes",
        "Corner and middle plan-view post instances are placed at their documented "
        "floor elevations. Four unlocated section-detail strokes remain at source Z=0.",
    )
    return placed


def main() -> None:
    if not SOURCE_DXF.is_file():
        raise FileNotFoundError(f"DXF source does not exist: {SOURCE_DXF}")

    OUTPUT_FCSTD.parent.mkdir(parents=True, exist_ok=True)
    document = FreeCAD.newDocument("Drawing1_Test_Zevekote_3D_reference")
    import_stats = Import.readDXF(str(SOURCE_DXF))
    document.recompute()

    layer_components = add_layer_components(document)
    points, elevations = add_floor_slope_reference(document)
    floor_solid = add_floor_solid(document, document.getObject("FloorElevationReference"), points)
    placed_columns = place_columns_on_floor(document)
    document.recompute()

    floor_surface = document.getObject("SlopedFloorSurface")
    if not floor_surface.Shape.isValid():
        raise RuntimeError("The generated sloped floor reference surface is invalid.")
    if not document.getObject("SlopedFloorSolid").Shape.isValid():
        raise RuntimeError("The generated sloped floor solid is invalid.")

    document.saveAs(str(OUTPUT_FCSTD))
    report = {
        "source_dxf": str(SOURCE_DXF),
        "output_fcstd": str(OUTPUT_FCSTD),
        "units": "mm",
        "dxf_import": import_stats,
        "layer_components_created": layer_components,
        "floor_elevations": elevations,
        "floor_solid": floor_solid,
        "column_floor_placements": placed_columns,
        "limitations": [
            "DXF outlines are imported as source geometry; no unsupported "
            "extrusion thickness is invented.",
            "The 250 mm floor solid is derived from the documented top-floor "
            "elevations and extruded vertically downward.",
            "Only the two identifiable plan-view column instances are placed "
            "on the floor; unmapped detail strokes remain at source Z=0.",
            "Physical material mapping remains unresolved.",
        ],
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    FreeCAD.closeDocument(document.Name)


if __name__ == "__main__":
    main()
