# Public MCP Tool Inventory

The authoritative registry contains exactly 53 public tools. The names and
order below mirror `src/freecad_mcp/tool_registry.py`; repository consistency
tests prevent the registry, runtime registration, and this inventory from
drifting apart.

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
22. `analyze_sketch`
23. `validate_sketch_profile`
24. `list_sketch_open_vertices`
25. `add_external_geometry`
26. `list_external_geometry`
27. `remove_external_geometry`
28. `get_sketch_dependencies`
29. `remove_sketch_constraints`
30. `remove_sketch_geometry`
31. `set_sketch_geometry_construction`
32. `update_sketch_geometry`
33. `replace_sketch_constraint`
34. `update_sketch_constraint_value`
35. `add_sketch_reference_constraints`
36. `set_sketch_constraint_name`
37. `set_sketch_constraint_expression`
38. `clear_sketch_constraint_expression`
39. `list_sketch_constraint_expressions`
40. `trim_sketch_geometry`
41. `split_sketch_geometry`
42. `extend_sketch_geometry`
43. `chamfer_sketch_geometry`
44. `fillet_sketch_geometry`
45. `mirror_sketch_geometry`
46. `translate_sketch_geometry`
47. `rotate_sketch_geometry`
48. `scale_sketch_geometry`
49. `rectangular_array_sketch_geometry`
50. `polar_array_sketch_geometry`
51. `set_sketch_constraint_driving`
52. `set_sketch_constraint_active`
53. `set_sketch_constraint_virtual_space`

## Deferred

`offset_sketch_geometry` is not exposed. FreeCAD 1.1 does not provide a
headless Sketcher offset API; the GUI command uses OpenCASCADE internally and
has no supported Python binding. Implementing offset would require a separate
research and contract milestone built on Part/OCC offset operations — it is
not a thin native adapter.
