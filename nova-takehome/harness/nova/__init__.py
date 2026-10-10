"""Nova: freight invoice audit harness.

Pipeline: reader (eml -> text pages, OCR for scans) -> docs (classify + parse each document by what it says) ->
world (everything held on the report date) -> detect (the six classes, conflicts, missing documents) ->
report (actions per mode, confidence, supersedes / retro / learned_at). The model is only a fallback reader.
"""
