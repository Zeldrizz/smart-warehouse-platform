USE warehouse;

UPDATE zones_by_id
SET zone_name = 'Synthetic Traffic Zone A',
    capacity = 30000,
    updated_at = toTimestamp(now())
WHERE zone_id = 'ZONE-LIVE-A';

UPDATE zones_by_id
SET zone_name = 'Synthetic Traffic Zone B',
    capacity = 30000,
    updated_at = toTimestamp(now())
WHERE zone_id = 'ZONE-LIVE-B';

UPDATE zones_by_id
SET zone_name = 'Synthetic Traffic Zone C',
    capacity = 20000,
    updated_at = toTimestamp(now())
WHERE zone_id = 'ZONE-LIVE-C';
