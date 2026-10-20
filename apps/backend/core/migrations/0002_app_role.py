"""Create the least-privilege group role `cb_app`: DML only, no DDL, read-only `django_migrations`.

- `ALTER DEFAULT PRIVILEGES` applies only to tables and sequences created later **by the role that
  ran this migration**. Every migration must therefore run as the database owner
  (`MIGRATE_DATABASE_URL`), or the new tables are invisible to the app.
- The runtime login `cb_app_login` is created by hand after this migration
  (`CREATE ROLE cb_app_login LOGIN PASSWORD '…' IN ROLE cb_app;`, see the runbook's
  `## Database roles and migrations`), never in the Neon Console, which makes console roles
  `neon_superuser`. No LOGIN role and no password ever goes in a migration.
- Roles are cluster-wide, not per database, so the `IF NOT EXISTS` guard makes test databases and
  re-runs safe. The reverse keeps the role for the same reason: other databases may use it.
"""

from django.db import migrations

FORWARD = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cb_app') THEN
    CREATE ROLE cb_app NOLOGIN;
  END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO cb_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cb_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cb_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE django_migrations FROM cb_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cb_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cb_app;
"""

REVERSE = """
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM cb_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM cb_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cb_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cb_app;
REVOKE USAGE ON SCHEMA public FROM cb_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_ratelimit"),
        ("bookings", "0002_courts"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
