"""Compare the local KdU cap and the statutory fallback against market rents.

Both modules read the Zensus 2022 rents of each Gemeinde's rented housing
stock, which is the only rent measurement available at the resolution at
which the caps themselves vary.

- {mod}`kdu.market_rent_comparison.market_rent_correlation` asks whether
  either cap tracks the local rent level.
- {mod}`kdu.market_rent_comparison.share_of_stock_above_cap` asks how much
  of the local rented stock each cap places beyond reach.
"""
