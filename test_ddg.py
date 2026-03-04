import re

title = "SUNLU PETG Filament Refill 1.75mm 4KG, High Speed 3D Printer Filament Matte PETG Refill, No-Spool Filament Bundles for Reusable Spools Compatible with Bambu Labs, Pink/Orange/Yellow/Green 1KG/Roll"
title_upper = title.upper()
print(f"Title: {title}")

# 3. Weight Regex Parsing
weight = 1000 # Default fallback
multipack = 1

# Try to look for total weight first e.g. "4KG"
total_match = re.search(r'(\d+(?:\.\d+)?)\s*KG', title_upper)
if total_match:
    val = float(total_match.group(1))
    if val >= 1.0 and val <= 10.0:
        weight = val * 1000.0

# If we still think it's 1000, check if we found multipack keywords
if weight == 1000:
    mp_match = re.search(r'(\d+)\s*(?:pk|pack|rolls|spools|kg/roll)', title_upper)
    if mp_match:
        try: 
            multipack = int(mp_match.group(1))
            weight = 1000 * multipack
        except ValueError: 
            pass

print(f"Calculated Weight: {weight}g")
