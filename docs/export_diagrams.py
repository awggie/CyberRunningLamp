"""
Exports the two diagrams in docs/wiring.html as standalone SVG files so the README
can show them on GitHub (which won't render the HTML page).

wiring.html is the source of truth. After editing a diagram there, run:
	python3 docs/export_diagrams.py

Each SVG gets the page's light-theme colors and a white background, so it reads the
same in GitHub's light and dark themes.
"""

import re
from pathlib import Path

docs_dir = Path(__file__).resolve().parent
page_html = (docs_dir / "wiring.html").read_text(encoding="utf-8")

# Output file names, in the order the <svg> elements appear in the page.
output_names = ["wiring-system.svg", "wiring-channel.svg"]

# Light-theme tokens: the bare :root block at the top of the page's <style>.
root_tokens = re.search(r":root\s*\{(.*?)\}", page_html, re.S).group(1)
# The SVG rules: everything from the "SVG styling" comment to the end of the style block.
svg_rules = re.search(r"/\* SVG styling via tokens \*/(.*?)</style>", page_html, re.S).group(1)
# Standalone SVGs can't load the page's web fonts, so name system fonts directly.
root_tokens = re.sub(r"--sans:[^;]*;", '--sans: "IBM Plex Sans", -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;', root_tokens)
root_tokens = re.sub(r"--mono:[^;]*;", '--mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;', root_tokens)
# Inside a standalone SVG, selectors like "svg text" still match; tokens live on the root <svg>.
embedded_style = f"svg {{{root_tokens}}}\n{svg_rules}"

svg_blocks = re.findall(r"<svg\b.*?</svg>", page_html, re.S)
if len(svg_blocks) != len(output_names):
	raise SystemExit(f"Expected {len(output_names)} diagrams in wiring.html, found {len(svg_blocks)}")

for svg_markup, output_name in zip(svg_blocks, output_names):
	view_box = re.search(r'viewBox="([^"]+)"', svg_markup).group(1)
	_, _, view_width, view_height = view_box.split()
	opening_tag_end = svg_markup.index(">") + 1
	opening_tag = svg_markup[:opening_tag_end].replace(
		"<svg ", f'<svg xmlns="http://www.w3.org/2000/svg" width="{view_width}" height="{view_height}" ', 1
	)
	standalone_svg = (
		opening_tag
		+ f"\n<style>{embedded_style}</style>"
		+ f'\n<rect x="0" y="0" width="{view_width}" height="{view_height}" fill="#ffffff"/>'
		+ svg_markup[opening_tag_end:]
		+ "\n"
	)
	(docs_dir / output_name).write_text(standalone_svg, encoding="utf-8")
	print(f"wrote docs/{output_name}")
