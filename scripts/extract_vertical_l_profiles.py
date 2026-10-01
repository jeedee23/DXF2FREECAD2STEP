"""Extract in-footprint vertical L-profile placements from the Zevekote DXF."""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
from ezdxf import bbox


SOURCE_DXF = Path(r"D:\github\DXF2FREECAD2STEP\dxf\Drawing1 - Test Zevekote.dxf")
OUTPUT_MANIFEST = Path(
    r"D:\github\DXF2FREECAD2STEP\fcstd\Drawing1 - Test Zevekote_vertical_l_profiles.json"
)
PROFILE_LAYER = "Staal - L profielen verticaal"
PLAN_BLOCKS = {
    "L profiel verticaal voor langse zijde",
    "L profiel verticaal voor kopse zijde",
}
SIDE_VIEW_BLOCK = "L profiel verticaal voor langse zijde zijaanzicht"
EXPECTED_PROFILE_COUNT = 15


def floor_outline(document):
    lines = [
        entity
        for entity in document.modelspace()
        if entity.dxf.layer == "Dakrand" and entity.dxftype() == "LINE"
    ]
    vertical = [
        line
        for line in lines
        if abs(line.dxf.start.x - line.dxf.end.x) < 0.000001
        and abs(line.dxf.start.y - line.dxf.end.y) > 60.0
    ]
    if not vertical:
        raise RuntimeError("Dakrand does not contain the long outer floor edge.")
    outer = max(vertical, key=lambda line: abs(line.dxf.start.y - line.dxf.end.y))
    outer_x = outer.dxf.start.x
    bottom_y, top_y = sorted((outer.dxf.start.y, outer.dxf.end.y))

    horizontal = [
        line
        for line in lines
        if abs(line.dxf.start.y - line.dxf.end.y) < 0.000001
        and abs(line.dxf.start.x - line.dxf.end.x) > 25.0
    ]
    wall_x_candidates = []
    for line in horizontal:
        if min(abs(line.dxf.start.y - top_y), abs(line.dxf.start.y - bottom_y)) > 0.000001:
            continue
        if abs(line.dxf.start.x - outer_x) < 0.000001:
            wall_x_candidates.append(line.dxf.end.x)
        elif abs(line.dxf.end.x - outer_x) < 0.000001:
            wall_x_candidates.append(line.dxf.start.x)
    if len(wall_x_candidates) < 2:
        raise RuntimeError("Dakrand does not define both wall-side floor corners.")

    return {
        "wall_x_cm": sum(wall_x_candidates) / len(wall_x_candidates),
        "outer_x_cm": outer_x,
        "top_y_cm": top_y,
        "bottom_y_cm": bottom_y,
    }


def profile_height_mm(document) -> float:
    side_view = document.blocks.get(SIDE_VIEW_BLOCK)
    side_view_box = bbox.extents(list(side_view), fast=True)
    height_mm = (side_view_box.extmax.y - side_view_box.extmin.y) * 10.0
    if height_mm <= 0.0:
        raise RuntimeError("Vertical L-profile side-view height is invalid.")
    return height_mm


def extract_profiles(document, outline):
    profiles = []
    for entity in document.modelspace():
        if entity.dxf.layer != PROFILE_LAYER or entity.dxftype() != "INSERT":
            continue
        if entity.dxf.name not in PLAN_BLOCKS:
            continue
        insert = entity.dxf.insert
        if not (
            outline["wall_x_cm"] <= insert.x <= outline["outer_x_cm"]
            and outline["bottom_y_cm"] <= insert.y <= outline["top_y_cm"]
        ):
            continue
        profiles.append(
            {
                "handle": entity.dxf.handle,
                "block": entity.dxf.name,
                "insert_dxf_cm": [insert.x, insert.y, insert.z],
                "rotation_degrees": entity.dxf.rotation,
                "global_xy_mm": [
                    (insert.x - outline["wall_x_cm"]) * 10.0,
                    (outline["top_y_cm"] - insert.y) * 10.0,
                ],
            }
        )
    profiles.sort(key=lambda profile: (profile["global_xy_mm"][1], profile["global_xy_mm"][0]))
    if len(profiles) != EXPECTED_PROFILE_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_PROFILE_COUNT} in-footprint vertical L profiles; found {len(profiles)}."
        )
    return profiles


def main() -> None:
    if not SOURCE_DXF.is_file():
        raise FileNotFoundError(f"DXF source does not exist: {SOURCE_DXF}")
    document = ezdxf.readfile(SOURCE_DXF)
    if PROFILE_LAYER not in document.layers:
        raise RuntimeError(f"The required layer does not exist: {PROFILE_LAYER}")
    outline = floor_outline(document)
    profiles = extract_profiles(document, outline)
    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.write_text(
        json.dumps(
            {
                "source_dxf": str(SOURCE_DXF),
                "source_units": "cm",
                "freecad_units": "mm",
                "dxf_to_mm_scale": 10.0,
                "datum_dxf_cm": [outline["wall_x_cm"], outline["top_y_cm"]],
                "source_layer": PROFILE_LAYER,
                "profile_height_mm": profile_height_mm(document),
                "profile_section_mm": {
                    "outer_width": 80.0,
                    "outer_depth": 45.0,
                    "wall_thickness": 2.0,
                    "inner_corner_radius": 2.0,
                    "outer_corner_radius": 4.0,
                },
                "profiles": profiles,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()