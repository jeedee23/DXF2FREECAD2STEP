"""Validate the shared-origin floor/wall FCStd and assembly STEP outputs."""

from __future__ import annotations

import json
from pathlib import Path

import FreeCAD
import Import


FCSTD_PATH = Path(r"D:\github\DXF2FREECAD2STEP\fcstd\Drawing1 - Test Zevekote_floor_wall.FCStd")
STEP_PATH = Path(r"D:\github\DXF2FREECAD2STEP\step\Drawing1 - Test Zevekote_floor_wall_assembly.step")
REPORT_PATH = FCSTD_PATH.with_suffix(".roundtrip.json")
TOLERANCE_MM = 0.01


def bounds_for(objects):
    boxes = [obj.Shape.BoundBox for obj in objects if hasattr(obj, "Shape") and not obj.Shape.isNull()]
    if not boxes:
        raise RuntimeError("No shapes were found for bounds validation.")
    return {
        "xmin": min(box.XMin for box in boxes),
        "xmax": max(box.XMax for box in boxes),
        "ymin": min(box.YMin for box in boxes),
        "ymax": max(box.YMax for box in boxes),
        "zmin": min(box.ZMin for box in boxes),
        "zmax": max(box.ZMax for box in boxes),
    }


def shape_objects(document):
    return [
        obj
        for obj in document.Objects
        if obj.TypeId == "Part::Feature" and hasattr(obj, "Shape") and not obj.Shape.isNull()
    ]


def assert_same_bounds(source, imported):
    for key, source_value in source.items():
        difference = abs(source_value - imported[key])
        if difference > TOLERANCE_MM:
            raise RuntimeError(
                f"STEP {key} differs by {difference:.6f} mm; tolerance is {TOLERANCE_MM} mm."
            )


def main() -> None:
    if not FCSTD_PATH.is_file() or not STEP_PATH.is_file():
        raise FileNotFoundError("Generate the FCStd and assembly STEP before validating them.")

    source_document = FreeCAD.openDocument(str(FCSTD_PATH))
    floor = source_document.getObject("Floor")
    wall = source_document.getObject("WallSolid")
    if floor is None or wall is None:
        raise RuntimeError("The FCStd does not contain the required Floor and WallSolid objects.")
    tiles = [obj for obj in floor.Group if obj.Name.startswith("FloorTile")]
    if len(tiles) != 21:
        raise RuntimeError(f"Expected 21 floor tiles, found {len(tiles)}.")
    if any(tile.Placement != FreeCAD.Placement() for tile in tiles):
        raise RuntimeError("A floor tile is not at the shared global origin.")
    source_objects = tiles + [wall]
    source_bounds = bounds_for(source_objects)
    source_solids = sum(len(obj.Shape.Solids) for obj in source_objects)
    FreeCAD.closeDocument(source_document.Name)

    roundtrip_document = FreeCAD.newDocument("FloorWallStepRoundTrip")
    Import.insert(str(STEP_PATH), roundtrip_document.Name)
    roundtrip_document.recompute()
    imported_objects = shape_objects(roundtrip_document)
    imported_bounds = bounds_for(imported_objects)
    imported_solids = sum(len(obj.Shape.Solids) for obj in imported_objects)
    if imported_solids != source_solids:
        raise RuntimeError(f"STEP has {imported_solids} solids; source has {source_solids}.")
    assert_same_bounds(source_bounds, imported_bounds)
    FreeCAD.closeDocument(roundtrip_document.Name)

    REPORT_PATH.write_text(
        json.dumps(
            {
                "fcstd": str(FCSTD_PATH),
                "step": str(STEP_PATH),
                "tile_count": len(tiles),
                "source_solid_count": source_solids,
                "imported_solid_count": imported_solids,
                "source_bounds_mm": source_bounds,
                "imported_bounds_mm": imported_bounds,
                "tolerance_mm": TOLERANCE_MM,
                "result": "PASS",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()