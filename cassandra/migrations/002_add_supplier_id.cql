USE warehouse;

ALTER TABLE inventory_by_product_zone ADD supplier_id text;
ALTER TABLE inventory_by_product ADD supplier_id text;
ALTER TABLE inventory_by_zone ADD supplier_id text;
