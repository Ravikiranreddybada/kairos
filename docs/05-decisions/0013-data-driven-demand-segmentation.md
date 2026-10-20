# ADR-0013: Data-driven demand segmentation (ADI / CV²)

Status: Accepted · Date: 2026-10-18

## Context

Model selection runs per segment (regular vs intermittent). The segment came from `dim_sku.is_intermittent`, a label the synthetic generator writes. Real retail data has no such column, so the pipeline would not run on client data, and the GBM used the same label as a feature – a quiet leak of generator truth into the model.

## Decision

Classify every store × SKU series from its own history with the Syntetos–Boylan–Croston (2005) scheme: ADI = observed days / days with demand, CV² = squared coefficient of variation of non-zero sizes, cut-offs 1.32 and 0.49 → smooth / erratic / intermittent / lumpy (`forecasting/segmentation.py`). Smooth + erratic select as "regular", intermittent + lumpy as "intermittent". Stockout days are excluded (censored demand, ADR-0004). The label is removed from GBM features; `roll_zero_share_28` carries the same signal from data. Patterns are saved in the run manifest and shown on the model card.

## Consequences

+ Pipeline needs only data a retailer has. Segment is per series, not per SKU (one SKU can be smooth in a big store and intermittent in a small one).
+ Tested: four textbook series classify correctly; data-driven segments agree ≥ 90% with the generator's truth; stockout zeros do not create false intermittency.
+ Removing the label did not cost accuracy: WAPE 0.325 → 0.324, MASE 0.728 → 0.726.
− Cut-offs are published defaults, not tuned to this client; revisit with real data.

## Alternatives considered

Keep master-data flag (rejected: not available, leaks); k-means on demand features (rejected for selection: clusters have no stable meaning across retrains, ADI/CV² is the standard planners recognise).
