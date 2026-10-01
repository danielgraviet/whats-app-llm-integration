-- Creates the second dashboard database for the web study and applies the
-- same schema. Run once against the running container:
--   docker exec -i wa-timescaledb psql -U postgres < dashboard/init-web-db.sql
--   docker exec -i wa-timescaledb psql -U postgres -d webstudy < dashboard/schema.sql
-- (Postgres cannot create a database inside a transaction or switch databases
--  from a script fed over stdin, hence the two commands.)
SELECT 'CREATE DATABASE webstudy'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'webstudy') \gexec
