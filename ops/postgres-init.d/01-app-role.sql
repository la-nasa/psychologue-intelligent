-- Rôle applicatif à moindre privilège (ADR-008 / threat-model-v2 TV-01).
--
-- L'API se connecte avec `pi_app` : NOSUPERUSER + NOBYPASSRLS, donc les
-- politiques Row-Level Security s'appliquent réellement. Le "bypass" contrôlé
-- (system_session) passe par le paramètre de session `app.bypass_rls`, jamais
-- par un attribut de rôle — voir app/core/db.py et la migration 0001.
--
-- Les migrations Alembic tournent séparément avec le rôle propriétaire (`pi`).
--
-- Exécuté une seule fois, à l'initialisation d'un volume vierge
-- (/docker-entrypoint-initdb.d). En CI, un job équivalent lance ce fichier.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pi_app') THEN
        CREATE ROLE pi_app WITH LOGIN PASSWORD 'pi_app_dev_only'
            NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE psychologue_intelligent TO pi_app;
GRANT USAGE ON SCHEMA public TO pi_app;

-- Tables créées ensuite par les migrations (rôle `pi`) : privilèges accordés
-- automatiquement à pi_app.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO pi_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO pi_app;

-- Filet pour d'éventuelles tables déjà présentes.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO pi_app;
