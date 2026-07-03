-- Initial data for Vision Retail AI
SET search_path TO vision_retail, public;

-- Insert store
INSERT INTO stores (store_code, store_name, city, country, layout_file_path)
VALUES ('brigade-bangalore', 'Brigade Road - Bangalore', 'Bangalore', 'India', '/data/Brigade Road - Store layout.xlsx')
ON CONFLICT (store_code) DO NOTHING;

-- Get store ID for use in inserts
WITH store_data AS (
    SELECT id FROM stores WHERE store_code = 'brigade-bangalore' LIMIT 1
)

-- Insert cameras
INSERT INTO cameras (store_id, camera_code, camera_name, camera_type, status)
SELECT id, 'CAM-1', 'Entry Camera', 'entry', 'active' FROM store_data
UNION ALL
SELECT id, 'CAM-2', 'Floor Camera 1', 'floor', 'active' FROM store_data
UNION ALL
SELECT id, 'CAM-3', 'Floor Camera 2', 'floor', 'active' FROM store_data
UNION ALL
SELECT id, 'CAM-4', 'Billing Camera 1', 'billing', 'active' FROM store_data
UNION ALL
SELECT id, 'CAM-5', 'Billing Camera 2', 'billing', 'active' FROM store_data
ON CONFLICT (store_id, camera_code) DO NOTHING;

-- Insert zones (example structure - adjust based on actual store layout)
WITH store_data AS (
    SELECT id FROM stores WHERE store_code = 'brigade-bangalore' LIMIT 1
)
INSERT INTO zones (store_id, zone_code, zone_name, zone_type)
SELECT id, 'entry', 'Entry Foyer', 'entry' FROM store_data
UNION ALL
SELECT id, 'skincare', 'Skincare Section', 'floor' FROM store_data
UNION ALL
SELECT id, 'makeup', 'Makeup Section', 'floor' FROM store_data
UNION ALL
SELECT id, 'haircare', 'Haircare Section', 'floor' FROM store_data
UNION ALL
SELECT id, 'billing', 'Billing Counter', 'billing' FROM store_data
ON CONFLICT (store_id, zone_code) DO NOTHING;
