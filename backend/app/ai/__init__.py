"""AI at the edges (project document, section 4.8).

Models only read free-text letters (CF9), answer questions over results views
(AF7) and reword a finished explanation (AF8). No model produces or changes a
figure: every number comes from SQL in Exasol, and the calculation path never
imports this package (tests/test_ai_boundary.py proves it).
"""
