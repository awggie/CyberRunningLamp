"""
cyberlamp_housing.py — parametric 3D model of the CyberRunningLamp housing.

Built with CadQuery (https://cadquery.readthedocs.io). Run:

	pip install cadquery
	python3 cyberlamp_housing.py

and it writes STL (for slicing), 3MF (opens straight into Bambu Studio) and
STEP (editable in Fusion 360) files into ./output/.

Layout: the salvaged Hella LED module lies flat, LEDs facing up, on three
standoffs rising from the lid of an electronics base. The module's front and
back fins stay exposed; a frosted diffuser cap slips over the oval LED boss.

Parts:
	1. fit_test_rings       — 4 short oval rings with different clearances; find
	                          which one fits the boss snugly before printing the cap
	2. fit_test_template    — flat template that drops over the boss and shows
	                          whether the 3 mounting holes line up
	3. diffuser_cap         — frosted cap over the LEDs (print in natural/white PETG)
	4. base_tub             — electronics enclosure: XIAO cradle, USB-C port,
	                          mode button, hex vents
	5. base_lid             — lid with standoffs for the module, vents and wire slot

Coordinate frame (all mm): taken from the module itself. Origin = center of the
bottom-left mounting hole (with the fins on the left, as in the reference
photo); +X toward the bottom-right hole; +Y toward the top hole; +Z up out of
the LED side. Measured geometry lives in module_geometry.json.
"""

import json
import math
from pathlib import Path

import cadquery as cq
import numpy as np
from scipy.spatial import ConvexHull

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
OUTPUT_DIRECTORY = SCRIPT_DIRECTORY / "output"

# ============================================================
# Measured module geometry (from calipers + top-down photo)
# ============================================================

module = json.loads((SCRIPT_DIRECTORY / "module_geometry.json").read_text())

mounting_holes = [
	tuple(module["holes_mm"]["bottom_left"]),
	tuple(module["holes_mm"]["bottom_right"]),
	tuple(module["holes_mm"]["top"]),
]
boss_center = tuple(module["boss"]["center_mm"])
boss_major_diameter = module["boss"]["major_mm"]        # 49.46
boss_minor_diameter = module["boss"]["minor_mm"]        # 42.03
boss_major_axis_angle = module["boss"]["major_axis_angle_deg"]
boss_height_above_plate = module["boss"]["height_above_plate_mm"]  # 11.9
plate_thickness = module["plate_thickness_mm"]          # ~3
connector_center = tuple(module["connector_center_mm"])

# ============================================================
# Tunable parameters — change these and re-run
# ============================================================

# Diffuser cap fit. Pick the value from the fit-test ring that fits best
# (ring 1–4 = the values in fit_test_clearances below).
cap_fit_clearance_per_side = 0.45
fit_test_clearances = [0.3, 0.6, 1.2, 1.6]   # rings 1–2: O-ring removed; 3–4: O-ring on

cap_wall_thickness = 1.8
cap_top_thickness = 1.2                      # thin enough to glow, thick enough to diffuse
cap_gap_above_boss = 16.0                    # more distance = smoother glow, fewer hotspots
cap_wire_notch_width = 10.0
cap_wire_notch_height = 6.0

# Module mounting
standoff_height = 32.0                       # must clear the module's back fins (~27–30 mm)
standoff_outer_diameter = 9.0
module_screw_pilot_diameter = 3.4            # original ~4 mm self-tapping screws bite into PETG
module_screw_pilot_depth = 14.0

# Base enclosure
base_length = 140.0                          # along X
base_width = 92.0                            # along Y
base_height = 34.0
base_wall_thickness = 2.4
base_floor_thickness = 2.4
base_corner_radius = 8.0
base_center = (7.5, 23.0)                    # centered under the module footprint

lid_thickness = 3.0
lid_screw_clearance_diameter = 3.4           # M3x6 self-tapping screws (HW-001)
corner_post_size = 8.0
corner_post_pilot_diameter = 2.5             # pilot for M3 self-tapping into PETG
corner_post_pilot_depth = 10.0

# XIAO ESP32S3 cradle (board drops in, USB-C faces the back wall)
xiao_board_length = 21.0                     # along Y (USB-C end at back wall)
xiao_board_width = 17.8                      # along X
xiao_fit_clearance = 0.2
xiao_cradle_floor_height = 1.8               # board bottom sits this high above the tub floor
xiao_center_x = 30.0
usb_slot_width = 13.0
usb_slot_height = 7.0
usb_recess_width = 16.0                      # thins the wall around the port so plugs seat fully
usb_recess_height = 10.0
usb_recess_depth = 1.2

# Mode button: 6x6 tactile switch with tall round actuator, glued into a pocket behind the front wall
button_actuator_hole_diameter = 3.8
button_center_x = 7.5
button_center_z = 17.0

# Hex vents
vent_hex_across_flats = 5.0
vent_hex_pitch = 7.0

# Wire pass-through in the lid (wires drop from the cap notch past the plate edge)
lid_wire_slot_center = (20.0, -11.5)
lid_wire_slot_size = (12.0, 4.5)

# ============================================================
# Helpers
# ============================================================

def ellipse_radius_at_angle(semi_major, semi_minor, ellipse_rotation_deg, direction_deg):
	"""Distance from an ellipse's center to its edge along a given direction."""
	local_angle = math.radians(direction_deg - ellipse_rotation_deg)
	return (semi_major * semi_minor) / math.sqrt(
		(semi_minor * math.cos(local_angle)) ** 2 + (semi_major * math.sin(local_angle)) ** 2
	)


def oval_ring(semi_major, semi_minor, wall, height):
	"""Open oval ring centered on the boss, rotated to match it."""
	outer = (
		cq.Workplane("XY")
		.ellipse(semi_major + wall, semi_minor + wall, rotation_angle=boss_major_axis_angle)
		.extrude(height)
	)
	inner = (
		cq.Workplane("XY")
		.ellipse(semi_major, semi_minor, rotation_angle=boss_major_axis_angle)
		.extrude(height)
	)
	return outer.cut(inner).translate((boss_center[0], boss_center[1], 0))


def bar_between(start_xy, end_xy, width, height):
	"""Flat rectangular bar between two XY points (for template arms)."""
	dx, dy = end_xy[0] - start_xy[0], end_xy[1] - start_xy[1]
	length = math.hypot(dx, dy)
	angle = math.degrees(math.atan2(dy, dx))
	return (
		cq.Workplane("XY")
		.rect(length, width)
		.extrude(height)
		.rotate((0, 0, 0), (0, 0, 1), angle)
		.translate(((start_xy[0] + end_xy[0]) / 2, (start_xy[1] + end_xy[1]) / 2, 0))
	)


def hex_prism_points(across_flats):
	"""Pointy-top hexagon outline (vertex up) — prints cleanly on vertical walls without supports."""
	circumradius = across_flats / math.sqrt(3)
	return [
		(circumradius * math.cos(math.radians(90 + 60 * i)), circumradius * math.sin(math.radians(90 + 60 * i)))
		for i in range(6)
	]


def hex_vent_cutter(plane_name, centers_2d, depth, offset_along_normal):
	"""Union of hex prisms on a workplane, used to cut a vent grid through a wall or lid."""
	points = hex_prism_points(vent_hex_across_flats)
	cutter = None
	for center_u, center_v in centers_2d:
		prism = (
			cq.Workplane(plane_name, origin=(0, 0, 0))
			.workplane(offset=offset_along_normal)
			.center(center_u, center_v)
			.polyline(points).close()
			.extrude(depth)
		)
		cutter = prism if cutter is None else cutter.union(prism)
	return cutter


def hex_grid(u_min, u_max, v_min, v_max):
	"""Staggered hex-grid centers that fit fully inside a rectangle."""
	margin = vent_hex_across_flats / math.sqrt(3)
	row_spacing = vent_hex_pitch * math.sqrt(3) / 2
	centers = []
	row = 0
	v = v_min + margin
	while v <= v_max - margin:
		u_offset = (vent_hex_pitch / 2) if row % 2 else 0.0
		u = u_min + margin + u_offset
		while u <= u_max - margin:
			centers.append((u, v))
			u += vent_hex_pitch
		v += row_spacing
		row += 1
	return centers


# Derived layout values
base_x_min = base_center[0] - base_length / 2
base_x_max = base_center[0] + base_length / 2
base_y_min = base_center[1] - base_width / 2
base_y_max = base_center[1] + base_width / 2
module_plate_bottom_z = base_height + lid_thickness + standoff_height

cap_inner_semi_major = boss_major_diameter / 2 + cap_fit_clearance_per_side
cap_inner_semi_minor = boss_minor_diameter / 2 + cap_fit_clearance_per_side
cap_inner_height = boss_height_above_plate + cap_gap_above_boss
connector_direction_deg = math.degrees(
	math.atan2(connector_center[1] - boss_center[1], connector_center[0] - boss_center[0])
)

# ============================================================
# Part 1: fit-test rings
# ============================================================

def build_fit_test_rings():
	"""Four 5 mm-tall oval rings in a row. Ring N has N small tabs so you can tell them apart."""
	rings = None
	for ring_index, clearance in enumerate(fit_test_clearances, start=1):
		ring = oval_ring(
			boss_major_diameter / 2 + clearance,
			boss_minor_diameter / 2 + clearance,
			wall=1.6,
			height=5.0,
		)
		# ID tabs on the outside edge along the minor axis
		edge_distance = ellipse_radius_at_angle(
			boss_major_diameter / 2 + clearance + 1.6,
			boss_minor_diameter / 2 + clearance + 1.6,
			boss_major_axis_angle,
			boss_major_axis_angle + 90,
		)
		for tab_number in range(ring_index):
			tab_direction = math.radians(boss_major_axis_angle + 90 + (tab_number - (ring_index - 1) / 2) * 7)
			tab_center = (
				boss_center[0] + (edge_distance + 1.0) * math.cos(tab_direction),
				boss_center[1] + (edge_distance + 1.0) * math.sin(tab_direction),
			)
			tab = cq.Workplane("XY").circle(1.4).extrude(3.0).translate((tab_center[0], tab_center[1], 0))
			ring = ring.union(tab)
		# Move to the origin, then lay the rings out in a row
		ring = ring.translate((-boss_center[0] + (ring_index - 1) * 60.0, -boss_center[1], 0))
		rings = ring if rings is None else rings.union(ring)
	return rings


# ============================================================
# Part 2: fit-test template (oval + 3 mounting holes)
# ============================================================

def build_fit_test_template():
	"""Drops over the boss; if the 3 rings line up with the module's holes, the hole map is right."""
	template_height = 2.4
	template = oval_ring(cap_inner_semi_major, cap_inner_semi_minor, wall=2.0, height=template_height)
	hole_ring_outer_radius = 4.5
	for hole_x, hole_y in mounting_holes:
		hole_ring = (
			cq.Workplane("XY")
			.circle(hole_ring_outer_radius)
			.circle(2.2)
			.extrude(template_height)
			.translate((hole_x, hole_y, 0))
		)
		# Arm from the oval ring's outer edge to the hole ring's edge
		direction_deg = math.degrees(math.atan2(hole_y - boss_center[1], hole_x - boss_center[0]))
		edge = ellipse_radius_at_angle(
			cap_inner_semi_major + 2.0, cap_inner_semi_minor + 2.0, boss_major_axis_angle, direction_deg
		) - 0.5
		start = (
			boss_center[0] + edge * math.cos(math.radians(direction_deg)),
			boss_center[1] + edge * math.sin(math.radians(direction_deg)),
		)
		hole_distance = math.hypot(hole_x - boss_center[0], hole_y - boss_center[1])
		stop_distance = hole_distance - hole_ring_outer_radius + 0.5
		stop = (
			boss_center[0] + stop_distance * math.cos(math.radians(direction_deg)),
			boss_center[1] + stop_distance * math.sin(math.radians(direction_deg)),
		)
		arm = bar_between(start, stop, width=5.0, height=template_height)
		template = template.union(arm).union(hole_ring)
	# Keep the hole bores open after the arms were added
	for hole_x, hole_y in mounting_holes:
		bore = cq.Workplane("XY").circle(2.2).extrude(template_height).translate((hole_x, hole_y, 0))
		template = template.cut(bore)
	return template


# ============================================================
# Part 3: diffuser cap
# ============================================================

def build_diffuser_cap():
	"""Oval cup that slides over the boss and rests on the module plate. Built in assembly position."""
	outer_height = cap_inner_height + cap_top_thickness
	outer = (
		cq.Workplane("XY")
		.ellipse(
			cap_inner_semi_major + cap_wall_thickness,
			cap_inner_semi_minor + cap_wall_thickness,
			rotation_angle=boss_major_axis_angle,
		)
		.extrude(outer_height)
	)
	outer = outer.faces(">Z").edges().chamfer(1.0)
	inner = (
		cq.Workplane("XY")
		.ellipse(cap_inner_semi_major, cap_inner_semi_minor, rotation_angle=boss_major_axis_angle)
		.extrude(cap_inner_height)
	)
	cap = outer.cut(inner)

	# Wire exit notch at the rim, facing the module's connector
	notch_radius = ellipse_radius_at_angle(
		cap_inner_semi_major + cap_wall_thickness / 2,
		cap_inner_semi_minor + cap_wall_thickness / 2,
		boss_major_axis_angle,
		connector_direction_deg,
	)
	notch = (
		cq.Workplane("XY")
		.rect(cap_wall_thickness * 4, cap_wire_notch_width)
		.extrude(cap_wire_notch_height)
		.edges("|X").fillet(1.5)
		.rotate((0, 0, 0), (0, 0, 1), connector_direction_deg)
		.translate((
			notch_radius * math.cos(math.radians(connector_direction_deg)),
			notch_radius * math.sin(math.radians(connector_direction_deg)),
			-1.5,  # start below the rim so the fillet only rounds the top corners
		))
	)
	cap = cap.cut(notch)
	return cap.translate((boss_center[0], boss_center[1], 0))


# ============================================================
# Part 4: base tub
# ============================================================

def build_base_tub():
	tub = (
		cq.Workplane("XY")
		.rect(base_length, base_width)
		.extrude(base_height)
		.edges("|Z").fillet(base_corner_radius)
	)
	tub = tub.faces(">Z").shell(-base_wall_thickness)
	tub = tub.edges("<Z").chamfer(0.8)
	tub = tub.translate((base_center[0], base_center[1], 0))

	inner_x_min = base_x_min + base_wall_thickness
	inner_x_max = base_x_max - base_wall_thickness
	inner_y_min = base_y_min + base_wall_thickness
	inner_y_max = base_y_max - base_wall_thickness

	# Corner posts for the lid screws (pilot holes from the top)
	post_inset = base_wall_thickness + corner_post_size / 2 + 1.0
	corner_post_centers = [
		(base_x_min + post_inset, base_y_min + post_inset),
		(base_x_max - post_inset, base_y_min + post_inset),
		(base_x_min + post_inset, base_y_max - post_inset),
		(base_x_max - post_inset, base_y_max - post_inset),
	]
	for post_x, post_y in corner_post_centers:
		post = (
			cq.Workplane("XY")
			.rect(corner_post_size, corner_post_size)
			.extrude(base_height)
			.edges("|Z").fillet(1.5)
			.translate((post_x, post_y, 0))
		)
		pilot = (
			cq.Workplane("XY")
			.circle(corner_post_pilot_diameter / 2)
			.extrude(corner_post_pilot_depth)
			.translate((post_x, post_y, base_height - corner_post_pilot_depth))
		)
		tub = tub.union(post).cut(pilot)

	# XIAO cradle against the back wall: a pocket the board drops into
	cradle_wall = 1.6
	pocket_x = xiao_board_width + 2 * xiao_fit_clearance
	pocket_y = xiao_board_length + 2 * xiao_fit_clearance
	pocket_y_max = inner_y_max - 0.3          # USB-C end sits right at the back wall
	pocket_center_y = pocket_y_max - pocket_y / 2
	cradle_top_z = base_floor_thickness + xiao_cradle_floor_height + 1.0  # lip ~ board thickness
	cradle_block = (
		cq.Workplane("XY")
		.rect(pocket_x + 2 * cradle_wall, pocket_y + cradle_wall)
		.extrude(cradle_top_z)
		.translate((xiao_center_x, pocket_center_y - cradle_wall / 2, 0))
	)
	cradle_pocket = (
		cq.Workplane("XY")
		.rect(pocket_x, pocket_y + 2.0)
		.extrude(cradle_top_z)
		.translate((xiao_center_x, pocket_center_y + 1.0, base_floor_thickness + xiao_cradle_floor_height))
	)
	tub = tub.union(cradle_block).cut(cradle_pocket)

	# USB-C port through the back wall, centered on the XIAO's connector
	usb_center_z = base_floor_thickness + xiao_cradle_floor_height + 1.0 + 1.6
	usb_slot = (
		cq.Workplane("XZ")
		.center(xiao_center_x, usb_center_z)
		.rect(usb_slot_width, usb_slot_height)
		.extrude(-(base_wall_thickness + 2))
		.edges("|Y").fillet(2.5)
		.translate((0, inner_y_max - 1, 0))
	)
	usb_recess = (
		cq.Workplane("XZ")
		.center(xiao_center_x, usb_center_z)
		.rect(usb_recess_width, usb_recess_height)
		.extrude(-(usb_recess_depth + 0.01))
		.edges("|Y").fillet(3.0)
		.translate((0, base_y_max - usb_recess_depth, 0))
	)
	tub = tub.cut(usb_slot).cut(usb_recess)

	# Mode button: actuator hole in the front wall + a square pocket behind it for the 6x6 switch body
	button_hole = (
		cq.Workplane("XZ")
		.center(button_center_x, button_center_z)
		.circle(button_actuator_hole_diameter / 2)
		.extrude(-(base_wall_thickness + 2))
		.translate((0, base_y_min - 1, 0))
	)
	button_holder = (
		cq.Workplane("XZ")
		.center(button_center_x, button_center_z)
		.rect(10.0, 10.0)
		.extrude(-3.5)
		.translate((0, inner_y_min, 0))
	)
	button_pocket = (
		cq.Workplane("XZ")
		.center(button_center_x, button_center_z)
		.rect(6.3, 6.3)
		.extrude(-3.5)
		.translate((0, inner_y_min, 0))
	)
	tub = tub.union(button_holder).cut(button_pocket).cut(button_hole)

	# Hex vents in both end walls (X-) and (X+)
	vent_v_min, vent_v_max = 8.0, base_height - 6.0
	end_wall_vents = hex_grid(inner_y_min + 10, inner_y_max - 10, vent_v_min, vent_v_max)
	left_cutter = hex_vent_cutter("YZ", end_wall_vents, base_wall_thickness + 2, base_x_min - 1)
	right_cutter = hex_vent_cutter("YZ", end_wall_vents, base_wall_thickness + 2, base_x_max - base_wall_thickness - 1)
	tub = tub.cut(left_cutter).cut(right_cutter)

	# Hex vents in the front wall, on either side of the button
	front_vents = [
		center for center in hex_grid(inner_x_min + 14, inner_x_max - 14, vent_v_min, vent_v_max)
		if abs(center[0] - button_center_x) > 12
	]
	# The XZ workplane's normal points toward -Y, so start just inside the wall and extrude outward
	front_cutter = hex_vent_cutter("XZ", front_vents, base_wall_thickness + 2, -(base_y_min + base_wall_thickness + 1))
	tub = tub.cut(front_cutter)

	# Decorative groove around the tub, cyberpunk panel-line style
	groove_z = 7.0
	groove_outer = (
		cq.Workplane("XY")
		.rect(base_length + 2, base_width + 2)
		.extrude(1.2)
		.translate((base_center[0], base_center[1], groove_z))
	)
	groove_keep = (
		cq.Workplane("XY")
		.rect(base_length - 1.2, base_width - 1.2)
		.extrude(1.2)
		.edges("|Z").fillet(base_corner_radius - 0.6)
		.translate((base_center[0], base_center[1], groove_z))
	)
	tub = tub.cut(groove_outer.cut(groove_keep))
	return tub


# ============================================================
# Part 5: base lid with module standoffs
# ============================================================

def build_base_lid():
	lid = (
		cq.Workplane("XY")
		.rect(base_length, base_width)
		.extrude(lid_thickness)
		.edges("|Z").fillet(base_corner_radius)
	)
	lid = lid.faces(">Z").edges().chamfer(0.8)
	lid = lid.translate((base_center[0], base_center[1], base_height))

	# Lid screw holes over the corner posts
	post_inset = base_wall_thickness + corner_post_size / 2 + 1.0
	for corner_x, corner_y in [
		(base_x_min + post_inset, base_y_min + post_inset),
		(base_x_max - post_inset, base_y_min + post_inset),
		(base_x_min + post_inset, base_y_max - post_inset),
		(base_x_max - post_inset, base_y_max - post_inset),
	]:
		screw_hole = (
			cq.Workplane("XY")
			.circle(lid_screw_clearance_diameter / 2)
			.extrude(lid_thickness + 2)
			.translate((corner_x, corner_y, base_height - 1))
		)
		lid = lid.cut(screw_hole)

	# Hex vent field under the module, keeping solid rings around the standoffs
	vent_centers = [
		center for center in hex_grid(-42.0, 58.0, 2.0, 50.0)
		if all(math.hypot(center[0] - hx, center[1] - hy) > standoff_outer_diameter / 2 + 5 for hx, hy in mounting_holes)
	]
	vent_cutter = hex_vent_cutter("XY", vent_centers, lid_thickness + 2, base_height - 1)
	lid = lid.cut(vent_cutter)

	# Wire slot where the LED wires drop down past the plate edge
	wire_slot = (
		cq.Workplane("XY")
		.slot2D(lid_wire_slot_size[0], lid_wire_slot_size[1])
		.extrude(lid_thickness + 2)
		.translate((lid_wire_slot_center[0], lid_wire_slot_center[1], base_height - 1))
	)
	lid = lid.cut(wire_slot)

	# Standoffs up to the module's mounting holes, with pilot holes for the original screws
	for hole_x, hole_y in mounting_holes:
		standoff = (
			cq.Workplane("XY")
			.circle(standoff_outer_diameter / 2)
			.extrude(standoff_height)
			.translate((hole_x, hole_y, base_height + lid_thickness))
		)
		# Wider foot so the standoff doesn't snap off at the lid
		foot = (
			cq.Workplane("XY")
			.circle(standoff_outer_diameter / 2 + 2.5)
			.workplane(offset=4.0)
			.circle(standoff_outer_diameter / 2)
			.loft()
			.translate((hole_x, hole_y, base_height + lid_thickness))
		)
		pilot = (
			cq.Workplane("XY")
			.circle(module_screw_pilot_diameter / 2)
			.extrude(module_screw_pilot_depth)
			.translate((hole_x, hole_y, module_plate_bottom_z - module_screw_pilot_depth))
		)
		lid = lid.union(standoff).union(foot).cut(pilot)
	return lid


# ============================================================
# Module proxy (for assembly renders only — not printed)
# ============================================================

def build_module_proxy():
	"""Rough stand-in for the LED module: plate outline (convex hull), boss, and back fin block."""
	outline_points = []
	for corner in module["fin_block_corners_mm"]:
		outline_points.append(corner)
	for point in module["right_edge_points_mm"]:
		outline_points.append(point)
	for hole_x, hole_y in mounting_holes:
		for angle in range(0, 360, 20):
			outline_points.append((hole_x + 4.5 * math.cos(math.radians(angle)), hole_y + 4.5 * math.sin(math.radians(angle))))
	for angle in range(0, 360, 10):
		radius = ellipse_radius_at_angle(boss_major_diameter / 2 + 3, boss_minor_diameter / 2 + 3, boss_major_axis_angle, angle)
		outline_points.append((boss_center[0] + radius * math.cos(math.radians(angle)), boss_center[1] + radius * math.sin(math.radians(angle))))
	points = np.array(outline_points)
	hull = ConvexHull(points)
	hull_outline = [tuple(points[i]) for i in hull.vertices]

	plate = cq.Workplane("XY").polyline(hull_outline).close().extrude(plate_thickness)
	for hole_x, hole_y in mounting_holes:
		plate = plate.cut(cq.Workplane("XY").circle(2.0).extrude(plate_thickness).translate((hole_x, hole_y, 0)))
	# Boss height (11.9 mm) is measured from the plate's top surface
	boss = (
		cq.Workplane("XY")
		.ellipse(boss_major_diameter / 2, boss_minor_diameter / 2, rotation_angle=boss_major_axis_angle)
		.extrude(boss_height_above_plate)
		.translate((boss_center[0], boss_center[1], plate_thickness))
	)
	# Back fins: rough block, ~27 mm deep. Real footprint near the holes is unverified —
	# the fit-test template and a dry fit on the standoffs will confirm clearance.
	back_block = (
		cq.Workplane("XY")
		.rect(100.0, 42.0)
		.extrude(27.0)
		.translate((3.0, 28.0, -27.0))
	)
	proxy = plate.union(boss).union(back_block)
	return proxy.translate((0, 0, module_plate_bottom_z))


# ============================================================
# Export
# ============================================================

def export_part(workplane, name, print_rotation=None):
	"""Write STL + 3MF + STEP. print_rotation=(axis, degrees) puts the part in print orientation."""
	shape = workplane
	if print_rotation is not None:
		axis, degrees = print_rotation
		shape = shape.rotate((0, 0, 0), axis, degrees)
	# Drop onto the build plate at Z=0
	bounding_box = shape.val().BoundingBox()
	shape = shape.translate((0, 0, -bounding_box.zmin))
	for extension in ("stl", "3mf", "step"):
		cq.exporters.export(shape, str(OUTPUT_DIRECTORY / f"{name}.{extension}"))
	return shape


def main():
	OUTPUT_DIRECTORY.mkdir(exist_ok=True)

	fit_rings = build_fit_test_rings()
	fit_template = build_fit_test_template()
	diffuser_cap = build_diffuser_cap()
	base_tub = build_base_tub()
	base_lid = build_base_lid()

	export_part(fit_rings, "01_fit_test_rings")
	export_part(fit_template, "02_fit_test_template")
	# Cap prints upside down (closed top on the textured plate = frosted face, no supports)
	export_part(diffuser_cap, "03_diffuser_cap", print_rotation=((1, 0, 0), 180))
	export_part(base_tub, "04_base_tub")
	export_part(base_lid, "05_base_lid")

	# Assembly (STEP only) for viewing in Fusion
	cap_on_module = diffuser_cap.translate((0, 0, module_plate_bottom_z + plate_thickness))
	assembly = (
		cq.Assembly(name="cyberlamp")
		.add(base_tub, name="base_tub", color=cq.Color(0.15, 0.15, 0.17))
		.add(base_lid, name="base_lid", color=cq.Color(0.2, 0.2, 0.22))
		.add(build_module_proxy(), name="led_module_proxy", color=cq.Color(0.75, 0.75, 0.78))
		.add(cap_on_module, name="diffuser_cap", color=cq.Color(1.0, 0.65, 0.2))
	)
	assembly.save(str(OUTPUT_DIRECTORY / "00_assembly.step"))

	print("Module plate sits", round(module_plate_bottom_z, 1), "mm above the desk")
	print("Overall height ≈", round(module_plate_bottom_z + plate_thickness + cap_inner_height + cap_top_thickness, 1), "mm")


if __name__ == "__main__":
	main()
