USE warehouse;

INSERT INTO zones_by_id (zone_id, zone_name, capacity, created_at, updated_at)
VALUES ('ZONE-LIVE-A', 'Synthetic Traffic Zone A', 500, toTimestamp(now()), toTimestamp(now()));

INSERT INTO zones_by_id (zone_id, zone_name, capacity, created_at, updated_at)
VALUES ('ZONE-LIVE-B', 'Synthetic Traffic Zone B', 500, toTimestamp(now()), toTimestamp(now()));

INSERT INTO zones_by_id (zone_id, zone_name, capacity, created_at, updated_at)
VALUES ('ZONE-LIVE-C', 'Synthetic Traffic Zone C', 300, toTimestamp(now()), toTimestamp(now()));
