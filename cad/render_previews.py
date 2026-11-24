"""
render_previews.py — shaded PNG previews of the CyberRunningLamp parts.

Run after installing CadQuery (which brings VTK along):

	python3 render_previews.py

On a machine without a display (CI, a server), wrap it in a virtual one:

	xvfb-run -a python3 render_previews.py

Writes PNGs into ./renders/.
"""

import tempfile
from pathlib import Path

import cadquery as cq
import vtk

import cyberlamp_housing as housing

RENDER_DIRECTORY = Path(__file__).resolve().parent / "renders"


def actor_from_workplane(workplane, color, opacity=1.0):
	"""Exports a CadQuery object to a temporary STL and wraps it in a smooth-shaded VTK actor."""
	with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as temporary_file:
		stl_path = temporary_file.name
	cq.exporters.export(workplane, stl_path, tolerance=0.05, angularTolerance=0.1)
	reader = vtk.vtkSTLReader()
	reader.SetFileName(stl_path)
	# Recompute normals with a feature angle so sharp edges stay crisp and curves look smooth
	normals = vtk.vtkPolyDataNormals()
	normals.SetInputConnection(reader.GetOutputPort())
	normals.SetFeatureAngle(35)
	normals.SplittingOn()
	mapper = vtk.vtkPolyDataMapper()
	mapper.SetInputConnection(normals.GetOutputPort())
	actor = vtk.vtkActor()
	actor.SetMapper(mapper)
	surface = actor.GetProperty()
	surface.SetColor(*color)
	surface.SetOpacity(opacity)
	surface.SetSpecular(0.25)
	surface.SetSpecularPower(25)
	return actor


def render(parts_with_colors, filename, camera_direction, elevation_up=(0, 0, 1), zoom=1.0):
	"""Renders parts from a direction vector (pointing from the object toward the camera)."""
	renderer = vtk.vtkRenderer()
	renderer.SetBackground(0.96, 0.96, 0.97)
	for part in parts_with_colors:
		workplane, color = part[0], part[1]
		opacity = part[2] if len(part) > 2 else 1.0
		renderer.AddActor(actor_from_workplane(workplane, color, opacity))

	# Soft two-light setup: key light plus a dim fill so shadowed sides stay readable
	renderer.RemoveAllLights()
	key_light = vtk.vtkLight()
	key_light.SetLightTypeToCameraLight()
	key_light.SetPosition(0.6, 1.0, 1.0)
	key_light.SetIntensity(0.9)
	fill_light = vtk.vtkLight()
	fill_light.SetLightTypeToCameraLight()
	fill_light.SetPosition(-1.0, -0.3, 0.5)
	fill_light.SetIntensity(0.4)
	renderer.AddLight(key_light)
	renderer.AddLight(fill_light)

	renderer.ResetCamera()
	camera = renderer.GetActiveCamera()
	focal_point = camera.GetFocalPoint()
	distance = camera.GetDistance()
	camera.SetPosition(*(focal_point[i] + camera_direction[i] * distance for i in range(3)))
	camera.SetViewUp(*elevation_up)
	renderer.ResetCamera()
	camera.Zoom(zoom)

	window = vtk.vtkRenderWindow()
	window.SetOffScreenRendering(1)
	window.SetSize(1200, 900)
	window.SetMultiSamples(8)
	window.AddRenderer(renderer)
	window.Render()

	image_filter = vtk.vtkWindowToImageFilter()
	image_filter.SetInput(window)
	image_filter.Update()
	writer = vtk.vtkPNGWriter()
	writer.SetFileName(str(RENDER_DIRECTORY / filename))
	writer.SetInputConnection(image_filter.GetOutputPort())
	writer.Write()


def main():
	RENDER_DIRECTORY.mkdir(exist_ok=True)

	tub = housing.build_base_tub()
	lid = housing.build_base_lid()
	cap = housing.build_diffuser_cap()
	cap_in_place = cap.translate((0, 0, housing.module_plate_bottom_z + housing.plate_thickness))
	module_proxy = housing.build_module_proxy()

	dark_body = (0.22, 0.23, 0.26)
	lid_color = (0.30, 0.31, 0.35)
	aluminum = (0.80, 0.81, 0.84)
	amber_glow = (1.0, 0.62, 0.18)

	assembly = [(tub, dark_body), (lid, lid_color), (module_proxy, aluminum, 0.55), (cap_in_place, amber_glow)]
	render(assembly, "assembly_front.png", camera_direction=(0.55, -1.0, 0.55), zoom=1.15)
	render(assembly, "assembly_back.png", camera_direction=(-0.45, 1.0, 0.45), zoom=1.15)
	render([(tub, dark_body)], "base_tub.png", camera_direction=(0.35, -0.6, 1.0), zoom=1.2)
	boost_proxy, perfboard_proxy, xiao_proxy = housing.build_electronics_proxies()
	render(
		[(tub, dark_body), (boost_proxy, (0.85, 0.15, 0.15)), (perfboard_proxy, (0.15, 0.6, 0.3)), (xiao_proxy, (0.2, 0.45, 0.9))],
		"base_interior_layout.png", camera_direction=(0.0, -0.35, 1.0), elevation_up=(0, 1, 0), zoom=1.25,
	)
	render([(lid, lid_color)], "base_lid.png", camera_direction=(0.5, -0.9, 0.7), zoom=1.15)
	render([(cap, amber_glow)], "diffuser_cap.png", camera_direction=(-0.9, -0.7, -0.35), zoom=1.1)
	render(
		[(housing.build_fit_test_template(), (0.2, 0.5, 0.85)), (housing.build_fit_test_rings().translate((-60, -70, 0)), (0.9, 0.45, 0.1))],
		"fit_tests.png", camera_direction=(0.0, -0.5, 1.0), zoom=1.2,
	)


if __name__ == "__main__":
	main()
