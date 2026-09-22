"""Builds reference.default.json from the POI CAMERA INSTALLATION TABLE image (transcribed row by row: distance, 6°, 7°, 8°)."""
import json
ROWS = [
 (0,1.6,1.6,1.6),(1,1.7,1.7,1.7),(2,1.8,1.8,1.9),(3,1.9,2.0,2.0),(4,2.0,2.1,2.2),(5,2.1,2.2,2.3),(6,2.2,2.3,2.4),
 (7,2.3,2.5,2.6),(8,2.4,2.6,2.7),(9,2.5,2.7,2.9),(10,2.6,2.8,3.0),(11,2.7,3.0,3.1),(12,2.8,3.1,3.3),(13,2.9,3.2,3.4),
 (14,3.0,3.3,3.6),(15,3.1,3.4,3.7),(16,3.2,3.6,3.8),(17,3.3,3.7,4.0),(18,3.4,3.8,4.1),(19,3.5,3.9,4.3),(20,3.6,4.1,4.4),
 (21,3.7,4.2,4.6),(22,3.8,4.3,4.7),(23,3.9,4.4,4.8),(24,4.0,4.5,5.0),(25,4.1,4.7,5.1)]
ref = {
 "version": 1, "updated": "",
 "angles": [6, 7, 8], "default_angle": 6,
 "height_table": [{"distance": d, "height": {"6": a, "7": b, "8": c}} for d, a, b, c in ROWS],
 "lens_ranges": [{"min": 1.3, "max": 3.1, "lens": "PLZ20C0-D"}, {"min": 3.2, "max": 8.9, "lens": "PLZ21C0-D"}, {"min": 9, "max": 25, "lens": "PFL1575-A-12D"}],
 "rules": {"fractional_distance": "ceil"},
 "poi_table_footnote": "The average eye level height of a standing person is 160 cm",
 "report_options": {"include_poi_table": False},
 "camera_models": ["IPC-HF7442F-Z-X"],
 "install_types": ["Wall Mount", "Ceiling Mount", "Pendant"],
 "environments": ["Indoor", "Outdoor"],
 "vendors": ["DAHUA"], "default_vendor": "DAHUA",
 "categories": ["Fast-food", "Restaurant / cafe", "Supermarket", "Retail shop", "Jewellery", "Pharmacy", "Bank / exchange", "Hotel", "Office", "Warehouse", "Other"],
 "nvr_defaults": [
   {"device_type": "IVD", "model": "DHI-IVD5148-1I-4G/WT", "description": "1U INTELLIGENT VIDEO DEVICE (HDD)", "qty": 1},
   {"device_type": "HDD", "model": "4TB SURVEILLANCE HDD", "description": "4TB SURVEILLANCE Hard Disk (Any MOI-SSD approved model)", "qty": 1}]}
json.dump(ref, open('reference.default.json', 'w'), indent=1, ensure_ascii=False)
print(len(ROWS), 'rows written')
