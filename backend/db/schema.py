from __future__ import annotations
import asyncpg

async def create_tables(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            version     TEXT NOT NULL DEFAULT '1.0',
            runner_type TEXT NOT NULL,
            config_yaml TEXT NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE(name, version)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            template_id       INTEGER REFERENCES templates(id),
            model_name        TEXT,
            submitter         TEXT,
            policy_config     JSONB DEFAULT '{}',
            policy_server_url TEXT DEFAULT '',
            status            TEXT DEFAULT 'pending',
            retry_count       INTEGER DEFAULT 0,
            max_retries       INTEGER DEFAULT 3,
            timeout_s         INTEGER DEFAULT 3600,
            baseline_run_id   TEXT,
            description       TEXT,
            config            JSONB DEFAULT '{}',
            created_at        DOUBLE PRECISION,
            updated_at        DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS runs (
            id          TEXT PRIMARY KEY,
            job_id      TEXT REFERENCES jobs(id),
            attempt     INTEGER DEFAULT 0,
            worker_id   INTEGER,
            status      TEXT DEFAULT 'pending',
            metrics     JSONB DEFAULT '{}',
            seed        BIGINT,
            elapsed_s   DOUBLE PRECISION,
            error_msg   TEXT,
            started_at  DOUBLE PRECISION,
            finished_at DOUBLE PRECISION
        );

        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'jobs_baseline_run_id_fkey'
            ) THEN
                ALTER TABLE jobs
                    ADD CONSTRAINT jobs_baseline_run_id_fkey
                    FOREIGN KEY (baseline_run_id) REFERENCES runs(id);
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS episodes (
            id                 SERIAL PRIMARY KEY,
            run_id             TEXT REFERENCES runs(id),
            episode_index      INTEGER,
            success            BOOLEAN,
            reward_total       DOUBLE PRECISION,
            steps              INTEGER,
            termination_reason TEXT,
            metadata           JSONB DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS matches (
            id           TEXT PRIMARY KEY,
            env_name     TEXT NOT NULL,
            template_id  INTEGER REFERENCES templates(id),
            seed         BIGINT,
            mode         TEXT DEFAULT 'direct',
            status       TEXT DEFAULT 'pending',
            model_a      TEXT NOT NULL,
            model_b      TEXT NOT NULL,
            winner       TEXT,
            is_blind     BOOLEAN DEFAULT false,
            judge_config JSONB DEFAULT '{}',
            created_at   TIMESTAMPTZ DEFAULT now(),
            finished_at  TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS match_runs (
            match_id TEXT REFERENCES matches(id),
            model    TEXT,
            run_id   TEXT REFERENCES runs(id),
            PRIMARY KEY (match_id, model)
        );

        CREATE TABLE IF NOT EXISTS elo_ratings (
            id         SERIAL PRIMARY KEY,
            model_name TEXT NOT NULL,
            env_name   TEXT NOT NULL,
            rating     DOUBLE PRECISION DEFAULT 1500,
            rd         DOUBLE PRECISION DEFAULT 350,
            volatility DOUBLE PRECISION DEFAULT 0.06,
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(model_name, env_name)
        );

        CREATE TABLE IF NOT EXISTS elo_history (
            id          SERIAL PRIMARY KEY,
            model_name  TEXT NOT NULL,
            env_name    TEXT NOT NULL,
            rating      DOUBLE PRECISION,
            rd          DOUBLE PRECISION,
            match_id    TEXT REFERENCES matches(id),
            recorded_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS hosts (
            id           SERIAL PRIMARY KEY,
            label        TEXT NOT NULL,
            host         TEXT NOT NULL,
            port         INTEGER DEFAULT 22,
            username     TEXT NOT NULL,
            password_enc TEXT NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS remote_workers (
            id               SERIAL PRIMARY KEY,
            host_id          INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
            worker_id        INTEGER NOT NULL,
            gpu_index        INTEGER NOT NULL,
            http_port        INTEGER NOT NULL,
            livestream_port  INTEGER NOT NULL,
            container_name   TEXT NOT NULL,
            status           TEXT DEFAULT 'deploying',
            deployed_at      TIMESTAMPTZ DEFAULT now(),
            stopped_at       TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS logs (
            id      SERIAL PRIMARY KEY,
            job_id  TEXT REFERENCES jobs(id),
            line    TEXT,
            ts      DOUBLE PRECISION
        );
        """)
        # Migration: add config column to existing tables
        await conn.execute("""
        ALTER TABLE jobs ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}';
        """)
