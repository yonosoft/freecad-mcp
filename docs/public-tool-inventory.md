# Public MCP Tool Inventory

The structured catalogue under `src/freecad_mcp/catalog/` contains
exactly 59 public tools, each with one complete definition. The numbered list
below is the
unchanged legacy MCP wire order derived as `REGISTERED_TOOL_NAMES`; it is
intentionally distinct from the catalogue's human-readable logical order.
Catalogue groups and sections are metadata only: all 59 tools remain visible,
with no runtime filtering. Repository consistency tests prevent the catalogue,
runtime registration, and this inventory from drifting apart.

1. `create_document`
2. `list_documents`
3. `get_document`
4. `save_document`
5. `list_objects`
6. `get_object`
7. `recompute_document`
8. `create_body`
9. `create_sketch`
10. `get_sketch`
11. `add_sketch_geometry`
12. `add_sketch_constraints`
13. `get_document_history`
14. `undo_document`
15. `redo_document`
16. `create_sketch_rectangle`
17. `create_sketch_centered_rectangle`
18. `create_sketch_equilateral_triangle`
19. `create_sketch_regular_polygon`
20. `create_sketch_slot`
21. `create_sketch_rounded_rectangle`
22. `create_sketch_polyline`
23. `analyze_sketch`
24. `validate_sketch_profile`
25. `list_sketch_open_vertices`
26. `add_external_geometry`
27. `list_external_geometry`
28. `remove_external_geometry`
29. `get_sketch_dependencies`
30. `remove_sketch_constraints`
31. `remove_sketch_geometry`
32. `set_sketch_geometry_construction`
33. `update_sketch_geometry`
34. `replace_sketch_constraint`
35. `update_sketch_constraint_value`
36. `add_sketch_reference_constraints`
37. `set_sketch_constraint_name`
38. `set_sketch_constraint_expression`
39. `clear_sketch_constraint_expression`
40. `list_sketch_constraint_expressions`
41. `trim_sketch_geometry`
42. `split_sketch_geometry`
43. `extend_sketch_geometry`
44. `chamfer_sketch_geometry`
45. `fillet_sketch_geometry`
46. `mirror_sketch_geometry`
47. `translate_sketch_geometry`
48. `rotate_sketch_geometry`
49. `scale_sketch_geometry`
50. `rectangular_array_sketch_geometry`
51. `polar_array_sketch_geometry`
52. `set_sketch_constraint_driving`
53. `set_sketch_constraint_active`
54. `set_sketch_constraint_virtual_space`
55. `translate_sketch`
56. `rotate_sketch`
57. `scale_sketch`
58. `mirror_sketch`
59. `analyze_sketch_constraints`

## Deferred

### `analyze_sketch_constraints`

Read-only constraint and solver diagnostics. Accepts `document_name` and `sketch_name`. Returns structured solver state, eight deterministic classifications, constraint-state counts, and ordered issues with zero-based constraint indices. Each issue includes non-binding candidate repair actions using existing tools. Never recomputes, modifies the sketch, opens transactions, consumes history, or saves.

`offset_sketch_geometry` is not exposed. FreeCAD 1.1 does not provide a
headless Sketcher offset API; the GUI command uses OpenCASCADE internally and
has no supported Python binding. Implementing offset would require a separate
research and contract milestone built on Part/OCC offset operations — it is
not a thin native adapter.
