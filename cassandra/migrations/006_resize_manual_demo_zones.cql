USE warehouse;

UPDATE zones_by_id
SET zone_name = 'Inbound / Picking Zone A',
    capacity = 10000,
    updated_at = toTimestamp(now())
WHERE zone_id = 'ZONE-A';

UPDATE zones_by_id
SET zone_name = 'Reserve Zone B',
    capacity = 10000,
    updated_at = toTimestamp(now())
WHERE zone_id = 'ZONE-B';

UPDATE zones_by_id
SET zone_name = 'Inventory Audit Zone C',
    capacity = 8000,
    updated_at = toTimestamp(now())
WHERE zone_id = 'ZONE-C';
