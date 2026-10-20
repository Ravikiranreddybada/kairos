# Inventory Policy (v3.2)

Owner: Supply Planning. Applies to all stores and distribution centres.

## Service level targets

Cycle service level (CSL) targets are set by ABC class.
A-class SKUs (top 20% of revenue) target 98% CSL.
B-class SKUs target 95% CSL.
C-class SKUs and intermittent items target 90% CSL.
Festival weeks (Diwali window, plus or minus 7 days) raise every class by one step, capped at 99%.

## Safety stock method

Safety stock must account for both demand uncertainty and supplier lead-time variability.
Planners must use the combined formula: SS = z x sqrt(L x sigma_d^2 + d^2 x sigma_L^2).
Using demand variability alone is not allowed for suppliers with on-time rate below 90%.

## Reorder rules

An order is triggered when inventory position (on hand plus on order) falls to or below the reorder point.
Order quantity is the largest of the supplier minimum order quantity, the economic order quantity, and the gap to the target level.
Orders above 5x the average weekly demand need approval from the category manager.

## Excess and obsolete stock

Stock with more than 90 days of cover is flagged as excess.
Intermittent SKUs with no sale in 120 days are reviewed for delisting.
