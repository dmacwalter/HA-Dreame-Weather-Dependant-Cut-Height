# Legacy: the YAML package

The first version of this project: a Home Assistant package
(`packages/dreame_cut_height.yaml`) with Jinja macros (`custom_templates/cut_height.jinja`),
input helpers and three automations. It has been replaced by the integration in
`custom_components/dreame_smart_cut_height`, which makes the same decisions and imports
the package's helpers the first time it starts. See "Moving from the YAML package" in
the main README.

Kept for reference only; it is not updated.
