-- OFFLINE COMPILE ONLY (no server, no driver). Branch 0450c20.
-- Fresh install (models):
CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	entity_type VARCHAR(50) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	action VARCHAR(50) NOT NULL, 
	before_state JSON, 
	after_state JSON, 
	staff_user_id INTEGER, 
	ip_address VARCHAR(45), 
	timestamp TIMESTAMP WITHOUT TIME ZONE, 
	actor_kind VARCHAR(10) DEFAULT 'HUMAN' NOT NULL, 
	actor_mechanism VARCHAR(64), 
	actor_role VARCHAR(20), 
	actor_shift_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_audit_actor_kind CHECK (actor_kind IN ('HUMAN','SYSTEM')), 
	CONSTRAINT ck_audit_actor_identity CHECK ((actor_kind = 'HUMAN' AND staff_user_id IS NOT NULL) OR (actor_kind = 'SYSTEM' AND staff_user_id IS NULL AND actor_mechanism IS NOT NULL)), 
	CONSTRAINT ck_audit_actor_not_zero CHECK (staff_user_id IS NULL OR staff_user_id > 0), 
	FOREIGN KEY(staff_user_id) REFERENCES users (id), 
	FOREIGN KEY(actor_shift_id) REFERENCES shifts (id)
);

-- Migration 10.0.0 on an existing PostgreSQL database:
ALTER TABLE audit_logs ADD COLUMN actor_kind VARCHAR(10) DEFAULT 'HUMAN' NOT NULL;
ALTER TABLE audit_logs ADD COLUMN actor_mechanism VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN actor_role VARCHAR(20);
ALTER TABLE audit_logs ADD COLUMN actor_shift_id INTEGER REFERENCES shifts(id);
ALTER TABLE audit_logs ALTER COLUMN staff_user_id DROP NOT NULL;
ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_actor_kind CHECK (actor_kind IN ('HUMAN','SYSTEM'));
ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_actor_identity CHECK ((actor_kind = 'HUMAN' AND staff_user_id IS NOT NULL) OR (actor_kind = 'SYSTEM' AND staff_user_id IS NULL AND actor_mechanism IS NOT NULL));
ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_actor_not_zero CHECK (staff_user_id IS NULL OR staff_user_id > 0);
