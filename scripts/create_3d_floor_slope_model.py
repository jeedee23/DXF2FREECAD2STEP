"""Build the shared-origin Floor and Wall components from the Zevekote DXF."""

from __future__ import annotations

import json
import math
from pathlib import Path

import FreeCAD
import Import
import Part


SOURCE_DXF = Path(r"D:\github\DXF2FREECAD2STEP\dxf\Drawing1 - Test Zevekote.dxf")
OUTPUT_FCSTD = Path(r"D:\github\DXF2FREECAD2STEP\fcstd\Drawing1 - Test Zevekote_floor_wall.FCStd")
OUTPUT_REPORT = OUTPUT_FCSTD.with_suffix(".validation.json")
OUTPUT_STEP_DIRECTORY = Path(r"D:\github\DXF2FREECAD2STEP\step")
PROFILE_MANIFEST = Path(r"D:\github\DXF2FREECAD2STEP\fcstd\Drawing1 - Test Zevekote_vertical_l_profiles.json")
FLOOR_THICKNESS_MM = 250.0
WALL_THICKNESS_MM = 250.0
WALL_HEIGHT_MM = 3300.0
MIDDLE_LEVEL_ROW_DXF_CM = 933.5357606862363
MIDDLE_LEVEL_ROW_MM = 3468.0
TILE_COLUMNS = 3
TILE_ROWS = 7
VERTICAL_PROFILE_COUNT = 15


def add_string_property(obj, name: str, value: str, group: str = "Traceability") -> None:
    obj.addProperty("App::PropertyString", name, group)
    setattr(obj, name, value)


def add_float_property(obj, name: str, value: float, group: str = "Geometry") -> None:
    obj.addProperty("App::PropertyFloat", name, group)
    setattr(obj, name, value)


def extract_floor_outline(document):
    layer = next(
        (
            obj
            for obj in document.Objects
            if obj.Name.startswith("Layer")
            and getattr(obj, "Label", "") == "Dakrand"
            and hasattr(obj, "Group")
        ),
        None,
    )
    if layer is None:
        raise RuntimeError("The DXF does not contain the required Dakrand layer.")

    edges = []
    for child in layer.Group:
        shape = getattr(child, "Shape", None)
        if shape is None or shape.isNull():
            continue
        for edge in shape.Edges:
            vertices = edge.Vertexes
            if len(vertices) == 2:
                edges.append((vertices[0].Point, vertices[1].Point))

    vertical = [
        (first, second)
        for first, second in edges
        if abs(first.x - second.x) < 0.001 and abs(first.y - second.y) > 600.0
    ]
    if not vertical:
        raise RuntimeError("Dakrand does not contain the required long outer floor edge.")
    right_start, right_end = max(vertical, key=lambda edge: abs(edge[0].y - edge[1].y))
    outer_x = right_start.x
    bottom_y, top_y = sorted((right_start.y, right_end.y))

    horizontal = [
        (first, second)
        for first, second in edges
        if abs(first.y - second.y) < 0.001 and abs(first.x - second.x) > 250.0
    ]

    wall_x_values = []
    for first, second in horizontal:
        if abs(first.y - top_y) < 0.01 or abs(first.y - bottom_y) < 0.01:
            if abs(first.x - outer_x) < 0.01:
                wall_x_values.append(second.x)
            elif abs(second.x - outer_x) < 0.01:
                wall_x_values.append(first.x)
    if len(wall_x_values) < 2:
        raise RuntimeError("Dakrand does not define both wall-side floor corners.")
    wall_x = sum(wall_x_values) / len(wall_x_values)

    return {
        "datum_dxf_cm": (wall_x, top_y),
        "width_mm": (outer_x - wall_x) * 10.0,
        "length_mm": (top_y - bottom_y) * 10.0,
        "middle_level_row_mm": (top_y - MIDDLE_LEVEL_ROW_DXF_CM) * 10.0,
    }


def remove_imported_dxf(document) -> None:
    for obj in list(document.Objects):
        document.removeObject(obj.Name)
    document.recompute()


def quadratic_value(y_value: float, samples):
    value = 0.0
    for index, (sample_y, sample_z) in enumerate(samples):
        basis = 1.0
        for other_index, (other_y, _) in enumerate(samples):
            if index != other_index:
                basis *= (y_value - other_y) / (sample_y - other_y)
        value += sample_z * basis
    return value


def floor_elevation(x_value: float, y_value: float, width_mm: float, length_mm: float, middle_y: float) -> float:
    left_samples = ((0.0, 0.0), (middle_y, -9.5), (length_mm, -19.0))
    right_samples = ((0.0, -20.0), (middle_y, -23.0), (length_mm, -26.0))
    left_z = quadratic_value(y_value, left_samples)
    right_z = quadratic_value(y_value, right_samples)
    return left_z + (right_z - left_z) * (x_value / width_mm)


def make_face(points):
    return Part.Face(Part.makePolygon(points + [points[0]]))


def make_tile_solid(top_left, top_right, bottom_right, bottom_left):
    bottom_left_point = FreeCAD.Vector(top_left.x, top_left.y, top_left.z - FLOOR_THICKNESS_MM)
    bottom_right_point = FreeCAD.Vector(top_right.x, top_right.y, top_right.z - FLOOR_THICKNESS_MM)
    bottom_bottom_right = FreeCAD.Vector(bottom_right.x, bottom_right.y, bottom_right.z - FLOOR_THICKNESS_MM)
    bottom_bottom_left = FreeCAD.Vector(bottom_left.x, bottom_left.y, bottom_left.z - FLOOR_THICKNESS_MM)

    faces = [
        make_face([top_left, top_right, bottom_right]),
        make_face([top_left, bottom_right, bottom_left]),
        make_face([bottom_left_point, bottom_bottom_right, bottom_right_point]),
        make_face([bottom_left_point, bottom_bottom_left, bottom_bottom_right]),
        make_face([top_left, bottom_left_point, bottom_right_point, top_right]),
        make_face([top_right, bottom_right_point, bottom_bottom_right, bottom_right]),
        make_face([bottom_right, bottom_bottom_right, bottom_bottom_left, bottom_left]),
        make_face([bottom_left, bottom_bottom_left, bottom_left_point, top_left]),
    ]
    return Part.makeSolid(Part.makeShell(faces))


def add_floor_tiles(document, floor_component, outline):
    width_mm = outline["width_mm"]
    length_mm = outline["length_mm"]
    middle_y = outline["middle_level_row_mm"]
    x_coordinates = [0.0, 1000.0, 2000.0, width_mm]
    y_coordinates = [0.0, 1000.0, 2000.0, 3000.0, middle_y, middle_y + 1000.0, middle_y + 2000.0, length_mm]

    if len(x_coordinates) - 1 != TILE_COLUMNS or len(y_coordinates) - 1 != TILE_ROWS:
        raise RuntimeError("The configured tile grid is not 3 columns by 7 rows.")
    if not all(first < second for first, second in zip(x_coordinates, x_coordinates[1:])):
        raise RuntimeError("Floor tile X coordinates are not strictly increasing.")
    if not all(first < second for first, second in zip(y_coordinates, y_coordinates[1:])):
        raise RuntimeError("Floor tile Y coordinates are not strictly increasing.")

    tiles = []
    for row_index, (top_y, bottom_y) in enumerate(zip(y_coordinates, y_coordinates[1:]), start=1):
        for column_index, (left_x, right_x) in enumerate(zip(x_coordinates, x_coordinates[1:]), start=1):
            top_left = FreeCAD.Vector(left_x, top_y, floor_elevation(left_x, top_y, width_mm, length_mm, middle_y))
            top_right = FreeCAD.Vector(right_x, top_y, floor_elevation(right_x, top_y, width_mm, length_mm, middle_y))
            bottom_right = FreeCAD.Vector(right_x, bottom_y, floor_elevation(right_x, bottom_y, width_mm, length_mm, middle_y))
            bottom_left = FreeCAD.Vector(left_x, bottom_y, floor_elevation(left_x, bottom_y, width_mm, length_mm, middle_y))
            tile = document.addObject("Part::Feature", f"FloorTile{row_index:02d}{column_index:02d}")
            tile.Label = f"Concrete cut tile R{row_index} C{column_index}"
            tile.Shape = make_tile_solid(top_left, top_right, bottom_right, bottom_left)
            add_float_property(tile, "Row", row_index, "Tile grid")
            add_float_property(tile, "Column", column_index, "Tile grid")
            add_float_property(tile, "TopLeftZ", top_left.z, "Tile elevations")
            add_float_property(tile, "TopRightZ", top_right.z, "Tile elevations")
            add_float_property(tile, "BottomRightZ", bottom_right.z, "Tile elevations")
            add_float_property(tile, "BottomLeftZ", bottom_left.z, "Tile elevations")
            add_float_property(tile, "ThicknessMm", FLOOR_THICKNESS_MM, "Tile elevations")
            if tile.ViewObject:
                tile.ViewObject.ShapeColor = (0.68, 0.70, 0.72)
                tile.ViewObject.LineColor = (0.15, 0.15, 0.15)
                tile.ViewObject.LineWidth = 1.5
            floor_component.addObject(tile)
            tiles.append(tile)
    return tiles, x_coordinates, y_coordinates


def profile_vector(profile, local_x_cm: float, local_y_cm: float, z_value: float):
    rotation = math.radians(profile["rotation_degrees"])
    source_x = local_x_cm * math.cos(rotation) - local_y_cm * math.sin(rotation)
    source_y = local_x_cm * math.sin(rotation) + local_y_cm * math.cos(rotation)
    global_x, global_y = profile["global_xy_mm"]
    return FreeCAD.Vector(global_x + source_x * 10.0, global_y - source_y * 10.0, z_value)


def make_vertical_l_profile(profile, base_z: float, height_mm: float):
    outer_top = profile_vector(profile, 7.6, 0.0, base_z)
    flange_start = profile_vector(profile, 0.0, 0.0, base_z)
    flange_inner = profile_vector(profile, 0.0, -0.2, base_z)
    inner_arc_start = profile_vector(profile, 7.6, -0.2, base_z)
    inner_arc_middle = profile_vector(profile, 7.7414213562, -0.2585786438, base_z)
    inner_arc_end = profile_vector(profile, 7.8, -0.4, base_z)
    web_inner_end = profile_vector(profile, 7.8, -4.5, base_z)
    web_outer_end = profile_vector(profile, 8.0, -4.5, base_z)
    outer_arc_start = profile_vector(profile, 8.0, -0.4, base_z)
    outer_arc_middle = profile_vector(profile, 7.8828427125, -0.1171572875, base_z)

    edges = [
        Part.makeLine(outer_top, flange_start),
        Part.makeLine(flange_start, flange_inner),
        Part.makeLine(flange_inner, inner_arc_start),
        Part.Arc(inner_arc_start, inner_arc_middle, inner_arc_end).toShape(),
        Part.makeLine(inner_arc_end, web_inner_end),
        Part.makeLine(web_inner_end, web_outer_end),
        Part.makeLine(web_outer_end, outer_arc_start),
        Part.Arc(outer_arc_start, outer_arc_middle, outer_top).toShape(),
    ]
    return Part.Face(Part.Wire(edges)).extrude(FreeCAD.Vector(0.0, 0.0, height_mm))


def add_vertical_l_profiles(document, assembly, outline):
    if not PROFILE_MANIFEST.is_file():
        raise FileNotFoundError(
            "Vertical L-profile manifest is missing. Run scripts/extract_vertical_l_profiles.py first."
        )
    manifest = json.loads(PROFILE_MANIFEST.read_text(encoding="utf-8"))
    datum_x, datum_y = manifest["datum_dxf_cm"]
    expected_x, expected_y = outline["datum_dxf_cm"]
    if abs(datum_x - expected_x) > 0.000001 or abs(datum_y - expected_y) > 0.000001:
        raise RuntimeError("Vertical L-profile manifest does not use the Floor/Wall point-1 datum.")
    profiles_data = manifest["profiles"]
    if len(profiles_data) != VERTICAL_PROFILE_COUNT:
        raise RuntimeError(
            f"Expected {VERTICAL_PROFILE_COUNT} vertical L profiles; manifest contains {len(profiles_data)}."
        )

    component = document.addObject("App::Part", "VerticalLProfiles")
    component.Label = "Staal - L profielen verticaal"
    add_string_property(component, "SourceDXFLayer", manifest["source_layer"])
    add_string_property(component, "SourceDXFFile", str(SOURCE_DXF))
    add_string_property(component, "CoordinateSystem", "Shared global origin at floor point 1.")
    add_float_property(component, "ProfileHeightMm", manifest["profile_height_mm"])
    add_float_property(component, "ProfileCount", len(profiles_data))
    assembly.addObject(component)

    profiles = []
    for index, profile_data in enumerate(profiles_data, start=1):
        x_value, y_value = profile_data["global_xy_mm"]
        base_z = floor_elevation(
            x_value,
            y_value,
            outline["width_mm"],
            outline["length_mm"],
            outline["middle_level_row_mm"],
        )
        profile = document.addObject("Part::Feature", f"VerticalLProfile{index:02d}")
        profile.Label = f"Vertical L profile {index:02d} ({profile_data['block']})"
        profile.Shape = make_vertical_l_profile(profile_data, base_z, manifest["profile_height_mm"])
        add_string_property(profile, "SourceDXFHandle", profile_data["handle"])
        add_string_property(profile, "SourceDXFBlock", profile_data["block"])
        add_float_property(profile, "BaseElevationMm", base_z)
        add_float_property(profile, "HeightMm", manifest["profile_height_mm"])
        if profile.ViewObject:
            profile.ViewObject.ShapeColor = (0.30, 0.34, 0.38)
            profile.ViewObject.LineColor = (0.08, 0.08, 0.08)
        component.addObject(profile)
        profiles.append(profile)
    return component, profiles, manifest


def add_wall(document, assembly, length_mm: float):
    wall_component = document.addObject("App::Part", "Wall")
    wall_component.Label = "Wall"
    add_string_property(wall_component, "SourceDXFLayer", "Bestaande ruwbouw")
    add_string_property(wall_component, "SourceDXFFile", str(SOURCE_DXF))
    add_string_property(wall_component, "CoordinateSystem", "Shared global origin at floor point 1.")
    assembly.addObject(wall_component)

    wall = document.addObject("Part::Feature", "WallSolid")
    wall.Label = "Existing rough-construction wall (250 mm x 3300 mm)"
    wall.Shape = Part.makeBox(
        WALL_THICKNESS_MM,
        length_mm,
        WALL_HEIGHT_MM,
        FreeCAD.Vector(-WALL_THICKNESS_MM, 0.0, 0.0),
    )
    add_float_property(wall, "ThicknessMm", WALL_THICKNESS_MM)
    add_float_property(wall, "HeightMm", WALL_HEIGHT_MM)
    if wall.ViewObject:
        wall.ViewObject.ShapeColor = (0.80, 0.72, 0.57)
        wall.ViewObject.LineColor = (0.25, 0.20, 0.15)
    wall_component.addObject(wall)
    return wall_component, wall


def validate_model(tiles, profiles, wall, outline, x_coordinates, y_coordinates):
    if len(tiles) != TILE_COLUMNS * TILE_ROWS:
        raise RuntimeError(f"Expected {TILE_COLUMNS * TILE_ROWS} floor tiles; created {len(tiles)}.")
    for tile in tiles:
        if not tile.Shape.isValid() or len(tile.Shape.Solids) != 1:
            raise RuntimeError(f"{tile.Label} is not one valid solid.")
        if tile.Placement != FreeCAD.Placement():
            raise RuntimeError(f"{tile.Label} is not at the shared global origin.")
    if len(profiles) != VERTICAL_PROFILE_COUNT:
        raise RuntimeError(f"Expected {VERTICAL_PROFILE_COUNT} vertical L profiles; created {len(profiles)}.")
    for profile in profiles:
        if not profile.Shape.isValid() or len(profile.Shape.Solids) != 1:
            raise RuntimeError(f"{profile.Label} is not one valid solid.")
        if profile.Placement != FreeCAD.Placement():
            raise RuntimeError(f"{profile.Label} is not at the shared global origin.")
    if not wall.Shape.isValid() or len(wall.Shape.Solids) != 1:
        raise RuntimeError("WallSolid is not one valid solid.")

    measurement_checks = {
        "point_1": floor_elevation(0.0, 0.0, outline["width_mm"], outline["length_mm"], outline["middle_level_row_mm"]),
        "point_2": floor_elevation(outline["width_mm"], 0.0, outline["width_mm"], outline["length_mm"], outline["middle_level_row_mm"]),
        "point_3": floor_elevation(0.0, outline["middle_level_row_mm"], outline["width_mm"], outline["length_mm"], outline["middle_level_row_mm"]),
        "point_4": floor_elevation(outline["width_mm"], outline["middle_level_row_mm"], outline["width_mm"], outline["length_mm"], outline["middle_level_row_mm"]),
        "point_5": floor_elevation(0.0, outline["length_mm"], outline["width_mm"], outline["length_mm"], outline["middle_level_row_mm"]),
        "point_6": floor_elevation(outline["width_mm"], outline["length_mm"], outline["width_mm"], outline["length_mm"], outline["middle_level_row_mm"]),
    }
    expected_levels = {"point_1": 0.0, "point_2": -20.0, "point_3": -9.5, "point_4": -23.0, "point_5": -19.0, "point_6": -26.0}
    for name, expected in expected_levels.items():
        if abs(measurement_checks[name] - expected) > 0.000001:
            raise RuntimeError(f"{name} is {measurement_checks[name]} mm, expected {expected} mm.")
    return measurement_checks


def main() -> None:
    if not SOURCE_DXF.is_file():
        raise FileNotFoundError(f"DXF source does not exist: {SOURCE_DXF}")

    OUTPUT_FCSTD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_STEP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    document = FreeCAD.newDocument("Drawing1_Test_Zevekote_Floor_Wall")
    Import.readDXF(str(SOURCE_DXF))
    document.recompute()
    outline = extract_floor_outline(document)
    remove_imported_dxf(document)

    assembly = document.addObject("App::Part", "FloorWallAssembly")
    assembly.Label = "Floor, wall, and vertical-profile assembly (shared global origin)"
    add_string_property(assembly, "CoordinateSystem", "Point 1 is FreeCAD (0, 0, 0); DXF centimetres are scaled to millimetres.")
    add_string_property(assembly, "SourceDXFFile", str(SOURCE_DXF))
    add_float_property(assembly, "DXFToMillimetreScale", 10.0)
    add_float_property(assembly, "FloorWidthMm", outline["width_mm"])
    add_float_property(assembly, "FloorLengthMm", outline["length_mm"])

    floor_component = document.addObject("App::Part", "Floor")
    floor_component.Label = "Floor"
    add_string_property(floor_component, "SourceDXFLayer", "Dakrand")
    add_string_property(floor_component, "SourceDXFFile", str(SOURCE_DXF))
    add_string_property(floor_component, "CoordinateSystem", "Shared global origin at floor point 1.")
    add_string_property(floor_component, "MeshMethod", "21 concrete-cut tiles, each split into two top-surface triangles.")
    add_float_property(floor_component, "ThicknessMm", FLOOR_THICKNESS_MM)
    assembly.addObject(floor_component)

    tiles, x_coordinates, y_coordinates = add_floor_tiles(document, floor_component, outline)
    vertical_profiles_component, profiles, profile_manifest = add_vertical_l_profiles(document, assembly, outline)
    wall_component, wall = add_wall(document, assembly, outline["length_mm"])
    document.recompute()
    checks = validate_model(tiles, profiles, wall, outline, x_coordinates, y_coordinates)

    document.saveAs(str(OUTPUT_FCSTD))
    assembly_step = OUTPUT_STEP_DIRECTORY / "Drawing1 - Test Zevekote_floor_wall_assembly.step"
    floor_step = OUTPUT_STEP_DIRECTORY / "Drawing1 - Test Zevekote_floor.step"
    wall_step = OUTPUT_STEP_DIRECTORY / "Drawing1 - Test Zevekote_wall.step"
    profiles_step = OUTPUT_STEP_DIRECTORY / "Drawing1 - Test Zevekote_vertical_l_profiles.step"
    Import.export(tiles + profiles + [wall], str(assembly_step))
    Import.export(tiles, str(floor_step))
    Import.export([wall], str(wall_step))
    Import.export(profiles, str(profiles_step))

    report = {
        "source_dxf": str(SOURCE_DXF),
        "output_fcstd": str(OUTPUT_FCSTD),
        "output_step": {
            "assembly": str(assembly_step),
            "floor": str(floor_step),
            "wall": str(wall_step),
            "vertical_l_profiles": str(profiles_step),
        },
        "units": "mm",
        "dxf_units": "unitless; project instruction specifies centimetres",
        "dxf_to_mm_scale": 10.0,
        "datum": {
            "source_dxf_cm": outline["datum_dxf_cm"],
            "freecad_mm": [0.0, 0.0, 0.0],
            "point": "1",
        },
        "floor": {
            "source_layer": "Dakrand",
            "width_mm": outline["width_mm"],
            "length_mm": outline["length_mm"],
            "thickness_mm": FLOOR_THICKNESS_MM,
            "tile_count": len(tiles),
            "x_coordinates_mm": x_coordinates,
            "y_coordinates_mm": y_coordinates,
            "measured_elevations_mm": checks,
        },
        "wall": {
            "source_layer": "Bestaande ruwbouw",
            "thickness_mm": WALL_THICKNESS_MM,
            "height_mm": WALL_HEIGHT_MM,
            "floor_facing_plane": "X = 0 mm",
        },
        "vertical_l_profiles": {
            "source_layer": profile_manifest["source_layer"],
            "profile_count": len(profiles),
            "profile_height_mm": profile_manifest["profile_height_mm"],
            "profile_section_mm": profile_manifest["profile_section_mm"],
        },
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    FreeCAD.closeDocument(document.Name)


if __name__ == "__main__":
    main()
