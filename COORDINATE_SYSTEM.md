# Coordinate System Reference

## Identifier Rule

```text
O       = requested global FreeCAD/Fusion origin
P1..P6 = six surveyed floor-elevation points from the annotated DXF image
```

`O` and `P6` are deliberately **not** treated as the same point.
The current plan establishes that `O` shares its XY location with `P1`.
`P6` is the wall-side/right-hand corner at the far end of the floor.

## Chosen Global Orientation

The reference below follows the latest annotated DXF plan. The numbered points
proceed clockwise from the origin.

```text
Top view

                  wall
P4 ------------- P5 ------------- P6
|                                 |
|                                 |
|                                 |
P3 ------------- P2 ------------- P1 = O
                                  0,0,0

      +X: from P1 to P6, toward the wall
      +Y: from P1 to P3, to the left along the lower floor edge
      +Z: vertically upward
```

```text
Global coordinate extents for the current floor footprint

O = (0, 0, 0)

floor X range = 0 .. 2995.494 mm
floor Y range = 0 .. 6446.220 mm

wall floor-facing plane = X = 2995.494 mm
wall thickness direction = +X, behind the floor-facing wall plane
```

## Origin Marker

The marker is an exported component in every STEP file.

```text
OriginMarker

X =    0 .. +100 mm
Y = -200 ..    0 mm
Z =    0 .. +100 mm
```

This makes the global origin and positive-X/negative-Y corner visible after a
STEP import into Fusion.

## Surveyed Floor Levels

These levels are relative to the drawing's `BASIS` reference plane. `P1` shares
the origin XY position, but its floor top is below the global `Z = 0` plane.

```text
P1 = (   0.000,    0.000, -20.0 mm)  origin XY corner
P2 = (   0.000, 3468.000, -23.0 mm)  lower edge, middle level point
P3 = (   0.000, 6446.220, -26.0 mm)  lower-left corner
P4 = (2995.494, 6446.220, -19.0 mm)  wall-side left corner
P5 = (2995.494, 3468.000,  -9.5 mm)  wall side, middle level point
P6 = (2995.494,    0.000,   0.0 mm)  wall-side right corner / BASIS
```

```text
Clockwise point order

P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P1
```

## Required Mapping Before Rebuild

The XY mapping is now established. Remaining floor-elevation labels must still
be transcribed from the DXF before a corrected mesh is built.

```text
Known:     O = P1 in XY only.
Known:     Z(P1) = -20.0 mm.
Known:     Z(P2) = -23.0 mm.
Known:     Z(P3) = -26.0 mm.
Known:     Z(P4) = -19.0 mm.
Known:     Z(P5) =  -9.5 mm.
Known:     Z(P6) =   0.0 mm (BASIS).
```

No Z rebasing is required: the drawing's `BASIS` is the global horizontal
`Z = 0` plane. The floor mesh directly uses the stated signed elevations.

## Wall Vertical Range

The required wall range is global and does not depend on the floor mesh:

```text
wall bottom = Z = -250 mm
wall top    = Z = +3300 mm
```

The sloped floor top is modeled from surveyed elevations; each concrete tile
extends 250 mm vertically below its local top surface.