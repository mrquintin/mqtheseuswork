--
-- PostgreSQL database dump
--

\restrict Kap6rjto6knbRZTQkvaYA7u0AqxeuqbgCajh0bFtbpJVESMuTzrf7jYTeqs8dho

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.10 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: auth; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA auth;


--
-- Name: extensions; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA extensions;


--
-- Name: graphql; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA graphql;


--
-- Name: graphql_public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA graphql_public;


--
-- Name: pgbouncer; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA pgbouncer;


--
-- Name: realtime; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA realtime;


--
-- Name: storage; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA storage;


--
-- Name: vault; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA vault;


--
-- Name: pg_stat_statements; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA extensions;


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;


--
-- Name: supabase_vault; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS supabase_vault WITH SCHEMA vault;


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions;


--
-- Name: aal_level; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.aal_level AS ENUM (
    'aal1',
    'aal2',
    'aal3'
);


--
-- Name: code_challenge_method; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.code_challenge_method AS ENUM (
    's256',
    'plain'
);


--
-- Name: factor_status; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.factor_status AS ENUM (
    'unverified',
    'verified'
);


--
-- Name: factor_type; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.factor_type AS ENUM (
    'totp',
    'webauthn',
    'phone'
);


--
-- Name: oauth_authorization_status; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.oauth_authorization_status AS ENUM (
    'pending',
    'approved',
    'denied',
    'expired'
);


--
-- Name: oauth_client_type; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.oauth_client_type AS ENUM (
    'public',
    'confidential'
);


--
-- Name: oauth_registration_type; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.oauth_registration_type AS ENUM (
    'dynamic',
    'manual'
);


--
-- Name: oauth_response_type; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.oauth_response_type AS ENUM (
    'code'
);


--
-- Name: one_time_token_type; Type: TYPE; Schema: auth; Owner: -
--

CREATE TYPE auth.one_time_token_type AS ENUM (
    'confirmation_token',
    'reauthentication_token',
    'recovery_token',
    'email_change_token_new',
    'email_change_token_current',
    'phone_change_token'
);


--
-- Name: AbstentionReason; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."AbstentionReason" AS ENUM (
    'INSUFFICIENT_SOURCES',
    'NEAR_DUPLICATE',
    'BUDGET',
    'CITATION_FABRICATION',
    'REVOKED_SOURCES',
    'ABSTAIN_OFF_DOMAIN'
);


--
-- Name: CitationRelation; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CitationRelation" AS ENUM (
    'SUPPORTS',
    'CONTRADICTS',
    'QUALIFIES',
    'MENTIONS'
);


--
-- Name: CitationVerdictLabel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CitationVerdictLabel" AS ENUM (
    'ENTAILS',
    'CONTRADICTS',
    'NEUTRAL',
    'AMBIGUOUS'
);


--
-- Name: CredibilityEventKind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CredibilityEventKind" AS ENUM (
    'FORECAST_RESOLUTION',
    'RETRACTION',
    'PEER_REVIEW_VERDICT',
    'MANUAL_OVERRIDE'
);


--
-- Name: CredibilityOutcome; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CredibilityOutcome" AS ENUM (
    'CONFIRMATION',
    'FAILURE'
);


--
-- Name: CurrentEventSource; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CurrentEventSource" AS ENUM (
    'X_TWITTER',
    'RSS',
    'MANUAL'
);


--
-- Name: CurrentEventStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CurrentEventStatus" AS ENUM (
    'OBSERVED',
    'ENRICHED',
    'OPINED',
    'ABSTAINED',
    'REVOKED'
);


--
-- Name: FollowUpRole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."FollowUpRole" AS ENUM (
    'USER',
    'ASSISTANT'
);


--
-- Name: ForecastBetMode; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastBetMode" AS ENUM (
    'PAPER',
    'LIVE'
);


--
-- Name: ForecastBetSide; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastBetSide" AS ENUM (
    'YES',
    'NO'
);


--
-- Name: ForecastBetStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastBetStatus" AS ENUM (
    'PENDING',
    'AUTHORIZED',
    'CONFIRMED',
    'SUBMITTED',
    'FILLED',
    'CANCELLED',
    'SETTLED',
    'FAILED'
);


--
-- Name: ForecastExchange; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastExchange" AS ENUM (
    'POLYMARKET',
    'KALSHI'
);


--
-- Name: ForecastFollowUpRole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastFollowUpRole" AS ENUM (
    'USER',
    'ASSISTANT'
);


--
-- Name: ForecastMarketStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastMarketStatus" AS ENUM (
    'OPEN',
    'CLOSED',
    'RESOLVED',
    'CANCELLED'
);


--
-- Name: ForecastOutcome; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastOutcome" AS ENUM (
    'YES',
    'NO',
    'CANCELLED',
    'AMBIGUOUS'
);


--
-- Name: ForecastPredictionStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastPredictionStatus" AS ENUM (
    'PUBLISHED',
    'ABSTAINED_INSUFFICIENT_SOURCES',
    'ABSTAINED_MARKET_EXPIRED',
    'ABSTAINED_NEAR_DUPLICATE',
    'ABSTAINED_BUDGET',
    'ABSTAINED_CITATION_FABRICATION',
    'ABSTAINED_REVOKED_SOURCES'
);


--
-- Name: ForecastSource; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastSource" AS ENUM (
    'POLYMARKET',
    'KALSHI'
);


--
-- Name: ForecastSupportLabel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForecastSupportLabel" AS ENUM (
    'DIRECT',
    'INDIRECT',
    'CONTRARY'
);


--
-- Name: OpinionStance; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."OpinionStance" AS ENUM (
    'AGREES',
    'DISAGREES',
    'COMPLICATES',
    'ABSTAINED'
);


--
-- Name: SourceStandingStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."SourceStandingStatus" AS ENUM (
    'ACTIVE',
    'RETRACTED',
    'CORRECTED',
    'DISPUTED',
    'EXPIRED'
);


--
-- Name: action; Type: TYPE; Schema: realtime; Owner: -
--

CREATE TYPE realtime.action AS ENUM (
    'INSERT',
    'UPDATE',
    'DELETE',
    'TRUNCATE',
    'ERROR'
);


--
-- Name: equality_op; Type: TYPE; Schema: realtime; Owner: -
--

CREATE TYPE realtime.equality_op AS ENUM (
    'eq',
    'neq',
    'lt',
    'lte',
    'gt',
    'gte',
    'in'
);


--
-- Name: user_defined_filter; Type: TYPE; Schema: realtime; Owner: -
--

CREATE TYPE realtime.user_defined_filter AS (
	column_name text,
	op realtime.equality_op,
	value text
);


--
-- Name: wal_column; Type: TYPE; Schema: realtime; Owner: -
--

CREATE TYPE realtime.wal_column AS (
	name text,
	type_name text,
	type_oid oid,
	value jsonb,
	is_pkey boolean,
	is_selectable boolean
);


--
-- Name: wal_rls; Type: TYPE; Schema: realtime; Owner: -
--

CREATE TYPE realtime.wal_rls AS (
	wal jsonb,
	is_rls_enabled boolean,
	subscription_ids uuid[],
	errors text[]
);


--
-- Name: buckettype; Type: TYPE; Schema: storage; Owner: -
--

CREATE TYPE storage.buckettype AS ENUM (
    'STANDARD',
    'ANALYTICS',
    'VECTOR'
);


--
-- Name: email(); Type: FUNCTION; Schema: auth; Owner: -
--

CREATE FUNCTION auth.email() RETURNS text
    LANGUAGE sql STABLE
    AS $$
  select 
  coalesce(
    nullif(current_setting('request.jwt.claim.email', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'email')
  )::text
$$;


--
-- Name: jwt(); Type: FUNCTION; Schema: auth; Owner: -
--

CREATE FUNCTION auth.jwt() RETURNS jsonb
    LANGUAGE sql STABLE
    AS $$
  select 
    coalesce(
        nullif(current_setting('request.jwt.claim', true), ''),
        nullif(current_setting('request.jwt.claims', true), '')
    )::jsonb
$$;


--
-- Name: role(); Type: FUNCTION; Schema: auth; Owner: -
--

CREATE FUNCTION auth.role() RETURNS text
    LANGUAGE sql STABLE
    AS $$
  select 
  coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;


--
-- Name: uid(); Type: FUNCTION; Schema: auth; Owner: -
--

CREATE FUNCTION auth.uid() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$
  select 
  coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;


--
-- Name: grant_pg_cron_access(); Type: FUNCTION; Schema: extensions; Owner: -
--

CREATE FUNCTION extensions.grant_pg_cron_access() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF EXISTS (
    SELECT
    FROM pg_event_trigger_ddl_commands() AS ev
    JOIN pg_extension AS ext
    ON ev.objid = ext.oid
    WHERE ext.extname = 'pg_cron'
  )
  THEN
    grant usage on schema cron to postgres with grant option;

    alter default privileges in schema cron grant all on tables to postgres with grant option;
    alter default privileges in schema cron grant all on functions to postgres with grant option;
    alter default privileges in schema cron grant all on sequences to postgres with grant option;

    alter default privileges for user supabase_admin in schema cron grant all
        on sequences to postgres with grant option;
    alter default privileges for user supabase_admin in schema cron grant all
        on tables to postgres with grant option;
    alter default privileges for user supabase_admin in schema cron grant all
        on functions to postgres with grant option;

    grant all privileges on all tables in schema cron to postgres with grant option;
    revoke all on table cron.job from postgres;
    grant select on table cron.job to postgres with grant option;
  END IF;
END;
$$;


--
-- Name: grant_pg_graphql_access(); Type: FUNCTION; Schema: extensions; Owner: -
--

CREATE FUNCTION extensions.grant_pg_graphql_access() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $_$
DECLARE
    func_is_graphql_resolve bool;
BEGIN
    func_is_graphql_resolve = (
        SELECT n.proname = 'resolve'
        FROM pg_event_trigger_ddl_commands() AS ev
        LEFT JOIN pg_catalog.pg_proc AS n
        ON ev.objid = n.oid
    );

    IF func_is_graphql_resolve
    THEN
        -- Update public wrapper to pass all arguments through to the pg_graphql resolve func
        DROP FUNCTION IF EXISTS graphql_public.graphql;
        create or replace function graphql_public.graphql(
            "operationName" text default null,
            query text default null,
            variables jsonb default null,
            extensions jsonb default null
        )
            returns jsonb
            language sql
        as $$
            select graphql.resolve(
                query := query,
                variables := coalesce(variables, '{}'),
                "operationName" := "operationName",
                extensions := extensions
            );
        $$;

        -- This hook executes when `graphql.resolve` is created. That is not necessarily the last
        -- function in the extension so we need to grant permissions on existing entities AND
        -- update default permissions to any others that are created after `graphql.resolve`
        grant usage on schema graphql to postgres, anon, authenticated, service_role;
        grant select on all tables in schema graphql to postgres, anon, authenticated, service_role;
        grant execute on all functions in schema graphql to postgres, anon, authenticated, service_role;
        grant all on all sequences in schema graphql to postgres, anon, authenticated, service_role;
        alter default privileges in schema graphql grant all on tables to postgres, anon, authenticated, service_role;
        alter default privileges in schema graphql grant all on functions to postgres, anon, authenticated, service_role;
        alter default privileges in schema graphql grant all on sequences to postgres, anon, authenticated, service_role;

        -- Allow postgres role to allow granting usage on graphql and graphql_public schemas to custom roles
        grant usage on schema graphql_public to postgres with grant option;
        grant usage on schema graphql to postgres with grant option;
    END IF;

END;
$_$;


--
-- Name: grant_pg_net_access(); Type: FUNCTION; Schema: extensions; Owner: -
--

CREATE FUNCTION extensions.grant_pg_net_access() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_event_trigger_ddl_commands() AS ev
    JOIN pg_extension AS ext
    ON ev.objid = ext.oid
    WHERE ext.extname = 'pg_net'
  )
  THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_roles
      WHERE rolname = 'supabase_functions_admin'
    )
    THEN
      CREATE USER supabase_functions_admin NOINHERIT CREATEROLE LOGIN NOREPLICATION;
    END IF;

    GRANT USAGE ON SCHEMA net TO supabase_functions_admin, postgres, anon, authenticated, service_role;

    IF EXISTS (
      SELECT FROM pg_extension
      WHERE extname = 'pg_net'
      -- all versions in use on existing projects as of 2025-02-20
      -- version 0.12.0 onwards don't need these applied
      AND extversion IN ('0.2', '0.6', '0.7', '0.7.1', '0.8', '0.10.0', '0.11.0')
    ) THEN
      ALTER function net.http_get(url text, params jsonb, headers jsonb, timeout_milliseconds integer) SECURITY DEFINER;
      ALTER function net.http_post(url text, body jsonb, params jsonb, headers jsonb, timeout_milliseconds integer) SECURITY DEFINER;

      ALTER function net.http_get(url text, params jsonb, headers jsonb, timeout_milliseconds integer) SET search_path = net;
      ALTER function net.http_post(url text, body jsonb, params jsonb, headers jsonb, timeout_milliseconds integer) SET search_path = net;

      REVOKE ALL ON FUNCTION net.http_get(url text, params jsonb, headers jsonb, timeout_milliseconds integer) FROM PUBLIC;
      REVOKE ALL ON FUNCTION net.http_post(url text, body jsonb, params jsonb, headers jsonb, timeout_milliseconds integer) FROM PUBLIC;

      GRANT EXECUTE ON FUNCTION net.http_get(url text, params jsonb, headers jsonb, timeout_milliseconds integer) TO supabase_functions_admin, postgres, anon, authenticated, service_role;
      GRANT EXECUTE ON FUNCTION net.http_post(url text, body jsonb, params jsonb, headers jsonb, timeout_milliseconds integer) TO supabase_functions_admin, postgres, anon, authenticated, service_role;
    END IF;
  END IF;
END;
$$;


--
-- Name: pgrst_ddl_watch(); Type: FUNCTION; Schema: extensions; Owner: -
--

CREATE FUNCTION extensions.pgrst_ddl_watch() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN SELECT * FROM pg_event_trigger_ddl_commands()
  LOOP
    IF cmd.command_tag IN (
      'CREATE SCHEMA', 'ALTER SCHEMA'
    , 'CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO', 'ALTER TABLE'
    , 'CREATE FOREIGN TABLE', 'ALTER FOREIGN TABLE'
    , 'CREATE VIEW', 'ALTER VIEW'
    , 'CREATE MATERIALIZED VIEW', 'ALTER MATERIALIZED VIEW'
    , 'CREATE FUNCTION', 'ALTER FUNCTION'
    , 'CREATE TRIGGER'
    , 'CREATE TYPE', 'ALTER TYPE'
    , 'CREATE RULE'
    , 'COMMENT'
    )
    -- don't notify in case of CREATE TEMP table or other objects created on pg_temp
    AND cmd.schema_name is distinct from 'pg_temp'
    THEN
      NOTIFY pgrst, 'reload schema';
    END IF;
  END LOOP;
END; $$;


--
-- Name: pgrst_drop_watch(); Type: FUNCTION; Schema: extensions; Owner: -
--

CREATE FUNCTION extensions.pgrst_drop_watch() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  obj record;
BEGIN
  FOR obj IN SELECT * FROM pg_event_trigger_dropped_objects()
  LOOP
    IF obj.object_type IN (
      'schema'
    , 'table'
    , 'foreign table'
    , 'view'
    , 'materialized view'
    , 'function'
    , 'trigger'
    , 'type'
    , 'rule'
    )
    AND obj.is_temporary IS false -- no pg_temp objects
    THEN
      NOTIFY pgrst, 'reload schema';
    END IF;
  END LOOP;
END; $$;


--
-- Name: set_graphql_placeholder(); Type: FUNCTION; Schema: extensions; Owner: -
--

CREATE FUNCTION extensions.set_graphql_placeholder() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $_$
    DECLARE
    graphql_is_dropped bool;
    BEGIN
    graphql_is_dropped = (
        SELECT ev.schema_name = 'graphql_public'
        FROM pg_event_trigger_dropped_objects() AS ev
        WHERE ev.schema_name = 'graphql_public'
    );

    IF graphql_is_dropped
    THEN
        create or replace function graphql_public.graphql(
            "operationName" text default null,
            query text default null,
            variables jsonb default null,
            extensions jsonb default null
        )
            returns jsonb
            language plpgsql
        as $$
            DECLARE
                server_version float;
            BEGIN
                server_version = (SELECT (SPLIT_PART((select version()), ' ', 2))::float);

                IF server_version >= 14 THEN
                    RETURN jsonb_build_object(
                        'errors', jsonb_build_array(
                            jsonb_build_object(
                                'message', 'pg_graphql extension is not enabled.'
                            )
                        )
                    );
                ELSE
                    RETURN jsonb_build_object(
                        'errors', jsonb_build_array(
                            jsonb_build_object(
                                'message', 'pg_graphql is only available on projects running Postgres 14 onwards.'
                            )
                        )
                    );
                END IF;
            END;
        $$;
    END IF;

    END;
$_$;


--
-- Name: graphql(text, text, jsonb, jsonb); Type: FUNCTION; Schema: graphql_public; Owner: -
--

CREATE FUNCTION graphql_public.graphql("operationName" text DEFAULT NULL::text, query text DEFAULT NULL::text, variables jsonb DEFAULT NULL::jsonb, extensions jsonb DEFAULT NULL::jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
            DECLARE
                server_version float;
            BEGIN
                server_version = (SELECT (SPLIT_PART((select version()), ' ', 2))::float);

                IF server_version >= 14 THEN
                    RETURN jsonb_build_object(
                        'errors', jsonb_build_array(
                            jsonb_build_object(
                                'message', 'pg_graphql extension is not enabled.'
                            )
                        )
                    );
                ELSE
                    RETURN jsonb_build_object(
                        'errors', jsonb_build_array(
                            jsonb_build_object(
                                'message', 'pg_graphql is only available on projects running Postgres 14 onwards.'
                            )
                        )
                    );
                END IF;
            END;
        $$;


--
-- Name: get_auth(text); Type: FUNCTION; Schema: pgbouncer; Owner: -
--

CREATE FUNCTION pgbouncer.get_auth(p_usename text) RETURNS TABLE(username text, password text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $_$
  BEGIN
      RAISE DEBUG 'PgBouncer auth request: %', p_usename;

      RETURN QUERY
      SELECT
          rolname::text,
          CASE WHEN rolvaliduntil < now()
              THEN null
              ELSE rolpassword::text
          END
      FROM pg_authid
      WHERE rolname=$1 and rolcanlogin;
  END;
  $_$;


--
-- Name: apply_rls(jsonb, integer); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.apply_rls(wal jsonb, max_record_bytes integer DEFAULT (1024 * 1024)) RETURNS SETOF realtime.wal_rls
    LANGUAGE plpgsql
    AS $$
declare
-- Regclass of the table e.g. public.notes
entity_ regclass = (quote_ident(wal ->> 'schema') || '.' || quote_ident(wal ->> 'table'))::regclass;

-- I, U, D, T: insert, update ...
action realtime.action = (
    case wal ->> 'action'
        when 'I' then 'INSERT'
        when 'U' then 'UPDATE'
        when 'D' then 'DELETE'
        else 'ERROR'
    end
);

-- Is row level security enabled for the table
is_rls_enabled bool = relrowsecurity from pg_class where oid = entity_;

subscriptions realtime.subscription[] = array_agg(subs)
    from
        realtime.subscription subs
    where
        subs.entity = entity_
        -- Filter by action early - only get subscriptions interested in this action
        -- action_filter column can be: '*' (all), 'INSERT', 'UPDATE', or 'DELETE'
        and (subs.action_filter = '*' or subs.action_filter = action::text);

-- Subscription vars
roles regrole[] = array_agg(distinct us.claims_role::text)
    from
        unnest(subscriptions) us;

working_role regrole;
claimed_role regrole;
claims jsonb;

subscription_id uuid;
subscription_has_access bool;
visible_to_subscription_ids uuid[] = '{}';

-- structured info for wal's columns
columns realtime.wal_column[];
-- previous identity values for update/delete
old_columns realtime.wal_column[];

error_record_exceeds_max_size boolean = octet_length(wal::text) > max_record_bytes;

-- Primary jsonb output for record
output jsonb;

begin
perform set_config('role', null, true);

columns =
    array_agg(
        (
            x->>'name',
            x->>'type',
            x->>'typeoid',
            realtime.cast(
                (x->'value') #>> '{}',
                coalesce(
                    (x->>'typeoid')::regtype, -- null when wal2json version <= 2.4
                    (x->>'type')::regtype
                )
            ),
            (pks ->> 'name') is not null,
            true
        )::realtime.wal_column
    )
    from
        jsonb_array_elements(wal -> 'columns') x
        left join jsonb_array_elements(wal -> 'pk') pks
            on (x ->> 'name') = (pks ->> 'name');

old_columns =
    array_agg(
        (
            x->>'name',
            x->>'type',
            x->>'typeoid',
            realtime.cast(
                (x->'value') #>> '{}',
                coalesce(
                    (x->>'typeoid')::regtype, -- null when wal2json version <= 2.4
                    (x->>'type')::regtype
                )
            ),
            (pks ->> 'name') is not null,
            true
        )::realtime.wal_column
    )
    from
        jsonb_array_elements(wal -> 'identity') x
        left join jsonb_array_elements(wal -> 'pk') pks
            on (x ->> 'name') = (pks ->> 'name');

for working_role in select * from unnest(roles) loop

    -- Update `is_selectable` for columns and old_columns
    columns =
        array_agg(
            (
                c.name,
                c.type_name,
                c.type_oid,
                c.value,
                c.is_pkey,
                pg_catalog.has_column_privilege(working_role, entity_, c.name, 'SELECT')
            )::realtime.wal_column
        )
        from
            unnest(columns) c;

    old_columns =
            array_agg(
                (
                    c.name,
                    c.type_name,
                    c.type_oid,
                    c.value,
                    c.is_pkey,
                    pg_catalog.has_column_privilege(working_role, entity_, c.name, 'SELECT')
                )::realtime.wal_column
            )
            from
                unnest(old_columns) c;

    if action <> 'DELETE' and count(1) = 0 from unnest(columns) c where c.is_pkey then
        return next (
            jsonb_build_object(
                'schema', wal ->> 'schema',
                'table', wal ->> 'table',
                'type', action
            ),
            is_rls_enabled,
            -- subscriptions is already filtered by entity
            (select array_agg(s.subscription_id) from unnest(subscriptions) as s where claims_role = working_role),
            array['Error 400: Bad Request, no primary key']
        )::realtime.wal_rls;

    -- The claims role does not have SELECT permission to the primary key of entity
    elsif action <> 'DELETE' and sum(c.is_selectable::int) <> count(1) from unnest(columns) c where c.is_pkey then
        return next (
            jsonb_build_object(
                'schema', wal ->> 'schema',
                'table', wal ->> 'table',
                'type', action
            ),
            is_rls_enabled,
            (select array_agg(s.subscription_id) from unnest(subscriptions) as s where claims_role = working_role),
            array['Error 401: Unauthorized']
        )::realtime.wal_rls;

    else
        output = jsonb_build_object(
            'schema', wal ->> 'schema',
            'table', wal ->> 'table',
            'type', action,
            'commit_timestamp', to_char(
                ((wal ->> 'timestamp')::timestamptz at time zone 'utc'),
                'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'
            ),
            'columns', (
                select
                    jsonb_agg(
                        jsonb_build_object(
                            'name', pa.attname,
                            'type', pt.typname
                        )
                        order by pa.attnum asc
                    )
                from
                    pg_attribute pa
                    join pg_type pt
                        on pa.atttypid = pt.oid
                where
                    attrelid = entity_
                    and attnum > 0
                    and pg_catalog.has_column_privilege(working_role, entity_, pa.attname, 'SELECT')
            )
        )
        -- Add "record" key for insert and update
        || case
            when action in ('INSERT', 'UPDATE') then
                jsonb_build_object(
                    'record',
                    (
                        select
                            jsonb_object_agg(
                                -- if unchanged toast, get column name and value from old record
                                coalesce((c).name, (oc).name),
                                case
                                    when (c).name is null then (oc).value
                                    else (c).value
                                end
                            )
                        from
                            unnest(columns) c
                            full outer join unnest(old_columns) oc
                                on (c).name = (oc).name
                        where
                            coalesce((c).is_selectable, (oc).is_selectable)
                            and ( not error_record_exceeds_max_size or (octet_length((c).value::text) <= 64))
                    )
                )
            else '{}'::jsonb
        end
        -- Add "old_record" key for update and delete
        || case
            when action = 'UPDATE' then
                jsonb_build_object(
                        'old_record',
                        (
                            select jsonb_object_agg((c).name, (c).value)
                            from unnest(old_columns) c
                            where
                                (c).is_selectable
                                and ( not error_record_exceeds_max_size or (octet_length((c).value::text) <= 64))
                        )
                    )
            when action = 'DELETE' then
                jsonb_build_object(
                    'old_record',
                    (
                        select jsonb_object_agg((c).name, (c).value)
                        from unnest(old_columns) c
                        where
                            (c).is_selectable
                            and ( not error_record_exceeds_max_size or (octet_length((c).value::text) <= 64))
                            and ( not is_rls_enabled or (c).is_pkey ) -- if RLS enabled, we can't secure deletes so filter to pkey
                    )
                )
            else '{}'::jsonb
        end;

        -- Create the prepared statement
        if is_rls_enabled and action <> 'DELETE' then
            if (select 1 from pg_prepared_statements where name = 'walrus_rls_stmt' limit 1) > 0 then
                deallocate walrus_rls_stmt;
            end if;
            execute realtime.build_prepared_statement_sql('walrus_rls_stmt', entity_, columns);
        end if;

        visible_to_subscription_ids = '{}';

        for subscription_id, claims in (
                select
                    subs.subscription_id,
                    subs.claims
                from
                    unnest(subscriptions) subs
                where
                    subs.entity = entity_
                    and subs.claims_role = working_role
                    and (
                        realtime.is_visible_through_filters(columns, subs.filters)
                        or (
                          action = 'DELETE'
                          and realtime.is_visible_through_filters(old_columns, subs.filters)
                        )
                    )
        ) loop

            if not is_rls_enabled or action = 'DELETE' then
                visible_to_subscription_ids = visible_to_subscription_ids || subscription_id;
            else
                -- Check if RLS allows the role to see the record
                perform
                    -- Trim leading and trailing quotes from working_role because set_config
                    -- doesn't recognize the role as valid if they are included
                    set_config('role', trim(both '"' from working_role::text), true),
                    set_config('request.jwt.claims', claims::text, true);

                execute 'execute walrus_rls_stmt' into subscription_has_access;

                if subscription_has_access then
                    visible_to_subscription_ids = visible_to_subscription_ids || subscription_id;
                end if;
            end if;
        end loop;

        perform set_config('role', null, true);

        return next (
            output,
            is_rls_enabled,
            visible_to_subscription_ids,
            case
                when error_record_exceeds_max_size then array['Error 413: Payload Too Large']
                else '{}'
            end
        )::realtime.wal_rls;

    end if;
end loop;

perform set_config('role', null, true);
end;
$$;


--
-- Name: broadcast_changes(text, text, text, text, text, record, record, text); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.broadcast_changes(topic_name text, event_name text, operation text, table_name text, table_schema text, new record, old record, level text DEFAULT 'ROW'::text) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    -- Declare a variable to hold the JSONB representation of the row
    row_data jsonb := '{}'::jsonb;
BEGIN
    IF level = 'STATEMENT' THEN
        RAISE EXCEPTION 'function can only be triggered for each row, not for each statement';
    END IF;
    -- Check the operation type and handle accordingly
    IF operation = 'INSERT' OR operation = 'UPDATE' OR operation = 'DELETE' THEN
        row_data := jsonb_build_object('old_record', OLD, 'record', NEW, 'operation', operation, 'table', table_name, 'schema', table_schema);
        PERFORM realtime.send (row_data, event_name, topic_name);
    ELSE
        RAISE EXCEPTION 'Unexpected operation type: %', operation;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Failed to process the row: %', SQLERRM;
END;

$$;


--
-- Name: build_prepared_statement_sql(text, regclass, realtime.wal_column[]); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.build_prepared_statement_sql(prepared_statement_name text, entity regclass, columns realtime.wal_column[]) RETURNS text
    LANGUAGE sql
    AS $$
      /*
      Builds a sql string that, if executed, creates a prepared statement to
      tests retrive a row from *entity* by its primary key columns.
      Example
          select realtime.build_prepared_statement_sql('public.notes', '{"id"}'::text[], '{"bigint"}'::text[])
      */
          select
      'prepare ' || prepared_statement_name || ' as
          select
              exists(
                  select
                      1
                  from
                      ' || entity || '
                  where
                      ' || string_agg(quote_ident(pkc.name) || '=' || quote_nullable(pkc.value #>> '{}') , ' and ') || '
              )'
          from
              unnest(columns) pkc
          where
              pkc.is_pkey
          group by
              entity
      $$;


--
-- Name: cast(text, regtype); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime."cast"(val text, type_ regtype) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE
    AS $$
declare
  res jsonb;
begin
  if type_::text = 'bytea' then
    return to_jsonb(val);
  end if;
  execute format('select to_jsonb(%L::'|| type_::text || ')', val) into res;
  return res;
end
$$;


--
-- Name: check_equality_op(realtime.equality_op, regtype, text, text); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.check_equality_op(op realtime.equality_op, type_ regtype, val_1 text, val_2 text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$
      /*
      Casts *val_1* and *val_2* as type *type_* and check the *op* condition for truthiness
      */
      declare
          op_symbol text = (
              case
                  when op = 'eq' then '='
                  when op = 'neq' then '!='
                  when op = 'lt' then '<'
                  when op = 'lte' then '<='
                  when op = 'gt' then '>'
                  when op = 'gte' then '>='
                  when op = 'in' then '= any'
                  else 'UNKNOWN OP'
              end
          );
          res boolean;
      begin
          execute format(
              'select %L::'|| type_::text || ' ' || op_symbol
              || ' ( %L::'
              || (
                  case
                      when op = 'in' then type_::text || '[]'
                      else type_::text end
              )
              || ')', val_1, val_2) into res;
          return res;
      end;
      $$;


--
-- Name: is_visible_through_filters(realtime.wal_column[], realtime.user_defined_filter[]); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.is_visible_through_filters(columns realtime.wal_column[], filters realtime.user_defined_filter[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $_$
    /*
    Should the record be visible (true) or filtered out (false) after *filters* are applied
    */
        select
            -- Default to allowed when no filters present
            $2 is null -- no filters. this should not happen because subscriptions has a default
            or array_length($2, 1) is null -- array length of an empty array is null
            or bool_and(
                coalesce(
                    realtime.check_equality_op(
                        op:=f.op,
                        type_:=coalesce(
                            col.type_oid::regtype, -- null when wal2json version <= 2.4
                            col.type_name::regtype
                        ),
                        -- cast jsonb to text
                        val_1:=col.value #>> '{}',
                        val_2:=f.value
                    ),
                    false -- if null, filter does not match
                )
            )
        from
            unnest(filters) f
            join unnest(columns) col
                on f.column_name = col.name;
    $_$;


--
-- Name: list_changes(name, name, integer, integer); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.list_changes(publication name, slot_name name, max_changes integer, max_record_bytes integer) RETURNS TABLE(wal jsonb, is_rls_enabled boolean, subscription_ids uuid[], errors text[], slot_changes_count bigint)
    LANGUAGE sql
    SET log_min_messages TO 'fatal'
    AS $$
  WITH pub AS (
    SELECT
      concat_ws(
        ',',
        CASE WHEN bool_or(pubinsert) THEN 'insert' ELSE NULL END,
        CASE WHEN bool_or(pubupdate) THEN 'update' ELSE NULL END,
        CASE WHEN bool_or(pubdelete) THEN 'delete' ELSE NULL END
      ) AS w2j_actions,
      coalesce(
        string_agg(
          realtime.quote_wal2json(format('%I.%I', schemaname, tablename)::regclass),
          ','
        ) filter (WHERE ppt.tablename IS NOT NULL AND ppt.tablename NOT LIKE '% %'),
        ''
      ) AS w2j_add_tables
    FROM pg_publication pp
    LEFT JOIN pg_publication_tables ppt ON pp.pubname = ppt.pubname
    WHERE pp.pubname = publication
    GROUP BY pp.pubname
    LIMIT 1
  ),
  -- MATERIALIZED ensures pg_logical_slot_get_changes is called exactly once
  w2j AS MATERIALIZED (
    SELECT x.*, pub.w2j_add_tables
    FROM pub,
         pg_logical_slot_get_changes(
           slot_name, null, max_changes,
           'include-pk', 'true',
           'include-transaction', 'false',
           'include-timestamp', 'true',
           'include-type-oids', 'true',
           'format-version', '2',
           'actions', pub.w2j_actions,
           'add-tables', pub.w2j_add_tables
         ) x
  ),
  -- Count raw slot entries before apply_rls/subscription filter
  slot_count AS (
    SELECT count(*)::bigint AS cnt
    FROM w2j
    WHERE w2j.w2j_add_tables <> ''
  ),
  -- Apply RLS and filter as before
  rls_filtered AS (
    SELECT xyz.wal, xyz.is_rls_enabled, xyz.subscription_ids, xyz.errors
    FROM w2j,
         realtime.apply_rls(
           wal := w2j.data::jsonb,
           max_record_bytes := max_record_bytes
         ) xyz(wal, is_rls_enabled, subscription_ids, errors)
    WHERE w2j.w2j_add_tables <> ''
      AND xyz.subscription_ids[1] IS NOT NULL
  )
  -- Real rows with slot count attached
  SELECT rf.wal, rf.is_rls_enabled, rf.subscription_ids, rf.errors, sc.cnt
  FROM rls_filtered rf, slot_count sc

  UNION ALL

  -- Sentinel row: always returned when no real rows exist so Elixir can
  -- always read slot_changes_count. Identified by wal IS NULL.
  SELECT null, null, null, null, sc.cnt
  FROM slot_count sc
  WHERE NOT EXISTS (SELECT 1 FROM rls_filtered)
$$;


--
-- Name: quote_wal2json(regclass); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.quote_wal2json(entity regclass) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
      select
        (
          select string_agg('' || ch,'')
          from unnest(string_to_array(nsp.nspname::text, null)) with ordinality x(ch, idx)
          where
            not (x.idx = 1 and x.ch = '"')
            and not (
              x.idx = array_length(string_to_array(nsp.nspname::text, null), 1)
              and x.ch = '"'
            )
        )
        || '.'
        || (
          select string_agg('' || ch,'')
          from unnest(string_to_array(pc.relname::text, null)) with ordinality x(ch, idx)
          where
            not (x.idx = 1 and x.ch = '"')
            and not (
              x.idx = array_length(string_to_array(nsp.nspname::text, null), 1)
              and x.ch = '"'
            )
          )
      from
        pg_class pc
        join pg_namespace nsp
          on pc.relnamespace = nsp.oid
      where
        pc.oid = entity
    $$;


--
-- Name: send(jsonb, text, text, boolean); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.send(payload jsonb, event text, topic text, private boolean DEFAULT true) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
  generated_id uuid;
  final_payload jsonb;
BEGIN
  BEGIN
    -- Generate a new UUID for the id
    generated_id := gen_random_uuid();

    -- Check if payload has an 'id' key, if not, add the generated UUID
    IF payload ? 'id' THEN
      final_payload := payload;
    ELSE
      final_payload := jsonb_set(payload, '{id}', to_jsonb(generated_id));
    END IF;

    -- Set the topic configuration
    EXECUTE format('SET LOCAL realtime.topic TO %L', topic);

    -- Attempt to insert the message
    INSERT INTO realtime.messages (id, payload, event, topic, private, extension)
    VALUES (generated_id, final_payload, event, topic, private, 'broadcast');
  EXCEPTION
    WHEN OTHERS THEN
      -- Capture and notify the error
      RAISE WARNING 'ErrorSendingBroadcastMessage: %', SQLERRM;
  END;
END;
$$;


--
-- Name: subscription_check_filters(); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.subscription_check_filters() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    /*
    Validates that the user defined filters for a subscription:
    - refer to valid columns that the claimed role may access
    - values are coercable to the correct column type
    */
    declare
        col_names text[] = coalesce(
                array_agg(c.column_name order by c.ordinal_position),
                '{}'::text[]
            )
            from
                information_schema.columns c
            where
                format('%I.%I', c.table_schema, c.table_name)::regclass = new.entity
                and pg_catalog.has_column_privilege(
                    (new.claims ->> 'role'),
                    format('%I.%I', c.table_schema, c.table_name)::regclass,
                    c.column_name,
                    'SELECT'
                );
        filter realtime.user_defined_filter;
        col_type regtype;

        in_val jsonb;
    begin
        for filter in select * from unnest(new.filters) loop
            -- Filtered column is valid
            if not filter.column_name = any(col_names) then
                raise exception 'invalid column for filter %', filter.column_name;
            end if;

            -- Type is sanitized and safe for string interpolation
            col_type = (
                select atttypid::regtype
                from pg_catalog.pg_attribute
                where attrelid = new.entity
                      and attname = filter.column_name
            );
            if col_type is null then
                raise exception 'failed to lookup type for column %', filter.column_name;
            end if;

            -- Set maximum number of entries for in filter
            if filter.op = 'in'::realtime.equality_op then
                in_val = realtime.cast(filter.value, (col_type::text || '[]')::regtype);
                if coalesce(jsonb_array_length(in_val), 0) > 100 then
                    raise exception 'too many values for `in` filter. Maximum 100';
                end if;
            else
                -- raises an exception if value is not coercable to type
                perform realtime.cast(filter.value, col_type);
            end if;

        end loop;

        -- Apply consistent order to filters so the unique constraint on
        -- (subscription_id, entity, filters) can't be tricked by a different filter order
        new.filters = coalesce(
            array_agg(f order by f.column_name, f.op, f.value),
            '{}'
        ) from unnest(new.filters) f;

        return new;
    end;
    $$;


--
-- Name: to_regrole(text); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.to_regrole(role_name text) RETURNS regrole
    LANGUAGE sql IMMUTABLE
    AS $$ select role_name::regrole $$;


--
-- Name: topic(); Type: FUNCTION; Schema: realtime; Owner: -
--

CREATE FUNCTION realtime.topic() RETURNS text
    LANGUAGE sql STABLE
    AS $$
select nullif(current_setting('realtime.topic', true), '')::text;
$$;


--
-- Name: allow_any_operation(text[]); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.allow_any_operation(expected_operations text[]) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
  WITH current_operation AS (
    SELECT storage.operation() AS raw_operation
  ),
  normalized AS (
    SELECT CASE
      WHEN raw_operation LIKE 'storage.%' THEN substr(raw_operation, 9)
      ELSE raw_operation
    END AS current_operation
    FROM current_operation
  )
  SELECT EXISTS (
    SELECT 1
    FROM normalized n
    CROSS JOIN LATERAL unnest(expected_operations) AS expected_operation
    WHERE expected_operation IS NOT NULL
      AND expected_operation <> ''
      AND n.current_operation = CASE
        WHEN expected_operation LIKE 'storage.%' THEN substr(expected_operation, 9)
        ELSE expected_operation
      END
  );
$$;


--
-- Name: allow_only_operation(text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.allow_only_operation(expected_operation text) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
  WITH current_operation AS (
    SELECT storage.operation() AS raw_operation
  ),
  normalized AS (
    SELECT
      CASE
        WHEN raw_operation LIKE 'storage.%' THEN substr(raw_operation, 9)
        ELSE raw_operation
      END AS current_operation,
      CASE
        WHEN expected_operation LIKE 'storage.%' THEN substr(expected_operation, 9)
        ELSE expected_operation
      END AS requested_operation
    FROM current_operation
  )
  SELECT CASE
    WHEN requested_operation IS NULL OR requested_operation = '' THEN FALSE
    ELSE COALESCE(current_operation = requested_operation, FALSE)
  END
  FROM normalized;
$$;


--
-- Name: can_insert_object(text, text, uuid, jsonb); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.can_insert_object(bucketid text, name text, owner uuid, metadata jsonb) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
  INSERT INTO "storage"."objects" ("bucket_id", "name", "owner", "metadata") VALUES (bucketid, name, owner, metadata);
  -- hack to rollback the successful insert
  RAISE sqlstate 'PT200' using
  message = 'ROLLBACK',
  detail = 'rollback successful insert';
END
$$;


--
-- Name: enforce_bucket_name_length(); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.enforce_bucket_name_length() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    if length(new.name) > 100 then
        raise exception 'bucket name "%" is too long (% characters). Max is 100.', new.name, length(new.name);
    end if;
    return new;
end;
$$;


--
-- Name: extension(text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.extension(name text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
    _parts text[];
    _filename text;
BEGIN
    -- Split on "/" to get path segments
    SELECT string_to_array(name, '/') INTO _parts;
    -- Get the last path segment (the actual filename)
    SELECT _parts[array_length(_parts, 1)] INTO _filename;
    -- Extract extension: reverse, split on '.', then reverse again
    RETURN reverse(split_part(reverse(_filename), '.', 1));
END
$$;


--
-- Name: filename(text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.filename(name text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
_parts text[];
BEGIN
	select string_to_array(name, '/') into _parts;
	return _parts[array_length(_parts,1)];
END
$$;


--
-- Name: foldername(text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.foldername(name text) RETURNS text[]
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
    _parts text[];
BEGIN
    -- Split on "/" to get path segments
    SELECT string_to_array(name, '/') INTO _parts;
    -- Return everything except the last segment
    RETURN _parts[1 : array_length(_parts,1) - 1];
END
$$;


--
-- Name: get_common_prefix(text, text, text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.get_common_prefix(p_key text, p_prefix text, p_delimiter text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
SELECT CASE
    WHEN position(p_delimiter IN substring(p_key FROM length(p_prefix) + 1)) > 0
    THEN left(p_key, length(p_prefix) + position(p_delimiter IN substring(p_key FROM length(p_prefix) + 1)))
    ELSE NULL
END;
$$;


--
-- Name: get_size_by_bucket(); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.get_size_by_bucket() RETURNS TABLE(size bigint, bucket_id text)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
    return query
        select sum((metadata->>'size')::bigint)::bigint as size, obj.bucket_id
        from "storage".objects as obj
        group by obj.bucket_id;
END
$$;


--
-- Name: list_multipart_uploads_with_delimiter(text, text, text, integer, text, text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.list_multipart_uploads_with_delimiter(bucket_id text, prefix_param text, delimiter_param text, max_keys integer DEFAULT 100, next_key_token text DEFAULT ''::text, next_upload_token text DEFAULT ''::text) RETURNS TABLE(key text, id text, created_at timestamp with time zone)
    LANGUAGE plpgsql
    AS $_$
BEGIN
    RETURN QUERY EXECUTE
        'SELECT DISTINCT ON(key COLLATE "C") * from (
            SELECT
                CASE
                    WHEN position($2 IN substring(key from length($1) + 1)) > 0 THEN
                        substring(key from 1 for length($1) + position($2 IN substring(key from length($1) + 1)))
                    ELSE
                        key
                END AS key, id, created_at
            FROM
                storage.s3_multipart_uploads
            WHERE
                bucket_id = $5 AND
                key ILIKE $1 || ''%'' AND
                CASE
                    WHEN $4 != '''' AND $6 = '''' THEN
                        CASE
                            WHEN position($2 IN substring(key from length($1) + 1)) > 0 THEN
                                substring(key from 1 for length($1) + position($2 IN substring(key from length($1) + 1))) COLLATE "C" > $4
                            ELSE
                                key COLLATE "C" > $4
                            END
                    ELSE
                        true
                END AND
                CASE
                    WHEN $6 != '''' THEN
                        id COLLATE "C" > $6
                    ELSE
                        true
                    END
            ORDER BY
                key COLLATE "C" ASC, created_at ASC) as e order by key COLLATE "C" LIMIT $3'
        USING prefix_param, delimiter_param, max_keys, next_key_token, bucket_id, next_upload_token;
END;
$_$;


--
-- Name: list_objects_with_delimiter(text, text, text, integer, text, text, text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.list_objects_with_delimiter(_bucket_id text, prefix_param text, delimiter_param text, max_keys integer DEFAULT 100, start_after text DEFAULT ''::text, next_token text DEFAULT ''::text, sort_order text DEFAULT 'asc'::text) RETURNS TABLE(name text, id uuid, metadata jsonb, updated_at timestamp with time zone, created_at timestamp with time zone, last_accessed_at timestamp with time zone)
    LANGUAGE plpgsql STABLE
    AS $_$
DECLARE
    v_peek_name TEXT;
    v_current RECORD;
    v_common_prefix TEXT;

    -- Configuration
    v_is_asc BOOLEAN;
    v_prefix TEXT;
    v_start TEXT;
    v_upper_bound TEXT;
    v_file_batch_size INT;

    -- Seek state
    v_next_seek TEXT;
    v_count INT := 0;

    -- Dynamic SQL for batch query only
    v_batch_query TEXT;

BEGIN
    -- ========================================================================
    -- INITIALIZATION
    -- ========================================================================
    v_is_asc := lower(coalesce(sort_order, 'asc')) = 'asc';
    v_prefix := coalesce(prefix_param, '');
    v_start := CASE WHEN coalesce(next_token, '') <> '' THEN next_token ELSE coalesce(start_after, '') END;
    v_file_batch_size := LEAST(GREATEST(max_keys * 2, 100), 1000);

    -- Calculate upper bound for prefix filtering (bytewise, using COLLATE "C")
    IF v_prefix = '' THEN
        v_upper_bound := NULL;
    ELSIF right(v_prefix, 1) = delimiter_param THEN
        v_upper_bound := left(v_prefix, -1) || chr(ascii(delimiter_param) + 1);
    ELSE
        v_upper_bound := left(v_prefix, -1) || chr(ascii(right(v_prefix, 1)) + 1);
    END IF;

    -- Build batch query (dynamic SQL - called infrequently, amortized over many rows)
    IF v_is_asc THEN
        IF v_upper_bound IS NOT NULL THEN
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND o.name COLLATE "C" >= $2 ' ||
                'AND o.name COLLATE "C" < $3 ORDER BY o.name COLLATE "C" ASC LIMIT $4';
        ELSE
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND o.name COLLATE "C" >= $2 ' ||
                'ORDER BY o.name COLLATE "C" ASC LIMIT $4';
        END IF;
    ELSE
        IF v_upper_bound IS NOT NULL THEN
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND o.name COLLATE "C" < $2 ' ||
                'AND o.name COLLATE "C" >= $3 ORDER BY o.name COLLATE "C" DESC LIMIT $4';
        ELSE
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND o.name COLLATE "C" < $2 ' ||
                'ORDER BY o.name COLLATE "C" DESC LIMIT $4';
        END IF;
    END IF;

    -- ========================================================================
    -- SEEK INITIALIZATION: Determine starting position
    -- ========================================================================
    IF v_start = '' THEN
        IF v_is_asc THEN
            v_next_seek := v_prefix;
        ELSE
            -- DESC without cursor: find the last item in range
            IF v_upper_bound IS NOT NULL THEN
                SELECT o.name INTO v_next_seek FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" >= v_prefix AND o.name COLLATE "C" < v_upper_bound
                ORDER BY o.name COLLATE "C" DESC LIMIT 1;
            ELSIF v_prefix <> '' THEN
                SELECT o.name INTO v_next_seek FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" >= v_prefix
                ORDER BY o.name COLLATE "C" DESC LIMIT 1;
            ELSE
                SELECT o.name INTO v_next_seek FROM storage.objects o
                WHERE o.bucket_id = _bucket_id
                ORDER BY o.name COLLATE "C" DESC LIMIT 1;
            END IF;

            IF v_next_seek IS NOT NULL THEN
                v_next_seek := v_next_seek || delimiter_param;
            ELSE
                RETURN;
            END IF;
        END IF;
    ELSE
        -- Cursor provided: determine if it refers to a folder or leaf
        IF EXISTS (
            SELECT 1 FROM storage.objects o
            WHERE o.bucket_id = _bucket_id
              AND o.name COLLATE "C" LIKE v_start || delimiter_param || '%'
            LIMIT 1
        ) THEN
            -- Cursor refers to a folder
            IF v_is_asc THEN
                v_next_seek := v_start || chr(ascii(delimiter_param) + 1);
            ELSE
                v_next_seek := v_start || delimiter_param;
            END IF;
        ELSE
            -- Cursor refers to a leaf object
            IF v_is_asc THEN
                v_next_seek := v_start || delimiter_param;
            ELSE
                v_next_seek := v_start;
            END IF;
        END IF;
    END IF;

    -- ========================================================================
    -- MAIN LOOP: Hybrid peek-then-batch algorithm
    -- Uses STATIC SQL for peek (hot path) and DYNAMIC SQL for batch
    -- ========================================================================
    LOOP
        EXIT WHEN v_count >= max_keys;

        -- STEP 1: PEEK using STATIC SQL (plan cached, very fast)
        IF v_is_asc THEN
            IF v_upper_bound IS NOT NULL THEN
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" >= v_next_seek AND o.name COLLATE "C" < v_upper_bound
                ORDER BY o.name COLLATE "C" ASC LIMIT 1;
            ELSE
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" >= v_next_seek
                ORDER BY o.name COLLATE "C" ASC LIMIT 1;
            END IF;
        ELSE
            IF v_upper_bound IS NOT NULL THEN
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" < v_next_seek AND o.name COLLATE "C" >= v_prefix
                ORDER BY o.name COLLATE "C" DESC LIMIT 1;
            ELSIF v_prefix <> '' THEN
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" < v_next_seek AND o.name COLLATE "C" >= v_prefix
                ORDER BY o.name COLLATE "C" DESC LIMIT 1;
            ELSE
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = _bucket_id AND o.name COLLATE "C" < v_next_seek
                ORDER BY o.name COLLATE "C" DESC LIMIT 1;
            END IF;
        END IF;

        EXIT WHEN v_peek_name IS NULL;

        -- STEP 2: Check if this is a FOLDER or FILE
        v_common_prefix := storage.get_common_prefix(v_peek_name, v_prefix, delimiter_param);

        IF v_common_prefix IS NOT NULL THEN
            -- FOLDER: Emit and skip to next folder (no heap access needed)
            name := rtrim(v_common_prefix, delimiter_param);
            id := NULL;
            updated_at := NULL;
            created_at := NULL;
            last_accessed_at := NULL;
            metadata := NULL;
            RETURN NEXT;
            v_count := v_count + 1;

            -- Advance seek past the folder range
            IF v_is_asc THEN
                v_next_seek := left(v_common_prefix, -1) || chr(ascii(delimiter_param) + 1);
            ELSE
                v_next_seek := v_common_prefix;
            END IF;
        ELSE
            -- FILE: Batch fetch using DYNAMIC SQL (overhead amortized over many rows)
            -- For ASC: upper_bound is the exclusive upper limit (< condition)
            -- For DESC: prefix is the inclusive lower limit (>= condition)
            FOR v_current IN EXECUTE v_batch_query USING _bucket_id, v_next_seek,
                CASE WHEN v_is_asc THEN COALESCE(v_upper_bound, v_prefix) ELSE v_prefix END, v_file_batch_size
            LOOP
                v_common_prefix := storage.get_common_prefix(v_current.name, v_prefix, delimiter_param);

                IF v_common_prefix IS NOT NULL THEN
                    -- Hit a folder: exit batch, let peek handle it
                    v_next_seek := v_current.name;
                    EXIT;
                END IF;

                -- Emit file
                name := v_current.name;
                id := v_current.id;
                updated_at := v_current.updated_at;
                created_at := v_current.created_at;
                last_accessed_at := v_current.last_accessed_at;
                metadata := v_current.metadata;
                RETURN NEXT;
                v_count := v_count + 1;

                -- Advance seek past this file
                IF v_is_asc THEN
                    v_next_seek := v_current.name || delimiter_param;
                ELSE
                    v_next_seek := v_current.name;
                END IF;

                EXIT WHEN v_count >= max_keys;
            END LOOP;
        END IF;
    END LOOP;
END;
$_$;


--
-- Name: operation(); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.operation() RETURNS text
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
    RETURN current_setting('storage.operation', true);
END;
$$;


--
-- Name: protect_delete(); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.protect_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Check if storage.allow_delete_query is set to 'true'
    IF COALESCE(current_setting('storage.allow_delete_query', true), 'false') != 'true' THEN
        RAISE EXCEPTION 'Direct deletion from storage tables is not allowed. Use the Storage API instead.'
            USING HINT = 'This prevents accidental data loss from orphaned objects.',
                  ERRCODE = '42501';
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: search(text, text, integer, integer, integer, text, text, text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.search(prefix text, bucketname text, limits integer DEFAULT 100, levels integer DEFAULT 1, offsets integer DEFAULT 0, search text DEFAULT ''::text, sortcolumn text DEFAULT 'name'::text, sortorder text DEFAULT 'asc'::text) RETURNS TABLE(name text, id uuid, updated_at timestamp with time zone, created_at timestamp with time zone, last_accessed_at timestamp with time zone, metadata jsonb)
    LANGUAGE plpgsql STABLE
    AS $_$
DECLARE
    v_peek_name TEXT;
    v_current RECORD;
    v_common_prefix TEXT;
    v_delimiter CONSTANT TEXT := '/';

    -- Configuration
    v_limit INT;
    v_prefix TEXT;
    v_prefix_lower TEXT;
    v_is_asc BOOLEAN;
    v_order_by TEXT;
    v_sort_order TEXT;
    v_upper_bound TEXT;
    v_file_batch_size INT;

    -- Dynamic SQL for batch query only
    v_batch_query TEXT;

    -- Seek state
    v_next_seek TEXT;
    v_count INT := 0;
    v_skipped INT := 0;
BEGIN
    -- ========================================================================
    -- INITIALIZATION
    -- ========================================================================
    v_limit := LEAST(coalesce(limits, 100), 1500);
    v_prefix := coalesce(prefix, '') || coalesce(search, '');
    v_prefix_lower := lower(v_prefix);
    v_is_asc := lower(coalesce(sortorder, 'asc')) = 'asc';
    v_file_batch_size := LEAST(GREATEST(v_limit * 2, 100), 1000);

    -- Validate sort column
    CASE lower(coalesce(sortcolumn, 'name'))
        WHEN 'name' THEN v_order_by := 'name';
        WHEN 'updated_at' THEN v_order_by := 'updated_at';
        WHEN 'created_at' THEN v_order_by := 'created_at';
        WHEN 'last_accessed_at' THEN v_order_by := 'last_accessed_at';
        ELSE v_order_by := 'name';
    END CASE;

    v_sort_order := CASE WHEN v_is_asc THEN 'asc' ELSE 'desc' END;

    -- ========================================================================
    -- NON-NAME SORTING: Use path_tokens approach (unchanged)
    -- ========================================================================
    IF v_order_by != 'name' THEN
        RETURN QUERY EXECUTE format(
            $sql$
            WITH folders AS (
                SELECT path_tokens[$1] AS folder
                FROM storage.objects
                WHERE objects.name ILIKE $2 || '%%'
                  AND bucket_id = $3
                  AND array_length(objects.path_tokens, 1) <> $1
                GROUP BY folder
                ORDER BY folder %s
            )
            (SELECT folder AS "name",
                   NULL::uuid AS id,
                   NULL::timestamptz AS updated_at,
                   NULL::timestamptz AS created_at,
                   NULL::timestamptz AS last_accessed_at,
                   NULL::jsonb AS metadata FROM folders)
            UNION ALL
            (SELECT path_tokens[$1] AS "name",
                   id, updated_at, created_at, last_accessed_at, metadata
             FROM storage.objects
             WHERE objects.name ILIKE $2 || '%%'
               AND bucket_id = $3
               AND array_length(objects.path_tokens, 1) = $1
             ORDER BY %I %s)
            LIMIT $4 OFFSET $5
            $sql$, v_sort_order, v_order_by, v_sort_order
        ) USING levels, v_prefix, bucketname, v_limit, offsets;
        RETURN;
    END IF;

    -- ========================================================================
    -- NAME SORTING: Hybrid skip-scan with batch optimization
    -- ========================================================================

    -- Calculate upper bound for prefix filtering
    IF v_prefix_lower = '' THEN
        v_upper_bound := NULL;
    ELSIF right(v_prefix_lower, 1) = v_delimiter THEN
        v_upper_bound := left(v_prefix_lower, -1) || chr(ascii(v_delimiter) + 1);
    ELSE
        v_upper_bound := left(v_prefix_lower, -1) || chr(ascii(right(v_prefix_lower, 1)) + 1);
    END IF;

    -- Build batch query (dynamic SQL - called infrequently, amortized over many rows)
    IF v_is_asc THEN
        IF v_upper_bound IS NOT NULL THEN
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND lower(o.name) COLLATE "C" >= $2 ' ||
                'AND lower(o.name) COLLATE "C" < $3 ORDER BY lower(o.name) COLLATE "C" ASC LIMIT $4';
        ELSE
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND lower(o.name) COLLATE "C" >= $2 ' ||
                'ORDER BY lower(o.name) COLLATE "C" ASC LIMIT $4';
        END IF;
    ELSE
        IF v_upper_bound IS NOT NULL THEN
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND lower(o.name) COLLATE "C" < $2 ' ||
                'AND lower(o.name) COLLATE "C" >= $3 ORDER BY lower(o.name) COLLATE "C" DESC LIMIT $4';
        ELSE
            v_batch_query := 'SELECT o.name, o.id, o.updated_at, o.created_at, o.last_accessed_at, o.metadata ' ||
                'FROM storage.objects o WHERE o.bucket_id = $1 AND lower(o.name) COLLATE "C" < $2 ' ||
                'ORDER BY lower(o.name) COLLATE "C" DESC LIMIT $4';
        END IF;
    END IF;

    -- Initialize seek position
    IF v_is_asc THEN
        v_next_seek := v_prefix_lower;
    ELSE
        -- DESC: find the last item in range first (static SQL)
        IF v_upper_bound IS NOT NULL THEN
            SELECT o.name INTO v_peek_name FROM storage.objects o
            WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" >= v_prefix_lower AND lower(o.name) COLLATE "C" < v_upper_bound
            ORDER BY lower(o.name) COLLATE "C" DESC LIMIT 1;
        ELSIF v_prefix_lower <> '' THEN
            SELECT o.name INTO v_peek_name FROM storage.objects o
            WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" >= v_prefix_lower
            ORDER BY lower(o.name) COLLATE "C" DESC LIMIT 1;
        ELSE
            SELECT o.name INTO v_peek_name FROM storage.objects o
            WHERE o.bucket_id = bucketname
            ORDER BY lower(o.name) COLLATE "C" DESC LIMIT 1;
        END IF;

        IF v_peek_name IS NOT NULL THEN
            v_next_seek := lower(v_peek_name) || v_delimiter;
        ELSE
            RETURN;
        END IF;
    END IF;

    -- ========================================================================
    -- MAIN LOOP: Hybrid peek-then-batch algorithm
    -- Uses STATIC SQL for peek (hot path) and DYNAMIC SQL for batch
    -- ========================================================================
    LOOP
        EXIT WHEN v_count >= v_limit;

        -- STEP 1: PEEK using STATIC SQL (plan cached, very fast)
        IF v_is_asc THEN
            IF v_upper_bound IS NOT NULL THEN
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" >= v_next_seek AND lower(o.name) COLLATE "C" < v_upper_bound
                ORDER BY lower(o.name) COLLATE "C" ASC LIMIT 1;
            ELSE
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" >= v_next_seek
                ORDER BY lower(o.name) COLLATE "C" ASC LIMIT 1;
            END IF;
        ELSE
            IF v_upper_bound IS NOT NULL THEN
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" < v_next_seek AND lower(o.name) COLLATE "C" >= v_prefix_lower
                ORDER BY lower(o.name) COLLATE "C" DESC LIMIT 1;
            ELSIF v_prefix_lower <> '' THEN
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" < v_next_seek AND lower(o.name) COLLATE "C" >= v_prefix_lower
                ORDER BY lower(o.name) COLLATE "C" DESC LIMIT 1;
            ELSE
                SELECT o.name INTO v_peek_name FROM storage.objects o
                WHERE o.bucket_id = bucketname AND lower(o.name) COLLATE "C" < v_next_seek
                ORDER BY lower(o.name) COLLATE "C" DESC LIMIT 1;
            END IF;
        END IF;

        EXIT WHEN v_peek_name IS NULL;

        -- STEP 2: Check if this is a FOLDER or FILE
        v_common_prefix := storage.get_common_prefix(lower(v_peek_name), v_prefix_lower, v_delimiter);

        IF v_common_prefix IS NOT NULL THEN
            -- FOLDER: Handle offset, emit if needed, skip to next folder
            IF v_skipped < offsets THEN
                v_skipped := v_skipped + 1;
            ELSE
                name := split_part(rtrim(storage.get_common_prefix(v_peek_name, v_prefix, v_delimiter), v_delimiter), v_delimiter, levels);
                id := NULL;
                updated_at := NULL;
                created_at := NULL;
                last_accessed_at := NULL;
                metadata := NULL;
                RETURN NEXT;
                v_count := v_count + 1;
            END IF;

            -- Advance seek past the folder range
            IF v_is_asc THEN
                v_next_seek := lower(left(v_common_prefix, -1)) || chr(ascii(v_delimiter) + 1);
            ELSE
                v_next_seek := lower(v_common_prefix);
            END IF;
        ELSE
            -- FILE: Batch fetch using DYNAMIC SQL (overhead amortized over many rows)
            -- For ASC: upper_bound is the exclusive upper limit (< condition)
            -- For DESC: prefix_lower is the inclusive lower limit (>= condition)
            FOR v_current IN EXECUTE v_batch_query
                USING bucketname, v_next_seek,
                    CASE WHEN v_is_asc THEN COALESCE(v_upper_bound, v_prefix_lower) ELSE v_prefix_lower END, v_file_batch_size
            LOOP
                v_common_prefix := storage.get_common_prefix(lower(v_current.name), v_prefix_lower, v_delimiter);

                IF v_common_prefix IS NOT NULL THEN
                    -- Hit a folder: exit batch, let peek handle it
                    v_next_seek := lower(v_current.name);
                    EXIT;
                END IF;

                -- Handle offset skipping
                IF v_skipped < offsets THEN
                    v_skipped := v_skipped + 1;
                ELSE
                    -- Emit file
                    name := split_part(v_current.name, v_delimiter, levels);
                    id := v_current.id;
                    updated_at := v_current.updated_at;
                    created_at := v_current.created_at;
                    last_accessed_at := v_current.last_accessed_at;
                    metadata := v_current.metadata;
                    RETURN NEXT;
                    v_count := v_count + 1;
                END IF;

                -- Advance seek past this file
                IF v_is_asc THEN
                    v_next_seek := lower(v_current.name) || v_delimiter;
                ELSE
                    v_next_seek := lower(v_current.name);
                END IF;

                EXIT WHEN v_count >= v_limit;
            END LOOP;
        END IF;
    END LOOP;
END;
$_$;


--
-- Name: search_by_timestamp(text, text, integer, integer, text, text, text, text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.search_by_timestamp(p_prefix text, p_bucket_id text, p_limit integer, p_level integer, p_start_after text, p_sort_order text, p_sort_column text, p_sort_column_after text) RETURNS TABLE(key text, name text, id uuid, updated_at timestamp with time zone, created_at timestamp with time zone, last_accessed_at timestamp with time zone, metadata jsonb)
    LANGUAGE plpgsql STABLE
    AS $_$
DECLARE
    v_cursor_op text;
    v_query text;
    v_prefix text;
BEGIN
    v_prefix := coalesce(p_prefix, '');

    IF p_sort_order = 'asc' THEN
        v_cursor_op := '>';
    ELSE
        v_cursor_op := '<';
    END IF;

    v_query := format($sql$
        WITH raw_objects AS (
            SELECT
                o.name AS obj_name,
                o.id AS obj_id,
                o.updated_at AS obj_updated_at,
                o.created_at AS obj_created_at,
                o.last_accessed_at AS obj_last_accessed_at,
                o.metadata AS obj_metadata,
                storage.get_common_prefix(o.name, $1, '/') AS common_prefix
            FROM storage.objects o
            WHERE o.bucket_id = $2
              AND o.name COLLATE "C" LIKE $1 || '%%'
        ),
        -- Aggregate common prefixes (folders)
        -- Both created_at and updated_at use MIN(obj_created_at) to match the old prefixes table behavior
        aggregated_prefixes AS (
            SELECT
                rtrim(common_prefix, '/') AS name,
                NULL::uuid AS id,
                MIN(obj_created_at) AS updated_at,
                MIN(obj_created_at) AS created_at,
                NULL::timestamptz AS last_accessed_at,
                NULL::jsonb AS metadata,
                TRUE AS is_prefix
            FROM raw_objects
            WHERE common_prefix IS NOT NULL
            GROUP BY common_prefix
        ),
        leaf_objects AS (
            SELECT
                obj_name AS name,
                obj_id AS id,
                obj_updated_at AS updated_at,
                obj_created_at AS created_at,
                obj_last_accessed_at AS last_accessed_at,
                obj_metadata AS metadata,
                FALSE AS is_prefix
            FROM raw_objects
            WHERE common_prefix IS NULL
        ),
        combined AS (
            SELECT * FROM aggregated_prefixes
            UNION ALL
            SELECT * FROM leaf_objects
        ),
        filtered AS (
            SELECT *
            FROM combined
            WHERE (
                $5 = ''
                OR ROW(
                    date_trunc('milliseconds', %I),
                    name COLLATE "C"
                ) %s ROW(
                    COALESCE(NULLIF($6, '')::timestamptz, 'epoch'::timestamptz),
                    $5
                )
            )
        )
        SELECT
            split_part(name, '/', $3) AS key,
            name,
            id,
            updated_at,
            created_at,
            last_accessed_at,
            metadata
        FROM filtered
        ORDER BY
            COALESCE(date_trunc('milliseconds', %I), 'epoch'::timestamptz) %s,
            name COLLATE "C" %s
        LIMIT $4
    $sql$,
        p_sort_column,
        v_cursor_op,
        p_sort_column,
        p_sort_order,
        p_sort_order
    );

    RETURN QUERY EXECUTE v_query
    USING v_prefix, p_bucket_id, p_level, p_limit, p_start_after, p_sort_column_after;
END;
$_$;


--
-- Name: search_v2(text, text, integer, integer, text, text, text, text); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.search_v2(prefix text, bucket_name text, limits integer DEFAULT 100, levels integer DEFAULT 1, start_after text DEFAULT ''::text, sort_order text DEFAULT 'asc'::text, sort_column text DEFAULT 'name'::text, sort_column_after text DEFAULT ''::text) RETURNS TABLE(key text, name text, id uuid, updated_at timestamp with time zone, created_at timestamp with time zone, last_accessed_at timestamp with time zone, metadata jsonb)
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
    v_sort_col text;
    v_sort_ord text;
    v_limit int;
BEGIN
    -- Cap limit to maximum of 1500 records
    v_limit := LEAST(coalesce(limits, 100), 1500);

    -- Validate and normalize sort_order
    v_sort_ord := lower(coalesce(sort_order, 'asc'));
    IF v_sort_ord NOT IN ('asc', 'desc') THEN
        v_sort_ord := 'asc';
    END IF;

    -- Validate and normalize sort_column
    v_sort_col := lower(coalesce(sort_column, 'name'));
    IF v_sort_col NOT IN ('name', 'updated_at', 'created_at') THEN
        v_sort_col := 'name';
    END IF;

    -- Route to appropriate implementation
    IF v_sort_col = 'name' THEN
        -- Use list_objects_with_delimiter for name sorting (most efficient: O(k * log n))
        RETURN QUERY
        SELECT
            split_part(l.name, '/', levels) AS key,
            l.name AS name,
            l.id,
            l.updated_at,
            l.created_at,
            l.last_accessed_at,
            l.metadata
        FROM storage.list_objects_with_delimiter(
            bucket_name,
            coalesce(prefix, ''),
            '/',
            v_limit,
            start_after,
            '',
            v_sort_ord
        ) l;
    ELSE
        -- Use aggregation approach for timestamp sorting
        -- Not efficient for large datasets but supports correct pagination
        RETURN QUERY SELECT * FROM storage.search_by_timestamp(
            prefix, bucket_name, v_limit, levels, start_after,
            v_sort_ord, v_sort_col, sort_column_after
        );
    END IF;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: storage; Owner: -
--

CREATE FUNCTION storage.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW; 
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_log_entries; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.audit_log_entries (
    instance_id uuid,
    id uuid NOT NULL,
    payload json,
    created_at timestamp with time zone,
    ip_address character varying(64) DEFAULT ''::character varying NOT NULL
);


--
-- Name: custom_oauth_providers; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.custom_oauth_providers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_type text NOT NULL,
    identifier text NOT NULL,
    name text NOT NULL,
    client_id text NOT NULL,
    client_secret text NOT NULL,
    acceptable_client_ids text[] DEFAULT '{}'::text[] NOT NULL,
    scopes text[] DEFAULT '{}'::text[] NOT NULL,
    pkce_enabled boolean DEFAULT true NOT NULL,
    attribute_mapping jsonb DEFAULT '{}'::jsonb NOT NULL,
    authorization_params jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    email_optional boolean DEFAULT false NOT NULL,
    issuer text,
    discovery_url text,
    skip_nonce_check boolean DEFAULT false NOT NULL,
    cached_discovery jsonb,
    discovery_cached_at timestamp with time zone,
    authorization_url text,
    token_url text,
    userinfo_url text,
    jwks_uri text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT custom_oauth_providers_authorization_url_https CHECK (((authorization_url IS NULL) OR (authorization_url ~~ 'https://%'::text))),
    CONSTRAINT custom_oauth_providers_authorization_url_length CHECK (((authorization_url IS NULL) OR (char_length(authorization_url) <= 2048))),
    CONSTRAINT custom_oauth_providers_client_id_length CHECK (((char_length(client_id) >= 1) AND (char_length(client_id) <= 512))),
    CONSTRAINT custom_oauth_providers_discovery_url_length CHECK (((discovery_url IS NULL) OR (char_length(discovery_url) <= 2048))),
    CONSTRAINT custom_oauth_providers_identifier_format CHECK ((identifier ~ '^[a-z0-9][a-z0-9:-]{0,48}[a-z0-9]$'::text)),
    CONSTRAINT custom_oauth_providers_issuer_length CHECK (((issuer IS NULL) OR ((char_length(issuer) >= 1) AND (char_length(issuer) <= 2048)))),
    CONSTRAINT custom_oauth_providers_jwks_uri_https CHECK (((jwks_uri IS NULL) OR (jwks_uri ~~ 'https://%'::text))),
    CONSTRAINT custom_oauth_providers_jwks_uri_length CHECK (((jwks_uri IS NULL) OR (char_length(jwks_uri) <= 2048))),
    CONSTRAINT custom_oauth_providers_name_length CHECK (((char_length(name) >= 1) AND (char_length(name) <= 100))),
    CONSTRAINT custom_oauth_providers_oauth2_requires_endpoints CHECK (((provider_type <> 'oauth2'::text) OR ((authorization_url IS NOT NULL) AND (token_url IS NOT NULL) AND (userinfo_url IS NOT NULL)))),
    CONSTRAINT custom_oauth_providers_oidc_discovery_url_https CHECK (((provider_type <> 'oidc'::text) OR (discovery_url IS NULL) OR (discovery_url ~~ 'https://%'::text))),
    CONSTRAINT custom_oauth_providers_oidc_issuer_https CHECK (((provider_type <> 'oidc'::text) OR (issuer IS NULL) OR (issuer ~~ 'https://%'::text))),
    CONSTRAINT custom_oauth_providers_oidc_requires_issuer CHECK (((provider_type <> 'oidc'::text) OR (issuer IS NOT NULL))),
    CONSTRAINT custom_oauth_providers_provider_type_check CHECK ((provider_type = ANY (ARRAY['oauth2'::text, 'oidc'::text]))),
    CONSTRAINT custom_oauth_providers_token_url_https CHECK (((token_url IS NULL) OR (token_url ~~ 'https://%'::text))),
    CONSTRAINT custom_oauth_providers_token_url_length CHECK (((token_url IS NULL) OR (char_length(token_url) <= 2048))),
    CONSTRAINT custom_oauth_providers_userinfo_url_https CHECK (((userinfo_url IS NULL) OR (userinfo_url ~~ 'https://%'::text))),
    CONSTRAINT custom_oauth_providers_userinfo_url_length CHECK (((userinfo_url IS NULL) OR (char_length(userinfo_url) <= 2048)))
);


--
-- Name: flow_state; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.flow_state (
    id uuid NOT NULL,
    user_id uuid,
    auth_code text,
    code_challenge_method auth.code_challenge_method,
    code_challenge text,
    provider_type text NOT NULL,
    provider_access_token text,
    provider_refresh_token text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    authentication_method text NOT NULL,
    auth_code_issued_at timestamp with time zone,
    invite_token text,
    referrer text,
    oauth_client_state_id uuid,
    linking_target_id uuid,
    email_optional boolean DEFAULT false NOT NULL
);


--
-- Name: identities; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.identities (
    provider_id text NOT NULL,
    user_id uuid NOT NULL,
    identity_data jsonb NOT NULL,
    provider text NOT NULL,
    last_sign_in_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    email text GENERATED ALWAYS AS (lower((identity_data ->> 'email'::text))) STORED,
    id uuid DEFAULT gen_random_uuid() NOT NULL
);


--
-- Name: instances; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.instances (
    id uuid NOT NULL,
    uuid uuid,
    raw_base_config text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: mfa_amr_claims; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.mfa_amr_claims (
    session_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    authentication_method text NOT NULL,
    id uuid NOT NULL
);


--
-- Name: mfa_challenges; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.mfa_challenges (
    id uuid NOT NULL,
    factor_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    verified_at timestamp with time zone,
    ip_address inet NOT NULL,
    otp_code text,
    web_authn_session_data jsonb
);


--
-- Name: mfa_factors; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.mfa_factors (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    friendly_name text,
    factor_type auth.factor_type NOT NULL,
    status auth.factor_status NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    secret text,
    phone text,
    last_challenged_at timestamp with time zone,
    web_authn_credential jsonb,
    web_authn_aaguid uuid,
    last_webauthn_challenge_data jsonb
);


--
-- Name: oauth_authorizations; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.oauth_authorizations (
    id uuid NOT NULL,
    authorization_id text NOT NULL,
    client_id uuid NOT NULL,
    user_id uuid,
    redirect_uri text NOT NULL,
    scope text NOT NULL,
    state text,
    resource text,
    code_challenge text,
    code_challenge_method auth.code_challenge_method,
    response_type auth.oauth_response_type DEFAULT 'code'::auth.oauth_response_type NOT NULL,
    status auth.oauth_authorization_status DEFAULT 'pending'::auth.oauth_authorization_status NOT NULL,
    authorization_code text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone DEFAULT (now() + '00:03:00'::interval) NOT NULL,
    approved_at timestamp with time zone,
    nonce text,
    CONSTRAINT oauth_authorizations_authorization_code_length CHECK ((char_length(authorization_code) <= 255)),
    CONSTRAINT oauth_authorizations_code_challenge_length CHECK ((char_length(code_challenge) <= 128)),
    CONSTRAINT oauth_authorizations_expires_at_future CHECK ((expires_at > created_at)),
    CONSTRAINT oauth_authorizations_nonce_length CHECK ((char_length(nonce) <= 255)),
    CONSTRAINT oauth_authorizations_redirect_uri_length CHECK ((char_length(redirect_uri) <= 2048)),
    CONSTRAINT oauth_authorizations_resource_length CHECK ((char_length(resource) <= 2048)),
    CONSTRAINT oauth_authorizations_scope_length CHECK ((char_length(scope) <= 4096)),
    CONSTRAINT oauth_authorizations_state_length CHECK ((char_length(state) <= 4096))
);


--
-- Name: oauth_client_states; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.oauth_client_states (
    id uuid NOT NULL,
    provider_type text NOT NULL,
    code_verifier text,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: oauth_clients; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.oauth_clients (
    id uuid NOT NULL,
    client_secret_hash text,
    registration_type auth.oauth_registration_type NOT NULL,
    redirect_uris text NOT NULL,
    grant_types text NOT NULL,
    client_name text,
    client_uri text,
    logo_uri text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    client_type auth.oauth_client_type DEFAULT 'confidential'::auth.oauth_client_type NOT NULL,
    token_endpoint_auth_method text NOT NULL,
    CONSTRAINT oauth_clients_client_name_length CHECK ((char_length(client_name) <= 1024)),
    CONSTRAINT oauth_clients_client_uri_length CHECK ((char_length(client_uri) <= 2048)),
    CONSTRAINT oauth_clients_logo_uri_length CHECK ((char_length(logo_uri) <= 2048)),
    CONSTRAINT oauth_clients_token_endpoint_auth_method_check CHECK ((token_endpoint_auth_method = ANY (ARRAY['client_secret_basic'::text, 'client_secret_post'::text, 'none'::text])))
);


--
-- Name: oauth_consents; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.oauth_consents (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    client_id uuid NOT NULL,
    scopes text NOT NULL,
    granted_at timestamp with time zone DEFAULT now() NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT oauth_consents_revoked_after_granted CHECK (((revoked_at IS NULL) OR (revoked_at >= granted_at))),
    CONSTRAINT oauth_consents_scopes_length CHECK ((char_length(scopes) <= 2048)),
    CONSTRAINT oauth_consents_scopes_not_empty CHECK ((char_length(TRIM(BOTH FROM scopes)) > 0))
);


--
-- Name: one_time_tokens; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.one_time_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_type auth.one_time_token_type NOT NULL,
    token_hash text NOT NULL,
    relates_to text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT one_time_tokens_token_hash_check CHECK ((char_length(token_hash) > 0))
);


--
-- Name: refresh_tokens; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.refresh_tokens (
    instance_id uuid,
    id bigint NOT NULL,
    token character varying(255),
    user_id character varying(255),
    revoked boolean,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    parent character varying(255),
    session_id uuid
);


--
-- Name: refresh_tokens_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.refresh_tokens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: refresh_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.refresh_tokens_id_seq OWNED BY auth.refresh_tokens.id;


--
-- Name: saml_providers; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.saml_providers (
    id uuid NOT NULL,
    sso_provider_id uuid NOT NULL,
    entity_id text NOT NULL,
    metadata_xml text NOT NULL,
    metadata_url text,
    attribute_mapping jsonb,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    name_id_format text,
    CONSTRAINT "entity_id not empty" CHECK ((char_length(entity_id) > 0)),
    CONSTRAINT "metadata_url not empty" CHECK (((metadata_url = NULL::text) OR (char_length(metadata_url) > 0))),
    CONSTRAINT "metadata_xml not empty" CHECK ((char_length(metadata_xml) > 0))
);


--
-- Name: saml_relay_states; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.saml_relay_states (
    id uuid NOT NULL,
    sso_provider_id uuid NOT NULL,
    request_id text NOT NULL,
    for_email text,
    redirect_to text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    flow_state_id uuid,
    CONSTRAINT "request_id not empty" CHECK ((char_length(request_id) > 0))
);


--
-- Name: schema_migrations; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.schema_migrations (
    version character varying(255) NOT NULL
);


--
-- Name: sessions; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    factor_id uuid,
    aal auth.aal_level,
    not_after timestamp with time zone,
    refreshed_at timestamp without time zone,
    user_agent text,
    ip inet,
    tag text,
    oauth_client_id uuid,
    refresh_token_hmac_key text,
    refresh_token_counter bigint,
    scopes text,
    CONSTRAINT sessions_scopes_length CHECK ((char_length(scopes) <= 4096))
);


--
-- Name: sso_domains; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.sso_domains (
    id uuid NOT NULL,
    sso_provider_id uuid NOT NULL,
    domain text NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    CONSTRAINT "domain not empty" CHECK ((char_length(domain) > 0))
);


--
-- Name: sso_providers; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.sso_providers (
    id uuid NOT NULL,
    resource_id text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    disabled boolean,
    CONSTRAINT "resource_id not empty" CHECK (((resource_id = NULL::text) OR (char_length(resource_id) > 0)))
);


--
-- Name: users; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.users (
    instance_id uuid,
    id uuid NOT NULL,
    aud character varying(255),
    role character varying(255),
    email character varying(255),
    encrypted_password character varying(255),
    email_confirmed_at timestamp with time zone,
    invited_at timestamp with time zone,
    confirmation_token character varying(255),
    confirmation_sent_at timestamp with time zone,
    recovery_token character varying(255),
    recovery_sent_at timestamp with time zone,
    email_change_token_new character varying(255),
    email_change character varying(255),
    email_change_sent_at timestamp with time zone,
    last_sign_in_at timestamp with time zone,
    raw_app_meta_data jsonb,
    raw_user_meta_data jsonb,
    is_super_admin boolean,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    phone text DEFAULT NULL::character varying,
    phone_confirmed_at timestamp with time zone,
    phone_change text DEFAULT ''::character varying,
    phone_change_token character varying(255) DEFAULT ''::character varying,
    phone_change_sent_at timestamp with time zone,
    confirmed_at timestamp with time zone GENERATED ALWAYS AS (LEAST(email_confirmed_at, phone_confirmed_at)) STORED,
    email_change_token_current character varying(255) DEFAULT ''::character varying,
    email_change_confirm_status smallint DEFAULT 0,
    banned_until timestamp with time zone,
    reauthentication_token character varying(255) DEFAULT ''::character varying,
    reauthentication_sent_at timestamp with time zone,
    is_sso_user boolean DEFAULT false NOT NULL,
    deleted_at timestamp with time zone,
    is_anonymous boolean DEFAULT false NOT NULL,
    CONSTRAINT users_email_change_confirm_status_check CHECK (((email_change_confirm_status >= 0) AND (email_change_confirm_status <= 2)))
);


--
-- Name: webauthn_challenges; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.webauthn_challenges (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    challenge_type text NOT NULL,
    session_data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT webauthn_challenges_challenge_type_check CHECK ((challenge_type = ANY (ARRAY['signup'::text, 'registration'::text, 'authentication'::text])))
);


--
-- Name: webauthn_credentials; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.webauthn_credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    credential_id bytea NOT NULL,
    public_key bytea NOT NULL,
    attestation_type text DEFAULT ''::text NOT NULL,
    aaguid uuid,
    sign_count bigint DEFAULT 0 NOT NULL,
    transports jsonb DEFAULT '[]'::jsonb NOT NULL,
    backup_eligible boolean DEFAULT false NOT NULL,
    backed_up boolean DEFAULT false NOT NULL,
    friendly_name text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone
);


--
-- Name: Addendum; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Addendum" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "articleSlug" text NOT NULL,
    "noosphereArticleId" text,
    "findingId" text DEFAULT ''::text NOT NULL,
    summary text NOT NULL,
    body text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "reviewerConfig" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "publishedAt" timestamp(3) without time zone,
    "dismissedAt" timestamp(3) without time zone,
    "dismissedReason" text DEFAULT ''::text NOT NULL
);


--
-- Name: AlertEvent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."AlertEvent" (
    id text NOT NULL,
    "ruleName" text NOT NULL,
    method text NOT NULL,
    metric text NOT NULL,
    value double precision NOT NULL,
    threshold double precision NOT NULL,
    "firedAt" timestamp(3) without time zone NOT NULL,
    "acknowledgedAt" timestamp(3) without time zone,
    "acknowledgedBy" text,
    "deliveredTo" jsonb DEFAULT '[]'::jsonb NOT NULL
);


--
-- Name: AlertRule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."AlertRule" (
    id text NOT NULL,
    name text NOT NULL,
    metric text NOT NULL,
    threshold double precision NOT NULL,
    method text DEFAULT '*'::text NOT NULL,
    "windowMinutes" integer DEFAULT 15 NOT NULL,
    "minSamples" integer DEFAULT 5 NOT NULL,
    "webhookUrl" text,
    enabled boolean DEFAULT true NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: AnchorRevision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."AnchorRevision" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "methodName" text NOT NULL,
    "methodVersion" text NOT NULL,
    "revisionId" text NOT NULL,
    "embeddingModel" text NOT NULL,
    anchors jsonb NOT NULL,
    "inRadius" double precision NOT NULL,
    "edgeRadius" double precision NOT NULL,
    notes text DEFAULT ''::text NOT NULL,
    active boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ApiKey; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ApiKey" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "founderId" text NOT NULL,
    label text NOT NULL,
    prefix text NOT NULL,
    "keyHash" text NOT NULL,
    scopes text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastUsedAt" timestamp(3) without time zone,
    "revokedAt" timestamp(3) without time zone
);


--
-- Name: AttentionAction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."AttentionAction" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "founderId" text NOT NULL,
    queue text NOT NULL,
    "itemId" text NOT NULL,
    action text NOT NULL,
    "snoozedUntil" timestamp(3) without time zone,
    reason text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: AuditEvent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."AuditEvent" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "founderId" text NOT NULL,
    "uploadId" text,
    action text NOT NULL,
    detail text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: CalibrationModel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CalibrationModel" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    domain text NOT NULL,
    version integer NOT NULL,
    "fitAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "sampleSize" integer NOT NULL,
    "resolutionHash" text NOT NULL,
    knots jsonb NOT NULL,
    active boolean DEFAULT true NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: CitationVerdict; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CitationVerdict" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "citationKind" text NOT NULL,
    "citationId" text NOT NULL,
    "sourceId" text NOT NULL,
    relation public."CitationRelation" NOT NULL,
    "relationHolds" public."CitationVerdictLabel" NOT NULL,
    confidence double precision NOT NULL,
    "excerptUsed" text NOT NULL,
    "statedClaim" text NOT NULL,
    "modelVersion" text NOT NULL,
    "cascadeWeight" double precision DEFAULT 0.0 NOT NULL,
    "overriddenById" text,
    "overrideReason" text,
    "overriddenAt" timestamp(3) without time zone,
    "rawPayload" jsonb,
    "computedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: Conclusion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Conclusion" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "noosphereId" text,
    text text NOT NULL,
    "confidenceTier" text NOT NULL,
    rationale text DEFAULT ''::text NOT NULL,
    "supportingPrincipleIds" text DEFAULT '[]'::text NOT NULL,
    "evidenceChainClaimIds" text DEFAULT '[]'::text NOT NULL,
    "dissentClaimIds" text DEFAULT '[]'::text NOT NULL,
    confidence double precision DEFAULT 0 NOT NULL,
    "topicHint" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "attributedFounderId" text,
    "normalizedText" text,
    "embeddingJson" text,
    "updatedAt" timestamp(3) without time zone
);


--
-- Name: ConclusionDeletionRequest; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ConclusionDeletionRequest" (
    id text NOT NULL,
    "conclusionId" text NOT NULL,
    "requesterId" text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    reason text,
    decision text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "respondedAt" timestamp(3) without time zone
);


--
-- Name: ConclusionMethod; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ConclusionMethod" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "conclusionId" text NOT NULL,
    "methodName" text NOT NULL,
    "methodVersion" text NOT NULL,
    weight double precision DEFAULT 1.0 NOT NULL,
    domain text DEFAULT ''::text NOT NULL,
    rationale text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ConclusionSource; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ConclusionSource" (
    "conclusionId" text NOT NULL,
    "uploadId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ContactSubmission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ContactSubmission" (
    id text NOT NULL,
    "fromName" text NOT NULL,
    "fromEmail" text NOT NULL,
    subject text,
    body text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "organizationId" text,
    "ipHash" text NOT NULL,
    "userAgent" text,
    "triagedAt" timestamp(3) without time zone,
    "triagedBy" text,
    notes text
);


--
-- Name: Contradiction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Contradiction" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "claimAId" text NOT NULL,
    "claimBId" text NOT NULL,
    severity double precision NOT NULL,
    "sixLayerJson" text,
    narrative text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "sourceUploadId" text,
    status text DEFAULT 'active'::text NOT NULL,
    resolution text,
    "resolvedById" text,
    "resolvedAt" timestamp(3) without time zone
);


--
-- Name: CritiqueBountyPayout; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CritiqueBountyPayout" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "critiqueSubmissionId" text NOT NULL,
    "amountUsd" integer DEFAULT 500 NOT NULL,
    "payoutMode" text DEFAULT 'self'::text NOT NULL,
    destination text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'pending_founder_confirmation'::text NOT NULL,
    "cancellationNote" text DEFAULT ''::text NOT NULL,
    "confirmedById" text,
    "confirmedAt" timestamp(3) without time zone,
    "externalRef" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: CritiqueSubmission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CritiqueSubmission" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "articleSlug" text NOT NULL,
    "publishedConclusionId" text,
    "targetClaim" text NOT NULL,
    "counterEvidence" text NOT NULL,
    "derivationMethod" text NOT NULL,
    citations text DEFAULT ''::text NOT NULL,
    "submitterEmail" text NOT NULL,
    "displayName" text DEFAULT ''::text NOT NULL,
    "publicUrl" text DEFAULT ''::text NOT NULL,
    bio text DEFAULT ''::text NOT NULL,
    orcid text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "moderatorNote" text DEFAULT ''::text NOT NULL,
    "severityLabel" text DEFAULT ''::text NOT NULL,
    "severityValue" double precision DEFAULT 0 NOT NULL,
    "decidedById" text,
    "decidedAt" timestamp(3) without time zone,
    "triggeredRevisionId" text,
    "addendumId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: CurrentEvent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CurrentEvent" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    source public."CurrentEventSource" NOT NULL,
    "externalId" text NOT NULL,
    "authorHandle" text,
    text text NOT NULL,
    url text,
    "capturedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "observedAt" timestamp(3) without time zone NOT NULL,
    "topicHint" text,
    "isNearDuplicate" boolean DEFAULT false NOT NULL,
    embedding bytea,
    status public."CurrentEventStatus" DEFAULT 'OBSERVED'::public."CurrentEventStatus" NOT NULL,
    "dedupeHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    metrics jsonb
);


--
-- Name: DashboardDismissal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."DashboardDismissal" (
    id text NOT NULL,
    "founderId" text NOT NULL,
    "conclusionId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: DeletionRequest; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."DeletionRequest" (
    id text NOT NULL,
    "uploadId" text NOT NULL,
    "requesterId" text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    reason text,
    decision text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "respondedAt" timestamp(3) without time zone
);


--
-- Name: DomainBoundVerdict; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."DomainBoundVerdict" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "conclusionId" text NOT NULL,
    "methodName" text NOT NULL,
    "methodVersion" text NOT NULL,
    status text NOT NULL,
    margin double precision NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    "anchorRevisionId" text,
    "matchedTags" text[] DEFAULT ARRAY[]::text[],
    "embeddingModel" text,
    evidence jsonb,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: DriftEvent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."DriftEvent" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "noosphereId" text,
    "targetId" text NOT NULL,
    "targetKind" text DEFAULT 'principle'::text NOT NULL,
    "episodeId" text DEFAULT ''::text NOT NULL,
    "observedAt" timestamp(3) without time zone NOT NULL,
    "driftScore" double precision DEFAULT 0 NOT NULL,
    notes text DEFAULT ''::text NOT NULL,
    "claimSequenceIdsJson" text DEFAULT '[]'::text NOT NULL,
    "naturalLanguageSummary" text DEFAULT ''::text NOT NULL,
    "earliestInconsistentClaimId" text DEFAULT ''::text NOT NULL,
    "authorTopicKey" text DEFAULT ''::text NOT NULL,
    "topicId" text DEFAULT ''::text NOT NULL,
    "baselineBrier" double precision,
    "baselineSlope" double precision,
    "brierMean" double precision,
    "calibrationSlope" double precision,
    "directionalBias" double precision,
    evidence jsonb,
    "methodDomain" text,
    "methodName" text,
    "methodVersion" text,
    "pValue" double precision,
    "sampleSize" integer,
    seed integer,
    severity text,
    sigma double precision,
    "windowDays" integer
);


--
-- Name: EquityInstrument; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EquityInstrument" (
    id character varying NOT NULL,
    symbol character varying(16) NOT NULL,
    exchange character varying(16) NOT NULL,
    "assetClass" character varying NOT NULL,
    name character varying(280) NOT NULL,
    cusip character varying(16),
    figi character varying(16),
    "isTradable" boolean NOT NULL,
    "lastPrice" numeric(18,6),
    "lastPriceAt" timestamp without time zone,
    currency character varying(8) DEFAULT 'USD'::character varying NOT NULL,
    "createdAt" timestamp without time zone NOT NULL,
    "updatedAt" timestamp without time zone NOT NULL
);


--
-- Name: EquityPortfolioState; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EquityPortfolioState" (
    id character varying NOT NULL,
    "organizationId" character varying NOT NULL,
    "paperBalanceUsd" numeric(14,2) NOT NULL,
    "liveBalanceUsd" numeric(14,2),
    "dailyLossUsd" numeric(14,2) NOT NULL,
    "dailyLossWindowResetAt" timestamp without time zone NOT NULL,
    "killSwitchEngaged" boolean NOT NULL,
    "killSwitchReason" character varying,
    "updatedAt" timestamp without time zone NOT NULL
);


--
-- Name: EquityPosition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EquityPosition" (
    id character varying NOT NULL,
    "signalId" character varying NOT NULL,
    "instrumentId" character varying NOT NULL,
    "organizationId" character varying NOT NULL,
    mode character varying NOT NULL,
    side character varying NOT NULL,
    qty numeric(20,6) NOT NULL,
    "entryPrice" numeric(18,6) NOT NULL,
    "entryAt" timestamp without time zone NOT NULL,
    "exitPrice" numeric(18,6),
    "exitAt" timestamp without time zone,
    status character varying NOT NULL,
    "externalOrderId" character varying,
    "realizedPnlUsd" numeric(14,4),
    "unrealizedPnlUsd" numeric(14,4),
    "liveAuthorizedAt" timestamp without time zone,
    "createdAt" timestamp without time zone NOT NULL,
    "updatedAt" timestamp without time zone NOT NULL,
    CONSTRAINT "EquityPosition_live_requires_authorizedAt_check" CHECK ((((mode)::text <> 'LIVE'::text) OR ("liveAuthorizedAt" IS NOT NULL)))
);


--
-- Name: EquityPriceTick; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EquityPriceTick" (
    id character varying NOT NULL,
    "instrumentId" character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    open numeric(18,6) NOT NULL,
    high numeric(18,6) NOT NULL,
    low numeric(18,6) NOT NULL,
    close numeric(18,6) NOT NULL,
    volume numeric(20,4) NOT NULL,
    source character varying NOT NULL,
    "createdAt" timestamp without time zone NOT NULL
);


--
-- Name: EquitySignal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EquitySignal" (
    id character varying NOT NULL,
    "instrumentId" character varying NOT NULL,
    "organizationId" character varying NOT NULL,
    direction character varying NOT NULL,
    "confidenceLow" numeric(8,6) NOT NULL,
    "confidenceHigh" numeric(8,6) NOT NULL,
    "targetPriceLow" numeric(18,6),
    "targetPriceHigh" numeric(18,6),
    "horizonDays" integer NOT NULL,
    headline character varying(140) NOT NULL,
    reasoning text NOT NULL,
    "modelName" character varying NOT NULL,
    "promptTokens" integer NOT NULL,
    "completionTokens" integer NOT NULL,
    status character varying NOT NULL,
    "abstentionReason" character varying,
    "liveAuthorizedAt" timestamp without time zone,
    "liveAuthorizedBy" character varying,
    "createdAt" timestamp without time zone NOT NULL,
    "updatedAt" timestamp without time zone NOT NULL
);


--
-- Name: EquitySignalCitation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EquitySignalCitation" (
    id character varying NOT NULL,
    "signalId" character varying NOT NULL,
    "sourceType" character varying NOT NULL,
    "sourceId" character varying NOT NULL,
    "quotedSpan" text NOT NULL,
    "supportLabel" character varying NOT NULL,
    "createdAt" timestamp without time zone NOT NULL
);


--
-- Name: EventOpinion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."EventOpinion" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "eventId" text NOT NULL,
    stance public."OpinionStance" NOT NULL,
    confidence double precision NOT NULL,
    headline character varying(140) NOT NULL,
    "bodyMarkdown" text NOT NULL,
    "uncertaintyNotes" text[],
    "topicHint" text,
    "modelName" text NOT NULL,
    "promptTokens" integer DEFAULT 0 NOT NULL,
    "completionTokens" integer DEFAULT 0 NOT NULL,
    "abstentionReason" public."AbstentionReason",
    "generatedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "revokedAt" timestamp(3) without time zone,
    "revokedReason" text
);


--
-- Name: FollowUpMessage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."FollowUpMessage" (
    id text NOT NULL,
    "sessionId" text NOT NULL,
    role public."FollowUpRole" NOT NULL,
    content text NOT NULL,
    citations jsonb,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: FollowUpSession; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."FollowUpSession" (
    id text NOT NULL,
    "opinionId" text NOT NULL,
    "clientFingerprint" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastActivityAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ForecastBet; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastBet" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    "organizationId" text NOT NULL,
    mode public."ForecastBetMode" DEFAULT 'PAPER'::public."ForecastBetMode" NOT NULL,
    exchange public."ForecastExchange" NOT NULL,
    side public."ForecastBetSide" NOT NULL,
    "stakeUsd" numeric(12,2) NOT NULL,
    "entryPrice" numeric(8,6) NOT NULL,
    "exitPrice" numeric(8,6),
    status public."ForecastBetStatus" NOT NULL,
    "externalOrderId" text,
    "clientOrderId" text,
    "settlementPnlUsd" numeric(12,2),
    "liveAuthorizedAt" timestamp(3) without time zone,
    "confirmedAt" timestamp(3) without time zone,
    "submittedAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "settledAt" timestamp(3) without time zone,
    CONSTRAINT "ForecastBet_live_requires_authorizedAt_check" CHECK (((mode <> 'LIVE'::public."ForecastBetMode") OR ("liveAuthorizedAt" IS NOT NULL)))
);


--
-- Name: ForecastCitation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastCitation" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    "sourceType" text NOT NULL,
    "sourceId" text NOT NULL,
    "quotedSpan" text NOT NULL,
    "supportLabel" public."ForecastSupportLabel" NOT NULL,
    "retrievalScore" double precision,
    "isRevoked" boolean DEFAULT false NOT NULL,
    "revokedReason" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ForecastFollowUpMessage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastFollowUpMessage" (
    id text NOT NULL,
    "sessionId" text NOT NULL,
    role public."ForecastFollowUpRole" NOT NULL,
    content text NOT NULL,
    citations jsonb,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ForecastFollowUpSession; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastFollowUpSession" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    "clientFingerprint" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastActivityAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ForecastMarket; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastMarket" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    source public."ForecastSource" NOT NULL,
    "externalId" text NOT NULL,
    title character varying(280) NOT NULL,
    description text,
    "resolutionCriteria" text,
    category text,
    "currentYesPrice" numeric(8,6),
    "currentNoPrice" numeric(8,6),
    volume numeric(18,4),
    "openTime" timestamp(3) without time zone,
    "closeTime" timestamp(3) without time zone,
    "resolvedAt" timestamp(3) without time zone,
    "resolvedOutcome" public."ForecastOutcome",
    "rawPayload" jsonb NOT NULL,
    status public."ForecastMarketStatus" DEFAULT 'OPEN'::public."ForecastMarketStatus" NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ForecastPortfolioState; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastPortfolioState" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "paperBalanceUsd" numeric(12,2) NOT NULL,
    "liveBalanceUsd" numeric(12,2),
    "dailyLossUsd" numeric(12,2) DEFAULT 0 NOT NULL,
    "dailyLossResetAt" timestamp(3) without time zone NOT NULL,
    "killSwitchEngaged" boolean DEFAULT false NOT NULL,
    "killSwitchReason" text,
    "totalResolved" integer DEFAULT 0 NOT NULL,
    "meanBrier90d" double precision,
    "meanLogLoss90d" double precision,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ForecastPrediction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastPrediction" (
    id text NOT NULL,
    "marketId" text NOT NULL,
    "organizationId" text NOT NULL,
    "probabilityYes" numeric(8,6),
    "confidenceLow" numeric(8,6),
    "confidenceHigh" numeric(8,6),
    headline character varying(140) NOT NULL,
    reasoning text NOT NULL,
    status public."ForecastPredictionStatus" NOT NULL,
    "abstentionReason" text,
    "topicHint" text,
    "modelName" text NOT NULL,
    "promptTokens" integer DEFAULT 0 NOT NULL,
    "completionTokens" integer DEFAULT 0 NOT NULL,
    "liveAuthorizedAt" timestamp(3) without time zone,
    "liveAuthorizedBy" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ForecastResolution; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastResolution" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    "marketOutcome" public."ForecastOutcome" NOT NULL,
    "brierScore" double precision,
    "logLoss" double precision,
    "calibrationBucket" numeric(3,1),
    "resolvedAt" timestamp(3) without time zone NOT NULL,
    justification text NOT NULL,
    "rawSettlement" jsonb,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    source text DEFAULT 'VENUE'::text NOT NULL,
    "sourceUrl" text
);


--
-- Name: ForecastTrace; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ForecastTrace" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    "marketId" text NOT NULL,
    "organizationId" text NOT NULL,
    "marketTitle" character varying(280) NOT NULL,
    "principlesUsed" jsonb NOT NULL,
    "modelOutput" jsonb NOT NULL,
    "gateResults" jsonb NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Founder; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Founder" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    name text NOT NULL,
    username text NOT NULL,
    email text NOT NULL,
    "passwordHash" text NOT NULL,
    role text DEFAULT 'founder'::text NOT NULL,
    bio text,
    avatar text,
    "noosphereId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "displayName" text,
    "accountNudgeDismissedAt" timestamp(3) without time zone,
    "roleTitle" text,
    "publicUrl" text,
    "dailyDigestOptIn" boolean DEFAULT false NOT NULL
);


--
-- Name: MethodMetricRollup; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."MethodMetricRollup" (
    id text NOT NULL,
    method text NOT NULL,
    "windowStart" timestamp(3) without time zone NOT NULL,
    "windowEnd" timestamp(3) without time zone NOT NULL,
    count integer NOT NULL,
    "errorCount" integer NOT NULL,
    "p50Ms" double precision NOT NULL,
    "p95Ms" double precision NOT NULL,
    "errorRate" double precision NOT NULL,
    "costUsd" double precision NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: MethodTrackRecord; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."MethodTrackRecord" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "methodName" text NOT NULL,
    "methodVersion" text NOT NULL,
    domain text DEFAULT ''::text NOT NULL,
    "sampleSize" integer NOT NULL,
    "weightedBrier" double precision,
    "calibrationSlope" double precision,
    "calibrationSlopeCiLow" double precision,
    "calibrationSlopeCiHigh" double precision,
    "severityPassRate" double precision,
    evidence jsonb NOT NULL,
    "computedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: MethodVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."MethodVersion" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "methodName" text NOT NULL,
    "methodVersion" text NOT NULL,
    "contentHash" text NOT NULL,
    source text NOT NULL,
    rationale text NOT NULL,
    "failuresPublicYaml" text DEFAULT ''::text NOT NULL,
    "domainBoundJson" text DEFAULT ''::text NOT NULL,
    "capturedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: MethodologyProfile; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."MethodologyProfile" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "uploadId" text,
    "conclusionId" text,
    "sourceKind" text DEFAULT 'UPLOAD'::text NOT NULL,
    "patternType" text NOT NULL,
    title text NOT NULL,
    summary text NOT NULL,
    "reasoningMoves" jsonb NOT NULL,
    "transferTargets" jsonb NOT NULL,
    assumptions jsonb NOT NULL,
    "failureModes" jsonb NOT NULL,
    "evidenceAnchors" jsonb NOT NULL,
    confidence double precision DEFAULT 0.5 NOT NULL,
    "dedupeKey" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: MethodologyQualityScore; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."MethodologyQualityScore" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "conclusionId" text NOT NULL,
    progressivity double precision NOT NULL,
    severity double precision NOT NULL,
    "aimMethodFit" double precision NOT NULL,
    compressibility double precision NOT NULL,
    "domainSensitivity" double precision NOT NULL,
    composite double precision NOT NULL,
    evidence jsonb NOT NULL,
    "modelName" text DEFAULT 'stub'::text NOT NULL,
    "promptVersion" text DEFAULT 'mqs-prompt-v1.0'::text NOT NULL,
    "scoredAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: OpenQuestion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."OpenQuestion" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "noosphereId" text,
    summary text NOT NULL,
    "claimAId" text NOT NULL,
    "claimBId" text NOT NULL,
    "unresolvedReason" text DEFAULT ''::text NOT NULL,
    "layerDisagreementSummary" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "sourceUploadId" text
);


--
-- Name: OperatorState; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."OperatorState" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: OpinionCitation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."OpinionCitation" (
    id text NOT NULL,
    "opinionId" text NOT NULL,
    "sourceKind" text NOT NULL,
    "conclusionId" text,
    "claimId" text,
    "quotedSpan" text NOT NULL,
    "retrievalScore" double precision NOT NULL,
    "isRevoked" boolean DEFAULT false NOT NULL,
    "revokedReason" text,
    "revokedAt" timestamp(3) without time zone,
    "justificationMetadata" jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: Organization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Organization" (
    id text NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    "deletedAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Principle; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Principle" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    text text NOT NULL,
    "domainsJson" text DEFAULT '[]'::text NOT NULL,
    "clusterConclusionIds" text DEFAULT '[]'::text NOT NULL,
    "citedConclusionIds" text DEFAULT '[]'::text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    "triageReason" text DEFAULT ''::text NOT NULL,
    "mergedIntoId" text,
    "convictionScore" double precision DEFAULT 0.0 NOT NULL,
    "domainBreadth" integer DEFAULT 0 NOT NULL,
    "clusterCentroidSimilarity" double precision DEFAULT 0.0 NOT NULL,
    "publicVisible" boolean DEFAULT false NOT NULL,
    "driftReason" text,
    "reviewedByFounderId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "reviewedAt" timestamp(3) without time zone,
    "publishedAt" timestamp(3) without time zone
);


--
-- Name: PublicReply; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."PublicReply" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "publicResponseId" text NOT NULL,
    "founderId" text NOT NULL,
    visibility text DEFAULT 'private'::text NOT NULL,
    body text NOT NULL,
    "publishConfirmed" boolean DEFAULT false NOT NULL,
    "publishConfirmedAt" timestamp(3) without time zone,
    "promotedToReview" boolean DEFAULT false NOT NULL,
    "triggeredRevisionId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: PublicResponse; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."PublicResponse" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "publishedConclusionId" text NOT NULL,
    kind text NOT NULL,
    body text NOT NULL,
    "citationUrl" text DEFAULT ''::text NOT NULL,
    "submitterEmail" text DEFAULT ''::text NOT NULL,
    orcid text DEFAULT ''::text NOT NULL,
    pseudonymous boolean DEFAULT false NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "moderatorNote" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "seenAt" timestamp(3) without time zone,
    "publishConsent" boolean DEFAULT false NOT NULL
);


--
-- Name: PublicationReview; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."PublicationReview" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "conclusionId" text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    "checklistJson" text DEFAULT '{}'::text NOT NULL,
    "reviewerNotes" text DEFAULT ''::text NOT NULL,
    "declineReason" text DEFAULT ''::text NOT NULL,
    "revisionAsk" text DEFAULT ''::text NOT NULL,
    "reviewerFounderId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: PublicationSignature; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."PublicationSignature" (
    id text NOT NULL,
    "publishedConclusionId" text NOT NULL,
    slug text NOT NULL,
    version integer NOT NULL,
    "canonicalHash" text NOT NULL,
    "signatureHex" text NOT NULL,
    "keyFingerprint" text NOT NULL,
    "signedAt" text NOT NULL,
    "payloadJson" text DEFAULT '{}'::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: PublishedConclusion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."PublishedConclusion" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "sourceConclusionId" text NOT NULL,
    slug text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    "discountedConfidence" double precision NOT NULL,
    "statedConfidence" double precision DEFAULT 0 NOT NULL,
    "calibrationDiscountReason" text DEFAULT ''::text NOT NULL,
    "payloadJson" text DEFAULT '{}'::text NOT NULL,
    doi text DEFAULT ''::text NOT NULL,
    "zenodoRecordId" text DEFAULT ''::text NOT NULL,
    "publishedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    kind text DEFAULT 'CONCLUSION'::text NOT NULL
);


--
-- Name: RecalibrationOverride; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."RecalibrationOverride" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "conclusionId" text NOT NULL,
    "founderId" text NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ResearchSuggestion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ResearchSuggestion" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "noosphereId" text,
    title text NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    rationale text DEFAULT ''::text NOT NULL,
    "readingUris" text DEFAULT '[]'::text NOT NULL,
    "sessionLabel" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "suggestedForFounderId" text,
    "sourceUploadId" text
);


--
-- Name: ResolutionMismatch; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ResolutionMismatch" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    venue text NOT NULL,
    "venueOutcome" text NOT NULL,
    "venueResolvedAt" timestamp(3) without time zone,
    "venueSourceUrl" text,
    "rawVenuePayload" jsonb,
    reason text NOT NULL,
    kind text NOT NULL,
    "reviewedAt" timestamp(3) without time zone,
    "reviewedBy" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ResolutionOverride; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ResolutionOverride" (
    id text NOT NULL,
    "predictionId" text NOT NULL,
    outcome public."ForecastOutcome" NOT NULL,
    "resolvedAt" timestamp(3) without time zone NOT NULL,
    reason text NOT NULL,
    "citationUrl" text NOT NULL,
    "founderId" text NOT NULL,
    "rawSettlement" jsonb,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ResolutionRevision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ResolutionRevision" (
    id text NOT NULL,
    "resolutionId" text NOT NULL,
    "newOutcome" public."ForecastOutcome" NOT NULL,
    "newResolvedAt" timestamp(3) without time zone NOT NULL,
    reason text NOT NULL,
    "rawSettlement" jsonb,
    source text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ResponseTriage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ResponseTriage" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "publicResponseId" text NOT NULL,
    label text NOT NULL,
    "manualLabel" text DEFAULT ''::text NOT NULL,
    "spamReason" text DEFAULT ''::text NOT NULL,
    "manualReason" text DEFAULT ''::text NOT NULL,
    confidence double precision NOT NULL,
    "impliedObjection" text DEFAULT ''::text NOT NULL,
    rationale text DEFAULT ''::text NOT NULL,
    "usedLlm" boolean DEFAULT false NOT NULL,
    "senderHash" text DEFAULT ''::text NOT NULL,
    "elevatedSenderFlag" boolean DEFAULT false NOT NULL,
    "severityInputsJson" text DEFAULT '{}'::text NOT NULL,
    "severityValue" double precision DEFAULT 0 NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "archivedAt" timestamp(3) without time zone,
    "archiveNote" text DEFAULT ''::text NOT NULL
);


--
-- Name: ReviewItem; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ReviewItem" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "noosphereId" text,
    "claimAId" text NOT NULL,
    "claimBId" text NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    "layerVerdictsJson" text DEFAULT '{}'::text NOT NULL,
    severity double precision DEFAULT 0 NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    "aggregatorVerdict" text,
    "priorScoresJson" text,
    "humanVerdict" text,
    "humanOverrule" boolean DEFAULT false NOT NULL,
    "resolutionNote" text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "resolvedAt" timestamp(3) without time zone,
    "resolvedByFounderId" text
);


--
-- Name: RevisionEvent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."RevisionEvent" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "planId" text NOT NULL,
    "founderId" text NOT NULL,
    "inputsJson" text NOT NULL,
    "planJson" text NOT NULL,
    "preConfidenceSnapshot" text NOT NULL,
    "affectedConclusionIds" text DEFAULT '[]'::text NOT NULL,
    "typedConfirmation" boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "revertedAt" timestamp(3) without time zone
);


--
-- Name: Session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Session" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "founderId" text NOT NULL,
    token text NOT NULL,
    "expiresAt" timestamp(3) without time zone NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: SocialPost; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."SocialPost" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    source text NOT NULL,
    "sourceId" text,
    platform text NOT NULL,
    body text NOT NULL,
    media jsonb,
    status text NOT NULL,
    "approvedBy" text,
    "approvedAt" timestamp(3) without time zone,
    "postedAt" timestamp(3) without time zone,
    "externalId" text,
    "failureReason" text,
    "markdownBody" text,
    subject text,
    "bundleId" uuid
);


--
-- Name: SourceCredibilityUpdate; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."SourceCredibilityUpdate" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "sourceId" text NOT NULL,
    "sourceType" text NOT NULL,
    "conclusionId" text NOT NULL,
    outcome public."CredibilityOutcome" NOT NULL,
    kind public."CredibilityEventKind" NOT NULL,
    weight double precision NOT NULL,
    "posteriorAlpha" double precision NOT NULL,
    "posteriorBeta" double precision NOT NULL,
    "nUpdates" integer NOT NULL,
    "nConfirmations" integer NOT NULL,
    "nFailures" integer NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    "rawPayload" jsonb,
    "observedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: SourceStanding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."SourceStanding" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "sourceId" text NOT NULL,
    status public."SourceStandingStatus" NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    poller text NOT NULL,
    "noticeSourceId" text,
    "rawPayload" jsonb,
    "observedAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: SourceTriageItem; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."SourceTriageItem" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    trigger text DEFAULT 'standing'::text NOT NULL,
    "standingId" text DEFAULT ''::text NOT NULL,
    "verdictId" text DEFAULT ''::text NOT NULL,
    "sourceId" text NOT NULL,
    "conclusionId" text NOT NULL,
    status public."SourceStandingStatus" DEFAULT 'ACTIVE'::public."SourceStandingStatus" NOT NULL,
    decision text DEFAULT 'pending'::text NOT NULL,
    "decisionNote" text,
    "decidedById" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "decidedAt" timestamp(3) without time zone
);


--
-- Name: Span; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Span" (
    id text NOT NULL,
    "traceId" text NOT NULL,
    "parentSpanId" text,
    name text NOT NULL,
    status text DEFAULT 'ok'::text NOT NULL,
    "startedAt" timestamp(3) without time zone NOT NULL,
    "endedAt" timestamp(3) without time zone,
    "durationMs" double precision,
    "errorKind" text,
    "errorMessage" text,
    attrs jsonb DEFAULT '{}'::jsonb NOT NULL,
    "costUsd" double precision DEFAULT 0.0 NOT NULL,
    "organizationId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: Subscriber; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Subscriber" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    email text NOT NULL,
    scope text NOT NULL,
    "scopeKey" text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    cadence text DEFAULT 'weekly'::text NOT NULL,
    "confirmToken" text DEFAULT ''::text NOT NULL,
    "unsubscribeToken" text NOT NULL,
    "confirmedAt" timestamp(3) without time zone,
    "unsubscribedAt" timestamp(3) without time zone,
    "unsubscribeReason" text DEFAULT ''::text NOT NULL,
    "lastSentAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Upload; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Upload" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    "founderId" text NOT NULL,
    title text NOT NULL,
    description text,
    "sourceType" text DEFAULT 'written'::text NOT NULL,
    "originalName" text NOT NULL,
    "mimeType" text NOT NULL,
    "filePath" text NOT NULL,
    "fileSize" integer NOT NULL,
    "textContent" text,
    status text DEFAULT 'pending'::text NOT NULL,
    "processLog" text DEFAULT ''::text NOT NULL,
    "claimsCount" integer,
    "methodCount" integer,
    "substCount" integer,
    "principleCount" integer,
    "errorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "publishedAt" timestamp(3) without time zone,
    slug text,
    "blogExcerpt" text,
    "authorBio" text,
    "deletedAt" timestamp(3) without time zone,
    visibility text DEFAULT 'org'::text NOT NULL,
    "audioUrl" text,
    "audioDurationSec" integer,
    "extractionMethod" text,
    blurb text
);


--
-- Name: UploadChunk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."UploadChunk" (
    id text NOT NULL,
    "uploadId" text NOT NULL,
    index integer NOT NULL,
    text text NOT NULL,
    "startMs" integer,
    "endMs" integer,
    "speakerLabel" text,
    "headingHint" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: WatchedMarket; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WatchedMarket" (
    id text NOT NULL,
    "organizationId" text NOT NULL,
    source public."ForecastSource" NOT NULL,
    url text NOT NULL,
    "externalId" text,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    notes text,
    "lastConsideredAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: _prisma_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public._prisma_migrations (
    id character varying(36) NOT NULL,
    checksum character varying(64) NOT NULL,
    finished_at timestamp with time zone,
    migration_name character varying(255) NOT NULL,
    logs text,
    rolled_back_at timestamp with time zone,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_steps_count integer DEFAULT 0 NOT NULL
);


--
-- Name: adversarial_challenge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.adversarial_challenge (
    id character varying NOT NULL,
    conclusion_id character varying NOT NULL,
    cluster_fingerprint character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: algorithm_calibration_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.algorithm_calibration_snapshot (
    id character varying NOT NULL,
    algorithm_id character varying NOT NULL,
    organization_id character varying NOT NULL,
    snapshot_at timestamp without time zone NOT NULL,
    total_invocations integer NOT NULL,
    resolved_invocations integer NOT NULL,
    accuracy double precision,
    mean_brier double precision,
    mean_horizon_error double precision,
    directional_accuracy double precision,
    confidence_calibration_drift double precision,
    last_30d_accuracy double precision,
    last_30d_resolved integer NOT NULL,
    probabilistic_resolved integer NOT NULL,
    directional_resolved integer NOT NULL,
    confidence_band_resolved integer NOT NULL
);


--
-- Name: algorithm_input_observation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.algorithm_input_observation (
    id character varying NOT NULL,
    invocation_id character varying NOT NULL,
    input_name character varying NOT NULL,
    value_json character varying NOT NULL,
    observed_at timestamp without time zone NOT NULL,
    source_artifact_id character varying,
    source_url character varying
);


--
-- Name: algorithm_invocation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.algorithm_invocation (
    id character varying NOT NULL,
    algorithm_id character varying NOT NULL,
    organization_id character varying NOT NULL,
    invoked_at timestamp without time zone NOT NULL,
    resolved_at timestamp without time zone,
    correctness character varying,
    payload_json character varying NOT NULL
);


--
-- Name: algorithm_triage_recommendation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.algorithm_triage_recommendation (
    id character varying NOT NULL,
    algorithm_id character varying NOT NULL,
    organization_id character varying NOT NULL,
    recommended_at timestamp without time zone NOT NULL,
    recommended_action character varying NOT NULL,
    trigger_reasons_json character varying NOT NULL,
    recommended_multiplier double precision NOT NULL,
    narrative character varying NOT NULL,
    status character varying NOT NULL,
    resolved_by character varying,
    resolved_at timestamp without time zone,
    resolution_note character varying
);


--
-- Name: artifact; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artifact (
    id character varying NOT NULL,
    uri character varying NOT NULL,
    mime_type character varying NOT NULL,
    byte_length integer NOT NULL,
    content_sha256 character varying NOT NULL,
    title character varying NOT NULL,
    author character varying NOT NULL,
    source_date_iso character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    effective_at timestamp without time zone,
    superseded_at timestamp without time zone,
    effective_at_inferred boolean NOT NULL,
    license_status character varying NOT NULL,
    literature_connector character varying NOT NULL
);


--
-- Name: battery_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battery_run (
    run_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: bet_resolution; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bet_resolution (
    id character varying NOT NULL,
    bet_spec_id character varying NOT NULL,
    resolved_at timestamp without time zone NOT NULL,
    outcome character varying NOT NULL,
    evidence_note character varying NOT NULL,
    resolved_by character varying NOT NULL,
    pnl_usd double precision,
    cost_realized double precision,
    accuracy_score double precision,
    audience_response character varying,
    payload_json character varying NOT NULL
);


--
-- Name: bet_spec; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bet_spec (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    kind character varying NOT NULL,
    status character varying NOT NULL,
    proposition character varying NOT NULL,
    resolution_criterion character varying NOT NULL,
    horizon_at timestamp without time zone NOT NULL,
    created_by_memo_id character varying,
    originating_algorithm_id character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    resolved_at timestamp without time zone,
    outcome character varying,
    outcome_note character varying,
    payload_json character varying NOT NULL
);


--
-- Name: cascade_edge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cascade_edge (
    edge_id character varying NOT NULL,
    src character varying NOT NULL,
    dst character varying NOT NULL,
    relation character varying NOT NULL,
    method_invocation_id character varying NOT NULL,
    retracted_at timestamp without time zone,
    payload_json character varying NOT NULL
);


--
-- Name: cascade_node; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cascade_node (
    node_id character varying NOT NULL,
    kind character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: chunk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunk (
    id character varying NOT NULL,
    artifact_id character varying NOT NULL,
    start_offset integer NOT NULL,
    end_offset integer NOT NULL,
    text character varying NOT NULL,
    metadata_json character varying NOT NULL
);


--
-- Name: citation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citation (
    id character varying NOT NULL,
    firm_claim_id character varying NOT NULL,
    voice_id character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: claim; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claim (
    id character varying NOT NULL,
    payload_json character varying NOT NULL,
    freshness character varying NOT NULL,
    last_validated_at timestamp without time zone
);


--
-- Name: claim_extraction_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claim_extraction_cache (
    chunk_id character varying NOT NULL,
    payload_json character varying NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: cluster_reindex_proposal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cluster_reindex_proposal (
    id character varying NOT NULL,
    proposed_at timestamp without time zone NOT NULL,
    drift double precision NOT NULL,
    cluster_count_before integer NOT NULL,
    cluster_count_after integer NOT NULL,
    summary_json character varying NOT NULL,
    status character varying NOT NULL,
    resolved_by character varying,
    resolved_at timestamp without time zone
);


--
-- Name: coherence_pair; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coherence_pair (
    id character varying NOT NULL,
    claim_a_id character varying NOT NULL,
    claim_b_id character varying NOT NULL,
    verdict character varying NOT NULL,
    scores_json character varying NOT NULL,
    confidence double precision NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: coherence_result_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coherence_result_cache (
    evaluation_key character varying NOT NULL,
    claim_a_id character varying NOT NULL,
    claim_b_id character varying NOT NULL,
    content_hash character varying NOT NULL,
    versions_json character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: conclusion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conclusion (
    id character varying NOT NULL,
    payload_json character varying NOT NULL,
    freshness character varying NOT NULL,
    last_validated_at timestamp without time zone
);


--
-- Name: contradiction_dispute; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contradiction_dispute (
    id character varying NOT NULL,
    contradiction_result_id character varying NOT NULL,
    detection_method character varying NOT NULL,
    disputed_by character varying NOT NULL,
    reason character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: contradiction_lifecycle; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contradiction_lifecycle (
    id character varying NOT NULL,
    contradiction_id character varying NOT NULL,
    current_status character varying NOT NULL,
    last_transition_at timestamp without time zone NOT NULL,
    events_json character varying NOT NULL,
    supported_principle_id character varying,
    subsuming_principle_id character varying,
    pending_subsumption_principle_id character varying
);


--
-- Name: contradiction_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contradiction_result (
    id character varying NOT NULL,
    principle_a_id character varying NOT NULL,
    principle_b_id character varying NOT NULL,
    score double precision NOT NULL,
    confidence_low double precision NOT NULL,
    confidence_high double precision NOT NULL,
    verdict character varying NOT NULL,
    axis character varying,
    human_explanation character varying,
    detection_method character varying NOT NULL,
    detected_at timestamp without time zone NOT NULL,
    raw_sparsity double precision NOT NULL,
    direction_method character varying NOT NULL,
    extras_json character varying NOT NULL,
    status character varying NOT NULL,
    dispute_count integer NOT NULL,
    last_dispute_at timestamp without time zone
);


--
-- Name: contradiction_test_task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contradiction_test_task (
    id character varying NOT NULL,
    principle_a_id character varying NOT NULL,
    principle_b_id character varying NOT NULL,
    pair_key character varying NOT NULL,
    priority character varying NOT NULL,
    status character varying NOT NULL,
    enqueued_at timestamp without time zone NOT NULL,
    started_at timestamp without time zone,
    finished_at timestamp without time zone,
    result_id character varying,
    last_error character varying
);


--
-- Name: counterfactual_eval_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.counterfactual_eval_run (
    run_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: cut_outcome; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cut_outcome (
    id character varying NOT NULL,
    cut_id character varying NOT NULL,
    outcome_id character varying NOT NULL
);


--
-- Name: decay_policy; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.decay_policy (
    id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: dialectic_contradiction_flag; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dialectic_contradiction_flag (
    id character varying NOT NULL,
    utterance_id character varying NOT NULL,
    flag_kind character varying NOT NULL,
    prior_utterance_id character varying,
    prior_principle_id character varying,
    prior_speaker_id character varying,
    contradiction_score double precision NOT NULL,
    axis character varying,
    human_explanation character varying,
    detection_method character varying NOT NULL,
    acknowledged_at timestamp without time zone,
    acknowledged_by character varying,
    acknowledgment_note character varying,
    detected_at timestamp without time zone NOT NULL
);


--
-- Name: dialectic_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dialectic_session (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    title character varying NOT NULL,
    started_at timestamp without time zone NOT NULL,
    ended_at timestamp without time zone,
    participants_json character varying NOT NULL,
    audio_path character varying NOT NULL,
    transcript_path character varying NOT NULL,
    status character varying NOT NULL,
    visibility character varying NOT NULL,
    live_contradictions_detected integer NOT NULL,
    principles_extracted integer NOT NULL,
    summary_memo_id character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: dialectic_utterance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dialectic_utterance (
    id character varying NOT NULL,
    session_id character varying NOT NULL,
    speaker_id character varying NOT NULL,
    start_time double precision NOT NULL,
    end_time double precision NOT NULL,
    text character varying NOT NULL,
    extracted_claim_ids_json character varying NOT NULL,
    derived_principle_ids_json character varying NOT NULL,
    live_contradiction_flags_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: drift_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.drift_event (
    id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: embedding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding (
    id character varying NOT NULL,
    model_name character varying NOT NULL,
    text_sha256 character varying NOT NULL,
    dimension integer NOT NULL,
    vector bytea,
    ref_claim_id character varying NOT NULL
);


--
-- Name: embedding_model_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_model_version (
    id character varying NOT NULL,
    effective_from timestamp without time zone NOT NULL,
    model_name character varying NOT NULL,
    notes character varying NOT NULL
);


--
-- Name: embedding_retry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_retry (
    id character varying NOT NULL,
    source_kind character varying NOT NULL,
    source_id character varying NOT NULL,
    model_name character varying NOT NULL,
    text_sha256 character varying NOT NULL,
    attempts integer NOT NULL,
    last_error character varying NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: entity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity (
    id character varying NOT NULL,
    canonical_key character varying NOT NULL,
    label character varying NOT NULL,
    entity_type character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: external_bundle; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_bundle (
    content_hash character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: founder_override; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.founder_override (
    override_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: graph_edge_reasoning; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.graph_edge_reasoning (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    src character varying NOT NULL,
    dst character varying NOT NULL,
    kind character varying NOT NULL,
    payload_json character varying NOT NULL,
    generated_at timestamp without time zone NOT NULL
);


--
-- Name: graph_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.graph_snapshot (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    snapshot_at timestamp without time zone NOT NULL,
    version character varying NOT NULL,
    nodes_json character varying NOT NULL,
    edges_json character varying NOT NULL,
    node_count integer NOT NULL,
    edge_count integer NOT NULL,
    notes character varying NOT NULL
);


--
-- Name: investment_memo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.investment_memo (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    synthesizer_result_id character varying,
    title character varying NOT NULL,
    slug character varying NOT NULL,
    status character varying NOT NULL,
    addressee character varying NOT NULL,
    question_type character varying NOT NULL,
    md_path character varying,
    pdf_path character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    sent_at timestamp without time zone,
    acknowledged_at timestamp without time zone,
    published_at timestamp without time zone,
    archived_at timestamp without time zone,
    synthesizer_version character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: ledger_entry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ledger_entry (
    entry_id character varying NOT NULL,
    prev_hash character varying NOT NULL,
    method_id character varying,
    "timestamp" timestamp without time zone NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: logical_algorithm; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logical_algorithm (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    name character varying NOT NULL,
    status character varying NOT NULL,
    payload_json character varying NOT NULL,
    weighting_multiplier double precision NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    last_invoked_at timestamp without time zone,
    provenance character varying NOT NULL
);


--
-- Name: memo_dispatch; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memo_dispatch (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    memo_id character varying NOT NULL,
    agent_id character varying NOT NULL,
    dispatched_at timestamp without time zone NOT NULL,
    outcome_action character varying NOT NULL,
    bet_link character varying,
    bet_link_kind character varying,
    acknowledged_by character varying NOT NULL,
    acknowledged_at timestamp without time zone,
    rationale character varying NOT NULL,
    deferred_until timestamp without time zone,
    failure_reason character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: method; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.method (
    method_id character varying NOT NULL,
    status character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: method_invocation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.method_invocation (
    id character varying NOT NULL,
    method_id character varying NOT NULL,
    correlation_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: mip_manifest; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mip_manifest (
    content_hash character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: object_policy_binding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.object_policy_binding (
    id character varying NOT NULL,
    object_id character varying NOT NULL,
    policy_id character varying NOT NULL
);


--
-- Name: outcome; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.outcome (
    outcome_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: portfolio_agent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portfolio_agent (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    name character varying NOT NULL,
    kind character varying NOT NULL,
    status character varying NOT NULL,
    default_bet_ceiling_usd double precision NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: prediction_resolution; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prediction_resolution (
    id character varying NOT NULL,
    predictive_claim_id character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: predictive_claim; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.predictive_claim (
    id character varying NOT NULL,
    author_key character varying NOT NULL,
    artifact_id character varying NOT NULL,
    status character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: principle_cluster; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.principle_cluster (
    principle_id character varying NOT NULL,
    cluster_id character varying NOT NULL,
    assigned_at timestamp without time zone NOT NULL,
    assignment_method character varying NOT NULL
);


--
-- Name: principle_cluster_centroid; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.principle_cluster_centroid (
    cluster_id character varying NOT NULL,
    centroid_vec bytea NOT NULL,
    dim integer NOT NULL,
    member_count integer NOT NULL,
    assignment_method character varying NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: quantitative_formalisation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quantitative_formalisation (
    id character varying NOT NULL,
    principle_id character varying NOT NULL,
    status character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: quantitative_test_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quantitative_test_result (
    id character varying NOT NULL,
    formalisation_id character varying NOT NULL,
    principle_id character varying NOT NULL,
    run_stamp character varying NOT NULL,
    status character varying NOT NULL,
    artifacts_path character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: reading_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reading_queue (
    id character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: rebuttal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rebuttal (
    id character varying NOT NULL,
    report_id character varying NOT NULL,
    finding_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: relative_position_map; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.relative_position_map (
    conclusion_id character varying NOT NULL,
    payload_json character varying NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: research_suggestion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_suggestion (
    id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: revalidation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revalidation (
    id character varying NOT NULL,
    object_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: review_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_item (
    id character varying NOT NULL,
    claim_a_id character varying NOT NULL,
    claim_b_id character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: review_report; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_report (
    report_id character varying NOT NULL,
    conclusion_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: rigor_submission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rigor_submission (
    submission_id character varying NOT NULL,
    author_id character varying NOT NULL,
    intended_venue character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: rigor_verdict; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rigor_verdict (
    ledger_entry_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: synthesizer_memo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.synthesizer_memo (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    synthesizer_version character varying NOT NULL,
    question character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: synthesizer_task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.synthesizer_task (
    id character varying NOT NULL,
    organization_id character varying NOT NULL,
    trigger character varying NOT NULL,
    status character varying NOT NULL,
    enqueued_at timestamp without time zone NOT NULL,
    started_at timestamp without time zone,
    finished_at timestamp without time zone,
    invocation_id character varying,
    current_event_id character varying,
    memo_id character varying,
    outcome character varying,
    payload_json character varying NOT NULL
);


--
-- Name: temporal_cut; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.temporal_cut (
    cut_id character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: topic_cluster; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.topic_cluster (
    cluster_id character varying NOT NULL,
    label character varying NOT NULL,
    description character varying NOT NULL,
    centroid_json character varying NOT NULL,
    model_version character varying NOT NULL,
    params_hash character varying NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    freshness character varying NOT NULL,
    last_validated_at timestamp without time zone
);


--
-- Name: topic_membership; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.topic_membership (
    claim_id character varying NOT NULL,
    cluster_id character varying NOT NULL
);


--
-- Name: transfer_study; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.transfer_study (
    study_id character varying NOT NULL,
    method_ref_name character varying NOT NULL,
    method_ref_version character varying NOT NULL,
    payload_json character varying NOT NULL
);


--
-- Name: voice; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.voice (
    id character varying NOT NULL,
    canonical_key character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: voice_phase; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.voice_phase (
    id character varying NOT NULL,
    voice_id character varying NOT NULL,
    payload_json character varying NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: messages; Type: TABLE; Schema: realtime; Owner: -
--

CREATE TABLE realtime.messages (
    topic text NOT NULL,
    extension text NOT NULL,
    payload jsonb,
    event text,
    private boolean DEFAULT false,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    inserted_at timestamp without time zone DEFAULT now() NOT NULL,
    id uuid DEFAULT gen_random_uuid() NOT NULL
)
PARTITION BY RANGE (inserted_at);


--
-- Name: schema_migrations; Type: TABLE; Schema: realtime; Owner: -
--

CREATE TABLE realtime.schema_migrations (
    version bigint NOT NULL,
    inserted_at timestamp(0) without time zone
);


--
-- Name: subscription; Type: TABLE; Schema: realtime; Owner: -
--

CREATE TABLE realtime.subscription (
    id bigint NOT NULL,
    subscription_id uuid NOT NULL,
    entity regclass NOT NULL,
    filters realtime.user_defined_filter[] DEFAULT '{}'::realtime.user_defined_filter[] NOT NULL,
    claims jsonb NOT NULL,
    claims_role regrole GENERATED ALWAYS AS (realtime.to_regrole((claims ->> 'role'::text))) STORED NOT NULL,
    created_at timestamp without time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    action_filter text DEFAULT '*'::text,
    CONSTRAINT subscription_action_filter_check CHECK ((action_filter = ANY (ARRAY['*'::text, 'INSERT'::text, 'UPDATE'::text, 'DELETE'::text])))
);


--
-- Name: subscription_id_seq; Type: SEQUENCE; Schema: realtime; Owner: -
--

ALTER TABLE realtime.subscription ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME realtime.subscription_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: buckets; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.buckets (
    id text NOT NULL,
    name text NOT NULL,
    owner uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    public boolean DEFAULT false,
    avif_autodetection boolean DEFAULT false,
    file_size_limit bigint,
    allowed_mime_types text[],
    owner_id text,
    type storage.buckettype DEFAULT 'STANDARD'::storage.buckettype NOT NULL
);


--
-- Name: buckets_analytics; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.buckets_analytics (
    name text NOT NULL,
    type storage.buckettype DEFAULT 'ANALYTICS'::storage.buckettype NOT NULL,
    format text DEFAULT 'ICEBERG'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: buckets_vectors; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.buckets_vectors (
    id text NOT NULL,
    type storage.buckettype DEFAULT 'VECTOR'::storage.buckettype NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: migrations; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.migrations (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    hash character varying(40) NOT NULL,
    executed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: objects; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.objects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    bucket_id text,
    name text,
    owner uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    last_accessed_at timestamp with time zone DEFAULT now(),
    metadata jsonb,
    path_tokens text[] GENERATED ALWAYS AS (string_to_array(name, '/'::text)) STORED,
    version text,
    owner_id text,
    user_metadata jsonb
);


--
-- Name: s3_multipart_uploads; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.s3_multipart_uploads (
    id text NOT NULL,
    in_progress_size bigint DEFAULT 0 NOT NULL,
    upload_signature text NOT NULL,
    bucket_id text NOT NULL,
    key text NOT NULL COLLATE pg_catalog."C",
    version text NOT NULL,
    owner_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    user_metadata jsonb,
    metadata jsonb
);


--
-- Name: s3_multipart_uploads_parts; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.s3_multipart_uploads_parts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    upload_id text NOT NULL,
    size bigint DEFAULT 0 NOT NULL,
    part_number integer NOT NULL,
    bucket_id text NOT NULL,
    key text NOT NULL COLLATE pg_catalog."C",
    etag text NOT NULL,
    owner_id text,
    version text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vector_indexes; Type: TABLE; Schema: storage; Owner: -
--

CREATE TABLE storage.vector_indexes (
    id text DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL COLLATE pg_catalog."C",
    bucket_id text NOT NULL,
    data_type text NOT NULL,
    dimension integer NOT NULL,
    distance_metric text NOT NULL,
    metadata_configuration jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: refresh_tokens id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens ALTER COLUMN id SET DEFAULT nextval('auth.refresh_tokens_id_seq'::regclass);


--
-- Name: mfa_amr_claims amr_id_pk; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_amr_claims
    ADD CONSTRAINT amr_id_pk PRIMARY KEY (id);


--
-- Name: audit_log_entries audit_log_entries_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.audit_log_entries
    ADD CONSTRAINT audit_log_entries_pkey PRIMARY KEY (id);


--
-- Name: custom_oauth_providers custom_oauth_providers_identifier_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.custom_oauth_providers
    ADD CONSTRAINT custom_oauth_providers_identifier_key UNIQUE (identifier);


--
-- Name: custom_oauth_providers custom_oauth_providers_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.custom_oauth_providers
    ADD CONSTRAINT custom_oauth_providers_pkey PRIMARY KEY (id);


--
-- Name: flow_state flow_state_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.flow_state
    ADD CONSTRAINT flow_state_pkey PRIMARY KEY (id);


--
-- Name: identities identities_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.identities
    ADD CONSTRAINT identities_pkey PRIMARY KEY (id);


--
-- Name: identities identities_provider_id_provider_unique; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.identities
    ADD CONSTRAINT identities_provider_id_provider_unique UNIQUE (provider_id, provider);


--
-- Name: instances instances_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.instances
    ADD CONSTRAINT instances_pkey PRIMARY KEY (id);


--
-- Name: mfa_amr_claims mfa_amr_claims_session_id_authentication_method_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_amr_claims
    ADD CONSTRAINT mfa_amr_claims_session_id_authentication_method_pkey UNIQUE (session_id, authentication_method);


--
-- Name: mfa_challenges mfa_challenges_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_challenges
    ADD CONSTRAINT mfa_challenges_pkey PRIMARY KEY (id);


--
-- Name: mfa_factors mfa_factors_last_challenged_at_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_factors
    ADD CONSTRAINT mfa_factors_last_challenged_at_key UNIQUE (last_challenged_at);


--
-- Name: mfa_factors mfa_factors_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_factors
    ADD CONSTRAINT mfa_factors_pkey PRIMARY KEY (id);


--
-- Name: oauth_authorizations oauth_authorizations_authorization_code_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_authorizations
    ADD CONSTRAINT oauth_authorizations_authorization_code_key UNIQUE (authorization_code);


--
-- Name: oauth_authorizations oauth_authorizations_authorization_id_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_authorizations
    ADD CONSTRAINT oauth_authorizations_authorization_id_key UNIQUE (authorization_id);


--
-- Name: oauth_authorizations oauth_authorizations_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_authorizations
    ADD CONSTRAINT oauth_authorizations_pkey PRIMARY KEY (id);


--
-- Name: oauth_client_states oauth_client_states_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_client_states
    ADD CONSTRAINT oauth_client_states_pkey PRIMARY KEY (id);


--
-- Name: oauth_clients oauth_clients_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_clients
    ADD CONSTRAINT oauth_clients_pkey PRIMARY KEY (id);


--
-- Name: oauth_consents oauth_consents_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_consents
    ADD CONSTRAINT oauth_consents_pkey PRIMARY KEY (id);


--
-- Name: oauth_consents oauth_consents_user_client_unique; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_consents
    ADD CONSTRAINT oauth_consents_user_client_unique UNIQUE (user_id, client_id);


--
-- Name: one_time_tokens one_time_tokens_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.one_time_tokens
    ADD CONSTRAINT one_time_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_unique; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_unique UNIQUE (token);


--
-- Name: saml_providers saml_providers_entity_id_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.saml_providers
    ADD CONSTRAINT saml_providers_entity_id_key UNIQUE (entity_id);


--
-- Name: saml_providers saml_providers_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.saml_providers
    ADD CONSTRAINT saml_providers_pkey PRIMARY KEY (id);


--
-- Name: saml_relay_states saml_relay_states_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.saml_relay_states
    ADD CONSTRAINT saml_relay_states_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: sso_domains sso_domains_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.sso_domains
    ADD CONSTRAINT sso_domains_pkey PRIMARY KEY (id);


--
-- Name: sso_providers sso_providers_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.sso_providers
    ADD CONSTRAINT sso_providers_pkey PRIMARY KEY (id);


--
-- Name: users users_phone_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_phone_key UNIQUE (phone);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: webauthn_challenges webauthn_challenges_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.webauthn_challenges
    ADD CONSTRAINT webauthn_challenges_pkey PRIMARY KEY (id);


--
-- Name: webauthn_credentials webauthn_credentials_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.webauthn_credentials
    ADD CONSTRAINT webauthn_credentials_pkey PRIMARY KEY (id);


--
-- Name: Addendum Addendum_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Addendum"
    ADD CONSTRAINT "Addendum_pkey" PRIMARY KEY (id);


--
-- Name: AlertEvent AlertEvent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AlertEvent"
    ADD CONSTRAINT "AlertEvent_pkey" PRIMARY KEY (id);


--
-- Name: AlertRule AlertRule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AlertRule"
    ADD CONSTRAINT "AlertRule_pkey" PRIMARY KEY (id);


--
-- Name: AnchorRevision AnchorRevision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AnchorRevision"
    ADD CONSTRAINT "AnchorRevision_pkey" PRIMARY KEY (id);


--
-- Name: ApiKey ApiKey_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ApiKey"
    ADD CONSTRAINT "ApiKey_pkey" PRIMARY KEY (id);


--
-- Name: AttentionAction AttentionAction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AttentionAction"
    ADD CONSTRAINT "AttentionAction_pkey" PRIMARY KEY (id);


--
-- Name: AuditEvent AuditEvent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AuditEvent"
    ADD CONSTRAINT "AuditEvent_pkey" PRIMARY KEY (id);


--
-- Name: CalibrationModel CalibrationModel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CalibrationModel"
    ADD CONSTRAINT "CalibrationModel_pkey" PRIMARY KEY (id);


--
-- Name: CitationVerdict CitationVerdict_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CitationVerdict"
    ADD CONSTRAINT "CitationVerdict_pkey" PRIMARY KEY (id);


--
-- Name: ConclusionDeletionRequest ConclusionDeletionRequest_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionDeletionRequest"
    ADD CONSTRAINT "ConclusionDeletionRequest_pkey" PRIMARY KEY (id);


--
-- Name: ConclusionMethod ConclusionMethod_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionMethod"
    ADD CONSTRAINT "ConclusionMethod_pkey" PRIMARY KEY (id);


--
-- Name: ConclusionSource ConclusionSource_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionSource"
    ADD CONSTRAINT "ConclusionSource_pkey" PRIMARY KEY ("conclusionId", "uploadId");


--
-- Name: Conclusion Conclusion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Conclusion"
    ADD CONSTRAINT "Conclusion_pkey" PRIMARY KEY (id);


--
-- Name: ContactSubmission ContactSubmission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ContactSubmission"
    ADD CONSTRAINT "ContactSubmission_pkey" PRIMARY KEY (id);


--
-- Name: Contradiction Contradiction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Contradiction"
    ADD CONSTRAINT "Contradiction_pkey" PRIMARY KEY (id);


--
-- Name: CritiqueBountyPayout CritiqueBountyPayout_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueBountyPayout"
    ADD CONSTRAINT "CritiqueBountyPayout_pkey" PRIMARY KEY (id);


--
-- Name: CritiqueSubmission CritiqueSubmission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueSubmission"
    ADD CONSTRAINT "CritiqueSubmission_pkey" PRIMARY KEY (id);


--
-- Name: CurrentEvent CurrentEvent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CurrentEvent"
    ADD CONSTRAINT "CurrentEvent_pkey" PRIMARY KEY (id);


--
-- Name: DashboardDismissal DashboardDismissal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DashboardDismissal"
    ADD CONSTRAINT "DashboardDismissal_pkey" PRIMARY KEY (id);


--
-- Name: DeletionRequest DeletionRequest_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DeletionRequest"
    ADD CONSTRAINT "DeletionRequest_pkey" PRIMARY KEY (id);


--
-- Name: DomainBoundVerdict DomainBoundVerdict_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DomainBoundVerdict"
    ADD CONSTRAINT "DomainBoundVerdict_pkey" PRIMARY KEY (id);


--
-- Name: DriftEvent DriftEvent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DriftEvent"
    ADD CONSTRAINT "DriftEvent_pkey" PRIMARY KEY (id);


--
-- Name: EquityInstrument EquityInstrument_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquityInstrument"
    ADD CONSTRAINT "EquityInstrument_pkey" PRIMARY KEY (id);


--
-- Name: EquityInstrument EquityInstrument_symbol_exchange_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquityInstrument"
    ADD CONSTRAINT "EquityInstrument_symbol_exchange_key" UNIQUE (symbol, exchange);


--
-- Name: EquityPortfolioState EquityPortfolioState_organizationId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquityPortfolioState"
    ADD CONSTRAINT "EquityPortfolioState_organizationId_key" UNIQUE ("organizationId");


--
-- Name: EquityPortfolioState EquityPortfolioState_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquityPortfolioState"
    ADD CONSTRAINT "EquityPortfolioState_pkey" PRIMARY KEY (id);


--
-- Name: EquityPosition EquityPosition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquityPosition"
    ADD CONSTRAINT "EquityPosition_pkey" PRIMARY KEY (id);


--
-- Name: EquityPriceTick EquityPriceTick_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquityPriceTick"
    ADD CONSTRAINT "EquityPriceTick_pkey" PRIMARY KEY (id);


--
-- Name: EquitySignalCitation EquitySignalCitation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquitySignalCitation"
    ADD CONSTRAINT "EquitySignalCitation_pkey" PRIMARY KEY (id);


--
-- Name: EquitySignal EquitySignal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EquitySignal"
    ADD CONSTRAINT "EquitySignal_pkey" PRIMARY KEY (id);


--
-- Name: EventOpinion EventOpinion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EventOpinion"
    ADD CONSTRAINT "EventOpinion_pkey" PRIMARY KEY (id);


--
-- Name: FollowUpMessage FollowUpMessage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."FollowUpMessage"
    ADD CONSTRAINT "FollowUpMessage_pkey" PRIMARY KEY (id);


--
-- Name: FollowUpSession FollowUpSession_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."FollowUpSession"
    ADD CONSTRAINT "FollowUpSession_pkey" PRIMARY KEY (id);


--
-- Name: ForecastBet ForecastBet_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastBet"
    ADD CONSTRAINT "ForecastBet_pkey" PRIMARY KEY (id);


--
-- Name: ForecastCitation ForecastCitation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastCitation"
    ADD CONSTRAINT "ForecastCitation_pkey" PRIMARY KEY (id);


--
-- Name: ForecastFollowUpMessage ForecastFollowUpMessage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastFollowUpMessage"
    ADD CONSTRAINT "ForecastFollowUpMessage_pkey" PRIMARY KEY (id);


--
-- Name: ForecastFollowUpSession ForecastFollowUpSession_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastFollowUpSession"
    ADD CONSTRAINT "ForecastFollowUpSession_pkey" PRIMARY KEY (id);


--
-- Name: ForecastMarket ForecastMarket_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastMarket"
    ADD CONSTRAINT "ForecastMarket_pkey" PRIMARY KEY (id);


--
-- Name: ForecastPortfolioState ForecastPortfolioState_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastPortfolioState"
    ADD CONSTRAINT "ForecastPortfolioState_pkey" PRIMARY KEY (id);


--
-- Name: ForecastPrediction ForecastPrediction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastPrediction"
    ADD CONSTRAINT "ForecastPrediction_pkey" PRIMARY KEY (id);


--
-- Name: ForecastResolution ForecastResolution_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastResolution"
    ADD CONSTRAINT "ForecastResolution_pkey" PRIMARY KEY (id);


--
-- Name: ForecastTrace ForecastTrace_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastTrace"
    ADD CONSTRAINT "ForecastTrace_pkey" PRIMARY KEY (id);


--
-- Name: Founder Founder_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Founder"
    ADD CONSTRAINT "Founder_pkey" PRIMARY KEY (id);


--
-- Name: MethodMetricRollup MethodMetricRollup_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodMetricRollup"
    ADD CONSTRAINT "MethodMetricRollup_pkey" PRIMARY KEY (id);


--
-- Name: MethodTrackRecord MethodTrackRecord_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodTrackRecord"
    ADD CONSTRAINT "MethodTrackRecord_pkey" PRIMARY KEY (id);


--
-- Name: MethodVersion MethodVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodVersion"
    ADD CONSTRAINT "MethodVersion_pkey" PRIMARY KEY (id);


--
-- Name: MethodologyProfile MethodologyProfile_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyProfile"
    ADD CONSTRAINT "MethodologyProfile_pkey" PRIMARY KEY (id);


--
-- Name: MethodologyQualityScore MethodologyQualityScore_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyQualityScore"
    ADD CONSTRAINT "MethodologyQualityScore_pkey" PRIMARY KEY (id);


--
-- Name: OpenQuestion OpenQuestion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OpenQuestion"
    ADD CONSTRAINT "OpenQuestion_pkey" PRIMARY KEY (id);


--
-- Name: OperatorState OperatorState_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OperatorState"
    ADD CONSTRAINT "OperatorState_pkey" PRIMARY KEY (id);


--
-- Name: OpinionCitation OpinionCitation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OpinionCitation"
    ADD CONSTRAINT "OpinionCitation_pkey" PRIMARY KEY (id);


--
-- Name: Organization Organization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Organization"
    ADD CONSTRAINT "Organization_pkey" PRIMARY KEY (id);


--
-- Name: Principle Principle_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Principle"
    ADD CONSTRAINT "Principle_pkey" PRIMARY KEY (id);


--
-- Name: PublicReply PublicReply_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicReply"
    ADD CONSTRAINT "PublicReply_pkey" PRIMARY KEY (id);


--
-- Name: PublicResponse PublicResponse_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicResponse"
    ADD CONSTRAINT "PublicResponse_pkey" PRIMARY KEY (id);


--
-- Name: PublicationReview PublicationReview_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicationReview"
    ADD CONSTRAINT "PublicationReview_pkey" PRIMARY KEY (id);


--
-- Name: PublicationSignature PublicationSignature_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicationSignature"
    ADD CONSTRAINT "PublicationSignature_pkey" PRIMARY KEY (id);


--
-- Name: PublishedConclusion PublishedConclusion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublishedConclusion"
    ADD CONSTRAINT "PublishedConclusion_pkey" PRIMARY KEY (id);


--
-- Name: RecalibrationOverride RecalibrationOverride_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RecalibrationOverride"
    ADD CONSTRAINT "RecalibrationOverride_pkey" PRIMARY KEY (id);


--
-- Name: ResearchSuggestion ResearchSuggestion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResearchSuggestion"
    ADD CONSTRAINT "ResearchSuggestion_pkey" PRIMARY KEY (id);


--
-- Name: ResolutionMismatch ResolutionMismatch_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResolutionMismatch"
    ADD CONSTRAINT "ResolutionMismatch_pkey" PRIMARY KEY (id);


--
-- Name: ResolutionOverride ResolutionOverride_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResolutionOverride"
    ADD CONSTRAINT "ResolutionOverride_pkey" PRIMARY KEY (id);


--
-- Name: ResolutionRevision ResolutionRevision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResolutionRevision"
    ADD CONSTRAINT "ResolutionRevision_pkey" PRIMARY KEY (id);


--
-- Name: ResponseTriage ResponseTriage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResponseTriage"
    ADD CONSTRAINT "ResponseTriage_pkey" PRIMARY KEY (id);


--
-- Name: ReviewItem ReviewItem_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewItem"
    ADD CONSTRAINT "ReviewItem_pkey" PRIMARY KEY (id);


--
-- Name: RevisionEvent RevisionEvent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RevisionEvent"
    ADD CONSTRAINT "RevisionEvent_pkey" PRIMARY KEY (id);


--
-- Name: Session Session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Session"
    ADD CONSTRAINT "Session_pkey" PRIMARY KEY (id);


--
-- Name: SocialPost SocialPost_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SocialPost"
    ADD CONSTRAINT "SocialPost_pkey" PRIMARY KEY (id);


--
-- Name: SourceCredibilityUpdate SourceCredibilityUpdate_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SourceCredibilityUpdate"
    ADD CONSTRAINT "SourceCredibilityUpdate_pkey" PRIMARY KEY (id);


--
-- Name: SourceStanding SourceStanding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SourceStanding"
    ADD CONSTRAINT "SourceStanding_pkey" PRIMARY KEY (id);


--
-- Name: SourceTriageItem SourceTriageItem_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SourceTriageItem"
    ADD CONSTRAINT "SourceTriageItem_pkey" PRIMARY KEY (id);


--
-- Name: Span Span_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Span"
    ADD CONSTRAINT "Span_pkey" PRIMARY KEY (id);


--
-- Name: Subscriber Subscriber_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Subscriber"
    ADD CONSTRAINT "Subscriber_pkey" PRIMARY KEY (id);


--
-- Name: UploadChunk UploadChunk_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."UploadChunk"
    ADD CONSTRAINT "UploadChunk_pkey" PRIMARY KEY (id);


--
-- Name: Upload Upload_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Upload"
    ADD CONSTRAINT "Upload_pkey" PRIMARY KEY (id);


--
-- Name: WatchedMarket WatchedMarket_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WatchedMarket"
    ADD CONSTRAINT "WatchedMarket_pkey" PRIMARY KEY (id);


--
-- Name: _prisma_migrations _prisma_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public._prisma_migrations
    ADD CONSTRAINT _prisma_migrations_pkey PRIMARY KEY (id);


--
-- Name: adversarial_challenge adversarial_challenge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adversarial_challenge
    ADD CONSTRAINT adversarial_challenge_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: algorithm_calibration_snapshot algorithm_calibration_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.algorithm_calibration_snapshot
    ADD CONSTRAINT algorithm_calibration_snapshot_pkey PRIMARY KEY (id);


--
-- Name: algorithm_input_observation algorithm_input_observation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.algorithm_input_observation
    ADD CONSTRAINT algorithm_input_observation_pkey PRIMARY KEY (id);


--
-- Name: algorithm_invocation algorithm_invocation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.algorithm_invocation
    ADD CONSTRAINT algorithm_invocation_pkey PRIMARY KEY (id);


--
-- Name: algorithm_triage_recommendation algorithm_triage_recommendation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.algorithm_triage_recommendation
    ADD CONSTRAINT algorithm_triage_recommendation_pkey PRIMARY KEY (id);


--
-- Name: artifact artifact_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artifact
    ADD CONSTRAINT artifact_pkey PRIMARY KEY (id);


--
-- Name: battery_run battery_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battery_run
    ADD CONSTRAINT battery_run_pkey PRIMARY KEY (run_id);


--
-- Name: bet_resolution bet_resolution_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bet_resolution
    ADD CONSTRAINT bet_resolution_pkey PRIMARY KEY (id);


--
-- Name: bet_spec bet_spec_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bet_spec
    ADD CONSTRAINT bet_spec_pkey PRIMARY KEY (id);


--
-- Name: cascade_edge cascade_edge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cascade_edge
    ADD CONSTRAINT cascade_edge_pkey PRIMARY KEY (edge_id);


--
-- Name: cascade_node cascade_node_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cascade_node
    ADD CONSTRAINT cascade_node_pkey PRIMARY KEY (node_id);


--
-- Name: chunk chunk_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunk
    ADD CONSTRAINT chunk_pkey PRIMARY KEY (id);


--
-- Name: citation citation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation
    ADD CONSTRAINT citation_pkey PRIMARY KEY (id);


--
-- Name: claim_extraction_cache claim_extraction_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_extraction_cache
    ADD CONSTRAINT claim_extraction_cache_pkey PRIMARY KEY (chunk_id);


--
-- Name: claim claim_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim
    ADD CONSTRAINT claim_pkey PRIMARY KEY (id);


--
-- Name: cluster_reindex_proposal cluster_reindex_proposal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_reindex_proposal
    ADD CONSTRAINT cluster_reindex_proposal_pkey PRIMARY KEY (id);


--
-- Name: coherence_pair coherence_pair_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coherence_pair
    ADD CONSTRAINT coherence_pair_pkey PRIMARY KEY (id);


--
-- Name: coherence_result_cache coherence_result_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coherence_result_cache
    ADD CONSTRAINT coherence_result_cache_pkey PRIMARY KEY (evaluation_key);


--
-- Name: conclusion conclusion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conclusion
    ADD CONSTRAINT conclusion_pkey PRIMARY KEY (id);


--
-- Name: contradiction_dispute contradiction_dispute_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contradiction_dispute
    ADD CONSTRAINT contradiction_dispute_pkey PRIMARY KEY (id);


--
-- Name: contradiction_lifecycle contradiction_lifecycle_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contradiction_lifecycle
    ADD CONSTRAINT contradiction_lifecycle_pkey PRIMARY KEY (id);


--
-- Name: contradiction_result contradiction_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contradiction_result
    ADD CONSTRAINT contradiction_result_pkey PRIMARY KEY (id);


--
-- Name: contradiction_test_task contradiction_test_task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contradiction_test_task
    ADD CONSTRAINT contradiction_test_task_pkey PRIMARY KEY (id);


--
-- Name: counterfactual_eval_run counterfactual_eval_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.counterfactual_eval_run
    ADD CONSTRAINT counterfactual_eval_run_pkey PRIMARY KEY (run_id);


--
-- Name: cut_outcome cut_outcome_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cut_outcome
    ADD CONSTRAINT cut_outcome_pkey PRIMARY KEY (id);


--
-- Name: decay_policy decay_policy_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decay_policy
    ADD CONSTRAINT decay_policy_pkey PRIMARY KEY (id);


--
-- Name: dialectic_contradiction_flag dialectic_contradiction_flag_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dialectic_contradiction_flag
    ADD CONSTRAINT dialectic_contradiction_flag_pkey PRIMARY KEY (id);


--
-- Name: dialectic_session dialectic_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dialectic_session
    ADD CONSTRAINT dialectic_session_pkey PRIMARY KEY (id);


--
-- Name: dialectic_utterance dialectic_utterance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dialectic_utterance
    ADD CONSTRAINT dialectic_utterance_pkey PRIMARY KEY (id);


--
-- Name: drift_event drift_event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drift_event
    ADD CONSTRAINT drift_event_pkey PRIMARY KEY (id);


--
-- Name: embedding_model_version embedding_model_version_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_model_version
    ADD CONSTRAINT embedding_model_version_pkey PRIMARY KEY (id);


--
-- Name: embedding embedding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding
    ADD CONSTRAINT embedding_pkey PRIMARY KEY (id);


--
-- Name: embedding_retry embedding_retry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_retry
    ADD CONSTRAINT embedding_retry_pkey PRIMARY KEY (id);


--
-- Name: entity entity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity
    ADD CONSTRAINT entity_pkey PRIMARY KEY (id);


--
-- Name: external_bundle external_bundle_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_bundle
    ADD CONSTRAINT external_bundle_pkey PRIMARY KEY (content_hash);


--
-- Name: founder_override founder_override_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.founder_override
    ADD CONSTRAINT founder_override_pkey PRIMARY KEY (override_id);


--
-- Name: graph_edge_reasoning graph_edge_reasoning_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_edge_reasoning
    ADD CONSTRAINT graph_edge_reasoning_pkey PRIMARY KEY (id);


--
-- Name: graph_snapshot graph_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_snapshot
    ADD CONSTRAINT graph_snapshot_pkey PRIMARY KEY (id);


--
-- Name: investment_memo investment_memo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.investment_memo
    ADD CONSTRAINT investment_memo_pkey PRIMARY KEY (id);


--
-- Name: ledger_entry ledger_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ledger_entry
    ADD CONSTRAINT ledger_entry_pkey PRIMARY KEY (entry_id);


--
-- Name: logical_algorithm logical_algorithm_org_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logical_algorithm
    ADD CONSTRAINT logical_algorithm_org_name_key UNIQUE (organization_id, name);


--
-- Name: logical_algorithm logical_algorithm_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logical_algorithm
    ADD CONSTRAINT logical_algorithm_pkey PRIMARY KEY (id);


--
-- Name: memo_dispatch memo_dispatch_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memo_dispatch
    ADD CONSTRAINT memo_dispatch_pkey PRIMARY KEY (id);


--
-- Name: method_invocation method_invocation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.method_invocation
    ADD CONSTRAINT method_invocation_pkey PRIMARY KEY (id);


--
-- Name: method method_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.method
    ADD CONSTRAINT method_pkey PRIMARY KEY (method_id);


--
-- Name: mip_manifest mip_manifest_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mip_manifest
    ADD CONSTRAINT mip_manifest_pkey PRIMARY KEY (content_hash);


--
-- Name: object_policy_binding object_policy_binding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.object_policy_binding
    ADD CONSTRAINT object_policy_binding_pkey PRIMARY KEY (id);


--
-- Name: outcome outcome_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outcome
    ADD CONSTRAINT outcome_pkey PRIMARY KEY (outcome_id);


--
-- Name: portfolio_agent portfolio_agent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_agent
    ADD CONSTRAINT portfolio_agent_pkey PRIMARY KEY (id);


--
-- Name: prediction_resolution prediction_resolution_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prediction_resolution
    ADD CONSTRAINT prediction_resolution_pkey PRIMARY KEY (id);


--
-- Name: predictive_claim predictive_claim_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.predictive_claim
    ADD CONSTRAINT predictive_claim_pkey PRIMARY KEY (id);


--
-- Name: principle_cluster_centroid principle_cluster_centroid_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.principle_cluster_centroid
    ADD CONSTRAINT principle_cluster_centroid_pkey PRIMARY KEY (cluster_id);


--
-- Name: principle_cluster principle_cluster_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.principle_cluster
    ADD CONSTRAINT principle_cluster_pkey PRIMARY KEY (principle_id);


--
-- Name: quantitative_formalisation quantitative_formalisation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quantitative_formalisation
    ADD CONSTRAINT quantitative_formalisation_pkey PRIMARY KEY (id);


--
-- Name: quantitative_test_result quantitative_test_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quantitative_test_result
    ADD CONSTRAINT quantitative_test_result_pkey PRIMARY KEY (id);


--
-- Name: reading_queue reading_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_queue
    ADD CONSTRAINT reading_queue_pkey PRIMARY KEY (id);


--
-- Name: rebuttal rebuttal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rebuttal
    ADD CONSTRAINT rebuttal_pkey PRIMARY KEY (id);


--
-- Name: relative_position_map relative_position_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.relative_position_map
    ADD CONSTRAINT relative_position_map_pkey PRIMARY KEY (conclusion_id);


--
-- Name: research_suggestion research_suggestion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_suggestion
    ADD CONSTRAINT research_suggestion_pkey PRIMARY KEY (id);


--
-- Name: revalidation revalidation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revalidation
    ADD CONSTRAINT revalidation_pkey PRIMARY KEY (id);


--
-- Name: review_item review_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_item
    ADD CONSTRAINT review_item_pkey PRIMARY KEY (id);


--
-- Name: review_report review_report_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_report
    ADD CONSTRAINT review_report_pkey PRIMARY KEY (report_id);


--
-- Name: rigor_submission rigor_submission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rigor_submission
    ADD CONSTRAINT rigor_submission_pkey PRIMARY KEY (submission_id);


--
-- Name: rigor_verdict rigor_verdict_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rigor_verdict
    ADD CONSTRAINT rigor_verdict_pkey PRIMARY KEY (ledger_entry_id);


--
-- Name: synthesizer_memo synthesizer_memo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.synthesizer_memo
    ADD CONSTRAINT synthesizer_memo_pkey PRIMARY KEY (id);


--
-- Name: synthesizer_task synthesizer_task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.synthesizer_task
    ADD CONSTRAINT synthesizer_task_pkey PRIMARY KEY (id);


--
-- Name: temporal_cut temporal_cut_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.temporal_cut
    ADD CONSTRAINT temporal_cut_pkey PRIMARY KEY (cut_id);


--
-- Name: topic_cluster topic_cluster_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topic_cluster
    ADD CONSTRAINT topic_cluster_pkey PRIMARY KEY (cluster_id);


--
-- Name: topic_membership topic_membership_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topic_membership
    ADD CONSTRAINT topic_membership_pkey PRIMARY KEY (claim_id);


--
-- Name: transfer_study transfer_study_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transfer_study
    ADD CONSTRAINT transfer_study_pkey PRIMARY KEY (study_id);


--
-- Name: voice_phase voice_phase_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voice_phase
    ADD CONSTRAINT voice_phase_pkey PRIMARY KEY (id);


--
-- Name: voice voice_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voice
    ADD CONSTRAINT voice_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: realtime; Owner: -
--

ALTER TABLE ONLY realtime.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id, inserted_at);


--
-- Name: subscription pk_subscription; Type: CONSTRAINT; Schema: realtime; Owner: -
--

ALTER TABLE ONLY realtime.subscription
    ADD CONSTRAINT pk_subscription PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: realtime; Owner: -
--

ALTER TABLE ONLY realtime.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: buckets_analytics buckets_analytics_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.buckets_analytics
    ADD CONSTRAINT buckets_analytics_pkey PRIMARY KEY (id);


--
-- Name: buckets buckets_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.buckets
    ADD CONSTRAINT buckets_pkey PRIMARY KEY (id);


--
-- Name: buckets_vectors buckets_vectors_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.buckets_vectors
    ADD CONSTRAINT buckets_vectors_pkey PRIMARY KEY (id);


--
-- Name: migrations migrations_name_key; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.migrations
    ADD CONSTRAINT migrations_name_key UNIQUE (name);


--
-- Name: migrations migrations_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.migrations
    ADD CONSTRAINT migrations_pkey PRIMARY KEY (id);


--
-- Name: objects objects_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.objects
    ADD CONSTRAINT objects_pkey PRIMARY KEY (id);


--
-- Name: s3_multipart_uploads_parts s3_multipart_uploads_parts_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.s3_multipart_uploads_parts
    ADD CONSTRAINT s3_multipart_uploads_parts_pkey PRIMARY KEY (id);


--
-- Name: s3_multipart_uploads s3_multipart_uploads_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.s3_multipart_uploads
    ADD CONSTRAINT s3_multipart_uploads_pkey PRIMARY KEY (id);


--
-- Name: vector_indexes vector_indexes_pkey; Type: CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.vector_indexes
    ADD CONSTRAINT vector_indexes_pkey PRIMARY KEY (id);


--
-- Name: audit_logs_instance_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX audit_logs_instance_id_idx ON auth.audit_log_entries USING btree (instance_id);


--
-- Name: confirmation_token_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX confirmation_token_idx ON auth.users USING btree (confirmation_token) WHERE ((confirmation_token)::text !~ '^[0-9 ]*$'::text);


--
-- Name: custom_oauth_providers_created_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX custom_oauth_providers_created_at_idx ON auth.custom_oauth_providers USING btree (created_at);


--
-- Name: custom_oauth_providers_enabled_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX custom_oauth_providers_enabled_idx ON auth.custom_oauth_providers USING btree (enabled);


--
-- Name: custom_oauth_providers_identifier_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX custom_oauth_providers_identifier_idx ON auth.custom_oauth_providers USING btree (identifier);


--
-- Name: custom_oauth_providers_provider_type_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX custom_oauth_providers_provider_type_idx ON auth.custom_oauth_providers USING btree (provider_type);


--
-- Name: email_change_token_current_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX email_change_token_current_idx ON auth.users USING btree (email_change_token_current) WHERE ((email_change_token_current)::text !~ '^[0-9 ]*$'::text);


--
-- Name: email_change_token_new_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX email_change_token_new_idx ON auth.users USING btree (email_change_token_new) WHERE ((email_change_token_new)::text !~ '^[0-9 ]*$'::text);


--
-- Name: factor_id_created_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX factor_id_created_at_idx ON auth.mfa_factors USING btree (user_id, created_at);


--
-- Name: flow_state_created_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX flow_state_created_at_idx ON auth.flow_state USING btree (created_at DESC);


--
-- Name: identities_email_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX identities_email_idx ON auth.identities USING btree (email text_pattern_ops);


--
-- Name: identities_user_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX identities_user_id_idx ON auth.identities USING btree (user_id);


--
-- Name: idx_auth_code; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_code ON auth.flow_state USING btree (auth_code);


--
-- Name: idx_oauth_client_states_created_at; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_oauth_client_states_created_at ON auth.oauth_client_states USING btree (created_at);


--
-- Name: idx_user_id_auth_method; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_user_id_auth_method ON auth.flow_state USING btree (user_id, authentication_method);


--
-- Name: idx_users_created_at_desc; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_users_created_at_desc ON auth.users USING btree (created_at DESC);


--
-- Name: idx_users_email; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_users_email ON auth.users USING btree (email);


--
-- Name: idx_users_last_sign_in_at_desc; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_users_last_sign_in_at_desc ON auth.users USING btree (last_sign_in_at DESC);


--
-- Name: idx_users_name; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_users_name ON auth.users USING btree (((raw_user_meta_data ->> 'name'::text))) WHERE ((raw_user_meta_data ->> 'name'::text) IS NOT NULL);


--
-- Name: mfa_challenge_created_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX mfa_challenge_created_at_idx ON auth.mfa_challenges USING btree (created_at DESC);


--
-- Name: mfa_factors_user_friendly_name_unique; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX mfa_factors_user_friendly_name_unique ON auth.mfa_factors USING btree (friendly_name, user_id) WHERE (TRIM(BOTH FROM friendly_name) <> ''::text);


--
-- Name: mfa_factors_user_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX mfa_factors_user_id_idx ON auth.mfa_factors USING btree (user_id);


--
-- Name: oauth_auth_pending_exp_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX oauth_auth_pending_exp_idx ON auth.oauth_authorizations USING btree (expires_at) WHERE (status = 'pending'::auth.oauth_authorization_status);


--
-- Name: oauth_clients_deleted_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX oauth_clients_deleted_at_idx ON auth.oauth_clients USING btree (deleted_at);


--
-- Name: oauth_consents_active_client_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX oauth_consents_active_client_idx ON auth.oauth_consents USING btree (client_id) WHERE (revoked_at IS NULL);


--
-- Name: oauth_consents_active_user_client_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX oauth_consents_active_user_client_idx ON auth.oauth_consents USING btree (user_id, client_id) WHERE (revoked_at IS NULL);


--
-- Name: oauth_consents_user_order_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX oauth_consents_user_order_idx ON auth.oauth_consents USING btree (user_id, granted_at DESC);


--
-- Name: one_time_tokens_relates_to_hash_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX one_time_tokens_relates_to_hash_idx ON auth.one_time_tokens USING hash (relates_to);


--
-- Name: one_time_tokens_token_hash_hash_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX one_time_tokens_token_hash_hash_idx ON auth.one_time_tokens USING hash (token_hash);


--
-- Name: one_time_tokens_user_id_token_type_key; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX one_time_tokens_user_id_token_type_key ON auth.one_time_tokens USING btree (user_id, token_type);


--
-- Name: reauthentication_token_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX reauthentication_token_idx ON auth.users USING btree (reauthentication_token) WHERE ((reauthentication_token)::text !~ '^[0-9 ]*$'::text);


--
-- Name: recovery_token_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX recovery_token_idx ON auth.users USING btree (recovery_token) WHERE ((recovery_token)::text !~ '^[0-9 ]*$'::text);


--
-- Name: refresh_tokens_instance_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX refresh_tokens_instance_id_idx ON auth.refresh_tokens USING btree (instance_id);


--
-- Name: refresh_tokens_instance_id_user_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX refresh_tokens_instance_id_user_id_idx ON auth.refresh_tokens USING btree (instance_id, user_id);


--
-- Name: refresh_tokens_parent_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX refresh_tokens_parent_idx ON auth.refresh_tokens USING btree (parent);


--
-- Name: refresh_tokens_session_id_revoked_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX refresh_tokens_session_id_revoked_idx ON auth.refresh_tokens USING btree (session_id, revoked);


--
-- Name: refresh_tokens_updated_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX refresh_tokens_updated_at_idx ON auth.refresh_tokens USING btree (updated_at DESC);


--
-- Name: saml_providers_sso_provider_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX saml_providers_sso_provider_id_idx ON auth.saml_providers USING btree (sso_provider_id);


--
-- Name: saml_relay_states_created_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX saml_relay_states_created_at_idx ON auth.saml_relay_states USING btree (created_at DESC);


--
-- Name: saml_relay_states_for_email_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX saml_relay_states_for_email_idx ON auth.saml_relay_states USING btree (for_email);


--
-- Name: saml_relay_states_sso_provider_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX saml_relay_states_sso_provider_id_idx ON auth.saml_relay_states USING btree (sso_provider_id);


--
-- Name: sessions_not_after_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX sessions_not_after_idx ON auth.sessions USING btree (not_after DESC);


--
-- Name: sessions_oauth_client_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX sessions_oauth_client_id_idx ON auth.sessions USING btree (oauth_client_id);


--
-- Name: sessions_user_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX sessions_user_id_idx ON auth.sessions USING btree (user_id);


--
-- Name: sso_domains_domain_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX sso_domains_domain_idx ON auth.sso_domains USING btree (lower(domain));


--
-- Name: sso_domains_sso_provider_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX sso_domains_sso_provider_id_idx ON auth.sso_domains USING btree (sso_provider_id);


--
-- Name: sso_providers_resource_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX sso_providers_resource_id_idx ON auth.sso_providers USING btree (lower(resource_id));


--
-- Name: sso_providers_resource_id_pattern_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX sso_providers_resource_id_pattern_idx ON auth.sso_providers USING btree (resource_id text_pattern_ops);


--
-- Name: unique_phone_factor_per_user; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX unique_phone_factor_per_user ON auth.mfa_factors USING btree (user_id, phone);


--
-- Name: user_id_created_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX user_id_created_at_idx ON auth.sessions USING btree (user_id, created_at);


--
-- Name: users_email_partial_key; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX users_email_partial_key ON auth.users USING btree (email) WHERE (is_sso_user = false);


--
-- Name: users_instance_id_email_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX users_instance_id_email_idx ON auth.users USING btree (instance_id, lower((email)::text));


--
-- Name: users_instance_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX users_instance_id_idx ON auth.users USING btree (instance_id);


--
-- Name: users_is_anonymous_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX users_is_anonymous_idx ON auth.users USING btree (is_anonymous);


--
-- Name: webauthn_challenges_expires_at_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX webauthn_challenges_expires_at_idx ON auth.webauthn_challenges USING btree (expires_at);


--
-- Name: webauthn_challenges_user_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX webauthn_challenges_user_id_idx ON auth.webauthn_challenges USING btree (user_id);


--
-- Name: webauthn_credentials_credential_id_key; Type: INDEX; Schema: auth; Owner: -
--

CREATE UNIQUE INDEX webauthn_credentials_credential_id_key ON auth.webauthn_credentials USING btree (credential_id);


--
-- Name: webauthn_credentials_user_id_idx; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX webauthn_credentials_user_id_idx ON auth.webauthn_credentials USING btree (user_id);


--
-- Name: Addendum_articleSlug_status_publishedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Addendum_articleSlug_status_publishedAt_idx" ON public."Addendum" USING btree ("articleSlug", status, "publishedAt");


--
-- Name: Addendum_organizationId_articleSlug_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Addendum_organizationId_articleSlug_status_idx" ON public."Addendum" USING btree ("organizationId", "articleSlug", status);


--
-- Name: AlertEvent_acknowledgedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AlertEvent_acknowledgedAt_idx" ON public."AlertEvent" USING btree ("acknowledgedAt");


--
-- Name: AlertEvent_firedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AlertEvent_firedAt_idx" ON public."AlertEvent" USING btree ("firedAt");


--
-- Name: AlertEvent_ruleName_firedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AlertEvent_ruleName_firedAt_idx" ON public."AlertEvent" USING btree ("ruleName", "firedAt");


--
-- Name: AlertRule_name_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "AlertRule_name_key" ON public."AlertRule" USING btree (name);


--
-- Name: AnchorRevision_organizationId_methodName_methodVersion_acti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AnchorRevision_organizationId_methodName_methodVersion_acti_idx" ON public."AnchorRevision" USING btree ("organizationId", "methodName", "methodVersion", active);


--
-- Name: AnchorRevision_organizationId_methodName_methodVersion_revi_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "AnchorRevision_organizationId_methodName_methodVersion_revi_key" ON public."AnchorRevision" USING btree ("organizationId", "methodName", "methodVersion", "revisionId");


--
-- Name: ApiKey_founderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ApiKey_founderId_idx" ON public."ApiKey" USING btree ("founderId");


--
-- Name: ApiKey_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ApiKey_organizationId_idx" ON public."ApiKey" USING btree ("organizationId");


--
-- Name: ApiKey_prefix_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ApiKey_prefix_idx" ON public."ApiKey" USING btree (prefix);


--
-- Name: AttentionAction_founderId_queue_itemId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AttentionAction_founderId_queue_itemId_createdAt_idx" ON public."AttentionAction" USING btree ("founderId", queue, "itemId", "createdAt");


--
-- Name: AttentionAction_organizationId_founderId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AttentionAction_organizationId_founderId_createdAt_idx" ON public."AttentionAction" USING btree ("organizationId", "founderId", "createdAt");


--
-- Name: AttentionAction_organizationId_queue_action_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AttentionAction_organizationId_queue_action_createdAt_idx" ON public."AttentionAction" USING btree ("organizationId", queue, action, "createdAt");


--
-- Name: AuditEvent_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "AuditEvent_organizationId_idx" ON public."AuditEvent" USING btree ("organizationId");


--
-- Name: CalibrationModel_organizationId_domain_active_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CalibrationModel_organizationId_domain_active_idx" ON public."CalibrationModel" USING btree ("organizationId", domain, active);


--
-- Name: CalibrationModel_organizationId_domain_fitAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CalibrationModel_organizationId_domain_fitAt_idx" ON public."CalibrationModel" USING btree ("organizationId", domain, "fitAt");


--
-- Name: CalibrationModel_organizationId_domain_version_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "CalibrationModel_organizationId_domain_version_key" ON public."CalibrationModel" USING btree ("organizationId", domain, version);


--
-- Name: CitationVerdict_organizationId_citationKind_citationId_comp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CitationVerdict_organizationId_citationKind_citationId_comp_idx" ON public."CitationVerdict" USING btree ("organizationId", "citationKind", "citationId", "computedAt");


--
-- Name: CitationVerdict_organizationId_relationHolds_computedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CitationVerdict_organizationId_relationHolds_computedAt_idx" ON public."CitationVerdict" USING btree ("organizationId", "relationHolds", "computedAt");


--
-- Name: CitationVerdict_organizationId_sourceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CitationVerdict_organizationId_sourceId_idx" ON public."CitationVerdict" USING btree ("organizationId", "sourceId");


--
-- Name: CitationVerdict_sourceId_computedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CitationVerdict_sourceId_computedAt_idx" ON public."CitationVerdict" USING btree ("sourceId", "computedAt");


--
-- Name: ConclusionDeletionRequest_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionDeletionRequest_conclusionId_idx" ON public."ConclusionDeletionRequest" USING btree ("conclusionId");


--
-- Name: ConclusionDeletionRequest_requesterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionDeletionRequest_requesterId_idx" ON public."ConclusionDeletionRequest" USING btree ("requesterId");


--
-- Name: ConclusionDeletionRequest_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionDeletionRequest_status_idx" ON public."ConclusionDeletionRequest" USING btree (status);


--
-- Name: ConclusionMethod_conclusionId_methodName_methodVersion_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ConclusionMethod_conclusionId_methodName_methodVersion_key" ON public."ConclusionMethod" USING btree ("conclusionId", "methodName", "methodVersion");


--
-- Name: ConclusionMethod_methodName_methodVersion_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionMethod_methodName_methodVersion_idx" ON public."ConclusionMethod" USING btree ("methodName", "methodVersion");


--
-- Name: ConclusionMethod_organizationId_methodName_methodVersion_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionMethod_organizationId_methodName_methodVersion_idx" ON public."ConclusionMethod" USING btree ("organizationId", "methodName", "methodVersion");


--
-- Name: ConclusionSource_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionSource_conclusionId_idx" ON public."ConclusionSource" USING btree ("conclusionId");


--
-- Name: ConclusionSource_uploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ConclusionSource_uploadId_idx" ON public."ConclusionSource" USING btree ("uploadId");


--
-- Name: Conclusion_noosphereId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Conclusion_noosphereId_key" ON public."Conclusion" USING btree ("noosphereId");


--
-- Name: Conclusion_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Conclusion_organizationId_idx" ON public."Conclusion" USING btree ("organizationId");


--
-- Name: Conclusion_organizationId_normalizedText_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Conclusion_organizationId_normalizedText_idx" ON public."Conclusion" USING btree ("organizationId", "normalizedText");


--
-- Name: ContactSubmission_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ContactSubmission_createdAt_idx" ON public."ContactSubmission" USING btree ("createdAt");


--
-- Name: ContactSubmission_fromEmail_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ContactSubmission_fromEmail_idx" ON public."ContactSubmission" USING btree ("fromEmail");


--
-- Name: ContactSubmission_ipHash_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ContactSubmission_ipHash_createdAt_idx" ON public."ContactSubmission" USING btree ("ipHash", "createdAt");


--
-- Name: ContactSubmission_triagedAt_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ContactSubmission_triagedAt_createdAt_idx" ON public."ContactSubmission" USING btree ("triagedAt", "createdAt");


--
-- Name: Contradiction_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Contradiction_organizationId_idx" ON public."Contradiction" USING btree ("organizationId");


--
-- Name: Contradiction_sourceUploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Contradiction_sourceUploadId_idx" ON public."Contradiction" USING btree ("sourceUploadId");


--
-- Name: Contradiction_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Contradiction_status_idx" ON public."Contradiction" USING btree (status);


--
-- Name: CritiqueBountyPayout_critiqueSubmissionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "CritiqueBountyPayout_critiqueSubmissionId_key" ON public."CritiqueBountyPayout" USING btree ("critiqueSubmissionId");


--
-- Name: CritiqueBountyPayout_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CritiqueBountyPayout_organizationId_idx" ON public."CritiqueBountyPayout" USING btree ("organizationId");


--
-- Name: CritiqueBountyPayout_organizationId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CritiqueBountyPayout_organizationId_status_idx" ON public."CritiqueBountyPayout" USING btree ("organizationId", status);


--
-- Name: CritiqueSubmission_organizationId_articleSlug_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CritiqueSubmission_organizationId_articleSlug_status_idx" ON public."CritiqueSubmission" USING btree ("organizationId", "articleSlug", status);


--
-- Name: CritiqueSubmission_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CritiqueSubmission_organizationId_idx" ON public."CritiqueSubmission" USING btree ("organizationId");


--
-- Name: CritiqueSubmission_organizationId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CritiqueSubmission_organizationId_status_idx" ON public."CritiqueSubmission" USING btree ("organizationId", status);


--
-- Name: CritiqueSubmission_severityValue_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CritiqueSubmission_severityValue_idx" ON public."CritiqueSubmission" USING btree ("severityValue");


--
-- Name: CurrentEvent_dedupeHash_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "CurrentEvent_dedupeHash_key" ON public."CurrentEvent" USING btree ("dedupeHash");


--
-- Name: CurrentEvent_organizationId_observedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CurrentEvent_organizationId_observedAt_idx" ON public."CurrentEvent" USING btree ("organizationId", "observedAt");


--
-- Name: CurrentEvent_organizationId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CurrentEvent_organizationId_status_idx" ON public."CurrentEvent" USING btree ("organizationId", status);


--
-- Name: DashboardDismissal_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DashboardDismissal_conclusionId_idx" ON public."DashboardDismissal" USING btree ("conclusionId");


--
-- Name: DashboardDismissal_founderId_conclusionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "DashboardDismissal_founderId_conclusionId_key" ON public."DashboardDismissal" USING btree ("founderId", "conclusionId");


--
-- Name: DashboardDismissal_founderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DashboardDismissal_founderId_idx" ON public."DashboardDismissal" USING btree ("founderId");


--
-- Name: DeletionRequest_active_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "DeletionRequest_active_unique" ON public."DeletionRequest" USING btree ("uploadId", "requesterId") WHERE (status = 'pending'::text);


--
-- Name: DeletionRequest_requesterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DeletionRequest_requesterId_idx" ON public."DeletionRequest" USING btree ("requesterId");


--
-- Name: DeletionRequest_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DeletionRequest_status_idx" ON public."DeletionRequest" USING btree (status);


--
-- Name: DeletionRequest_uploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DeletionRequest_uploadId_idx" ON public."DeletionRequest" USING btree ("uploadId");


--
-- Name: DomainBoundVerdict_conclusionId_methodName_methodVersion_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "DomainBoundVerdict_conclusionId_methodName_methodVersion_key" ON public."DomainBoundVerdict" USING btree ("conclusionId", "methodName", "methodVersion");


--
-- Name: DomainBoundVerdict_organizationId_methodName_methodVersion_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DomainBoundVerdict_organizationId_methodName_methodVersion_idx" ON public."DomainBoundVerdict" USING btree ("organizationId", "methodName", "methodVersion");


--
-- Name: DomainBoundVerdict_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DomainBoundVerdict_status_idx" ON public."DomainBoundVerdict" USING btree (status);


--
-- Name: DriftEvent_noosphereId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "DriftEvent_noosphereId_key" ON public."DriftEvent" USING btree ("noosphereId");


--
-- Name: DriftEvent_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DriftEvent_organizationId_idx" ON public."DriftEvent" USING btree ("organizationId");


--
-- Name: DriftEvent_organizationId_methodName_methodVersion_methodDo_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DriftEvent_organizationId_methodName_methodVersion_methodDo_idx" ON public."DriftEvent" USING btree ("organizationId", "methodName", "methodVersion", "methodDomain", "observedAt");


--
-- Name: DriftEvent_targetKind_observedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "DriftEvent_targetKind_observedAt_idx" ON public."DriftEvent" USING btree ("targetKind", "observedAt");


--
-- Name: EquityInstrument_assetClass_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityInstrument_assetClass_idx" ON public."EquityInstrument" USING btree ("assetClass");


--
-- Name: EquityInstrument_updatedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityInstrument_updatedAt_idx" ON public."EquityInstrument" USING btree ("updatedAt");


--
-- Name: EquityPosition_externalOrderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityPosition_externalOrderId_idx" ON public."EquityPosition" USING btree ("externalOrderId");


--
-- Name: EquityPosition_instrumentId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityPosition_instrumentId_status_idx" ON public."EquityPosition" USING btree ("instrumentId", status);


--
-- Name: EquityPosition_signalId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityPosition_signalId_idx" ON public."EquityPosition" USING btree ("signalId");


--
-- Name: EquityPriceTick_instrumentId_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityPriceTick_instrumentId_ts_idx" ON public."EquityPriceTick" USING btree ("instrumentId", ts);


--
-- Name: EquityPriceTick_source_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquityPriceTick_source_idx" ON public."EquityPriceTick" USING btree (source);


--
-- Name: EquitySignalCitation_signalId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquitySignalCitation_signalId_idx" ON public."EquitySignalCitation" USING btree ("signalId");


--
-- Name: EquitySignalCitation_sourceType_sourceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquitySignalCitation_sourceType_sourceId_idx" ON public."EquitySignalCitation" USING btree ("sourceType", "sourceId");


--
-- Name: EquitySignal_instrumentId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquitySignal_instrumentId_createdAt_idx" ON public."EquitySignal" USING btree ("instrumentId", "createdAt");


--
-- Name: EquitySignal_liveAuthorizedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquitySignal_liveAuthorizedAt_idx" ON public."EquitySignal" USING btree ("liveAuthorizedAt");


--
-- Name: EquitySignal_organizationId_status_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EquitySignal_organizationId_status_createdAt_idx" ON public."EquitySignal" USING btree ("organizationId", status, "createdAt");


--
-- Name: EventOpinion_eventId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EventOpinion_eventId_idx" ON public."EventOpinion" USING btree ("eventId");


--
-- Name: EventOpinion_organizationId_generatedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "EventOpinion_organizationId_generatedAt_idx" ON public."EventOpinion" USING btree ("organizationId", "generatedAt");


--
-- Name: FollowUpMessage_sessionId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "FollowUpMessage_sessionId_createdAt_idx" ON public."FollowUpMessage" USING btree ("sessionId", "createdAt");


--
-- Name: FollowUpSession_clientFingerprint_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "FollowUpSession_clientFingerprint_createdAt_idx" ON public."FollowUpSession" USING btree ("clientFingerprint", "createdAt");


--
-- Name: FollowUpSession_opinionId_lastActivityAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "FollowUpSession_opinionId_lastActivityAt_idx" ON public."FollowUpSession" USING btree ("opinionId", "lastActivityAt");


--
-- Name: ForecastBet_clientOrderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastBet_clientOrderId_idx" ON public."ForecastBet" USING btree ("clientOrderId");


--
-- Name: ForecastBet_externalOrderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastBet_externalOrderId_idx" ON public."ForecastBet" USING btree ("externalOrderId");


--
-- Name: ForecastBet_organizationId_mode_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastBet_organizationId_mode_createdAt_idx" ON public."ForecastBet" USING btree ("organizationId", mode, "createdAt");


--
-- Name: ForecastBet_predictionId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastBet_predictionId_status_idx" ON public."ForecastBet" USING btree ("predictionId", status);


--
-- Name: ForecastCitation_predictionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastCitation_predictionId_idx" ON public."ForecastCitation" USING btree ("predictionId");


--
-- Name: ForecastCitation_sourceType_sourceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastCitation_sourceType_sourceId_idx" ON public."ForecastCitation" USING btree ("sourceType", "sourceId");


--
-- Name: ForecastFollowUpMessage_sessionId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastFollowUpMessage_sessionId_createdAt_idx" ON public."ForecastFollowUpMessage" USING btree ("sessionId", "createdAt");


--
-- Name: ForecastFollowUpSession_clientFingerprint_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastFollowUpSession_clientFingerprint_createdAt_idx" ON public."ForecastFollowUpSession" USING btree ("clientFingerprint", "createdAt");


--
-- Name: ForecastFollowUpSession_predictionId_lastActivityAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastFollowUpSession_predictionId_lastActivityAt_idx" ON public."ForecastFollowUpSession" USING btree ("predictionId", "lastActivityAt");


--
-- Name: ForecastMarket_organizationId_status_closeTime_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastMarket_organizationId_status_closeTime_idx" ON public."ForecastMarket" USING btree ("organizationId", status, "closeTime");


--
-- Name: ForecastMarket_source_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastMarket_source_category_idx" ON public."ForecastMarket" USING btree (source, category);


--
-- Name: ForecastMarket_source_externalId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ForecastMarket_source_externalId_key" ON public."ForecastMarket" USING btree (source, "externalId");


--
-- Name: ForecastMarket_updatedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastMarket_updatedAt_idx" ON public."ForecastMarket" USING btree ("updatedAt");


--
-- Name: ForecastPortfolioState_organizationId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ForecastPortfolioState_organizationId_key" ON public."ForecastPortfolioState" USING btree ("organizationId");


--
-- Name: ForecastPrediction_liveAuthorizedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastPrediction_liveAuthorizedAt_idx" ON public."ForecastPrediction" USING btree ("liveAuthorizedAt");


--
-- Name: ForecastPrediction_marketId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastPrediction_marketId_createdAt_idx" ON public."ForecastPrediction" USING btree ("marketId", "createdAt");


--
-- Name: ForecastPrediction_organizationId_status_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastPrediction_organizationId_status_createdAt_idx" ON public."ForecastPrediction" USING btree ("organizationId", status, "createdAt");


--
-- Name: ForecastResolution_calibrationBucket_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastResolution_calibrationBucket_idx" ON public."ForecastResolution" USING btree ("calibrationBucket");


--
-- Name: ForecastResolution_predictionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ForecastResolution_predictionId_key" ON public."ForecastResolution" USING btree ("predictionId");


--
-- Name: ForecastResolution_resolvedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastResolution_resolvedAt_idx" ON public."ForecastResolution" USING btree ("resolvedAt");


--
-- Name: ForecastTrace_marketId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastTrace_marketId_idx" ON public."ForecastTrace" USING btree ("marketId");


--
-- Name: ForecastTrace_organizationId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ForecastTrace_organizationId_createdAt_idx" ON public."ForecastTrace" USING btree ("organizationId", "createdAt");


--
-- Name: ForecastTrace_predictionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ForecastTrace_predictionId_key" ON public."ForecastTrace" USING btree ("predictionId");


--
-- Name: Founder_organizationId_email_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Founder_organizationId_email_key" ON public."Founder" USING btree ("organizationId", email);


--
-- Name: Founder_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Founder_organizationId_idx" ON public."Founder" USING btree ("organizationId");


--
-- Name: Founder_organizationId_username_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Founder_organizationId_username_key" ON public."Founder" USING btree ("organizationId", username);


--
-- Name: MethodMetricRollup_method_windowStart_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodMetricRollup_method_windowStart_idx" ON public."MethodMetricRollup" USING btree (method, "windowStart");


--
-- Name: MethodMetricRollup_method_windowStart_windowEnd_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "MethodMetricRollup_method_windowStart_windowEnd_key" ON public."MethodMetricRollup" USING btree (method, "windowStart", "windowEnd");


--
-- Name: MethodMetricRollup_windowStart_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodMetricRollup_windowStart_idx" ON public."MethodMetricRollup" USING btree ("windowStart");


--
-- Name: MethodTrackRecord_methodName_methodVersion_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodTrackRecord_methodName_methodVersion_idx" ON public."MethodTrackRecord" USING btree ("methodName", "methodVersion");


--
-- Name: MethodTrackRecord_organizationId_computedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodTrackRecord_organizationId_computedAt_idx" ON public."MethodTrackRecord" USING btree ("organizationId", "computedAt");


--
-- Name: MethodTrackRecord_organizationId_methodName_methodVersion_d_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "MethodTrackRecord_organizationId_methodName_methodVersion_d_key" ON public."MethodTrackRecord" USING btree ("organizationId", "methodName", "methodVersion", domain);


--
-- Name: MethodVersion_methodName_capturedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodVersion_methodName_capturedAt_idx" ON public."MethodVersion" USING btree ("methodName", "capturedAt");


--
-- Name: MethodVersion_organizationId_methodName_contentHash_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "MethodVersion_organizationId_methodName_contentHash_key" ON public."MethodVersion" USING btree ("organizationId", "methodName", "contentHash");


--
-- Name: MethodVersion_organizationId_methodName_methodVersion_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodVersion_organizationId_methodName_methodVersion_idx" ON public."MethodVersion" USING btree ("organizationId", "methodName", "methodVersion");


--
-- Name: MethodologyProfile_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodologyProfile_conclusionId_idx" ON public."MethodologyProfile" USING btree ("conclusionId");


--
-- Name: MethodologyProfile_organizationId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodologyProfile_organizationId_createdAt_idx" ON public."MethodologyProfile" USING btree ("organizationId", "createdAt");


--
-- Name: MethodologyProfile_organizationId_dedupeKey_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "MethodologyProfile_organizationId_dedupeKey_key" ON public."MethodologyProfile" USING btree ("organizationId", "dedupeKey");


--
-- Name: MethodologyProfile_organizationId_patternType_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodologyProfile_organizationId_patternType_idx" ON public."MethodologyProfile" USING btree ("organizationId", "patternType");


--
-- Name: MethodologyProfile_uploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodologyProfile_uploadId_idx" ON public."MethodologyProfile" USING btree ("uploadId");


--
-- Name: MethodologyQualityScore_conclusionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "MethodologyQualityScore_conclusionId_key" ON public."MethodologyQualityScore" USING btree ("conclusionId");


--
-- Name: MethodologyQualityScore_organizationId_composite_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodologyQualityScore_organizationId_composite_idx" ON public."MethodologyQualityScore" USING btree ("organizationId", composite);


--
-- Name: MethodologyQualityScore_organizationId_scoredAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "MethodologyQualityScore_organizationId_scoredAt_idx" ON public."MethodologyQualityScore" USING btree ("organizationId", "scoredAt");


--
-- Name: OpenQuestion_noosphereId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "OpenQuestion_noosphereId_key" ON public."OpenQuestion" USING btree ("noosphereId");


--
-- Name: OpenQuestion_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OpenQuestion_organizationId_idx" ON public."OpenQuestion" USING btree ("organizationId");


--
-- Name: OpenQuestion_sourceUploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OpenQuestion_sourceUploadId_idx" ON public."OpenQuestion" USING btree ("sourceUploadId");


--
-- Name: OperatorState_key_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OperatorState_key_idx" ON public."OperatorState" USING btree (key);


--
-- Name: OperatorState_organizationId_key_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "OperatorState_organizationId_key_key" ON public."OperatorState" USING btree ("organizationId", key);


--
-- Name: OpinionCitation_claimId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OpinionCitation_claimId_idx" ON public."OpinionCitation" USING btree ("claimId");


--
-- Name: OpinionCitation_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OpinionCitation_conclusionId_idx" ON public."OpinionCitation" USING btree ("conclusionId");


--
-- Name: OpinionCitation_opinionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OpinionCitation_opinionId_idx" ON public."OpinionCitation" USING btree ("opinionId");


--
-- Name: Organization_slug_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Organization_slug_key" ON public."Organization" USING btree (slug);


--
-- Name: Principle_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Principle_organizationId_idx" ON public."Principle" USING btree ("organizationId");


--
-- Name: Principle_organizationId_publicVisible_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Principle_organizationId_publicVisible_idx" ON public."Principle" USING btree ("organizationId", "publicVisible");


--
-- Name: Principle_organizationId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Principle_organizationId_status_idx" ON public."Principle" USING btree ("organizationId", status);


--
-- Name: PublicReply_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicReply_organizationId_idx" ON public."PublicReply" USING btree ("organizationId");


--
-- Name: PublicReply_organizationId_visibility_publishConfirmed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicReply_organizationId_visibility_publishConfirmed_idx" ON public."PublicReply" USING btree ("organizationId", visibility, "publishConfirmed");


--
-- Name: PublicReply_publicResponseId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "PublicReply_publicResponseId_key" ON public."PublicReply" USING btree ("publicResponseId");


--
-- Name: PublicResponse_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicResponse_organizationId_idx" ON public."PublicResponse" USING btree ("organizationId");


--
-- Name: PublicResponse_publishedConclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicResponse_publishedConclusionId_idx" ON public."PublicResponse" USING btree ("publishedConclusionId");


--
-- Name: PublicResponse_seenAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicResponse_seenAt_idx" ON public."PublicResponse" USING btree ("seenAt");


--
-- Name: PublicResponse_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicResponse_status_idx" ON public."PublicResponse" USING btree (status);


--
-- Name: PublicationReview_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicationReview_conclusionId_idx" ON public."PublicationReview" USING btree ("conclusionId");


--
-- Name: PublicationReview_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicationReview_organizationId_idx" ON public."PublicationReview" USING btree ("organizationId");


--
-- Name: PublicationReview_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicationReview_status_idx" ON public."PublicationReview" USING btree (status);


--
-- Name: PublicationSignature_keyFingerprint_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicationSignature_keyFingerprint_idx" ON public."PublicationSignature" USING btree ("keyFingerprint");


--
-- Name: PublicationSignature_publishedConclusionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "PublicationSignature_publishedConclusionId_key" ON public."PublicationSignature" USING btree ("publishedConclusionId");


--
-- Name: PublicationSignature_slug_version_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublicationSignature_slug_version_idx" ON public."PublicationSignature" USING btree (slug, version);


--
-- Name: PublishedConclusion_kind_publishedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublishedConclusion_kind_publishedAt_idx" ON public."PublishedConclusion" USING btree (kind, "publishedAt");


--
-- Name: PublishedConclusion_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublishedConclusion_organizationId_idx" ON public."PublishedConclusion" USING btree ("organizationId");


--
-- Name: PublishedConclusion_slug_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "PublishedConclusion_slug_idx" ON public."PublishedConclusion" USING btree (slug);


--
-- Name: PublishedConclusion_slug_version_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "PublishedConclusion_slug_version_key" ON public."PublishedConclusion" USING btree (slug, version);


--
-- Name: RecalibrationOverride_conclusionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "RecalibrationOverride_conclusionId_key" ON public."RecalibrationOverride" USING btree ("conclusionId");


--
-- Name: RecalibrationOverride_founderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RecalibrationOverride_founderId_idx" ON public."RecalibrationOverride" USING btree ("founderId");


--
-- Name: RecalibrationOverride_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RecalibrationOverride_organizationId_idx" ON public."RecalibrationOverride" USING btree ("organizationId");


--
-- Name: ResearchSuggestion_noosphereId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ResearchSuggestion_noosphereId_key" ON public."ResearchSuggestion" USING btree ("noosphereId");


--
-- Name: ResearchSuggestion_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResearchSuggestion_organizationId_idx" ON public."ResearchSuggestion" USING btree ("organizationId");


--
-- Name: ResearchSuggestion_sourceUploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResearchSuggestion_sourceUploadId_idx" ON public."ResearchSuggestion" USING btree ("sourceUploadId");


--
-- Name: ResolutionMismatch_predictionId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResolutionMismatch_predictionId_createdAt_idx" ON public."ResolutionMismatch" USING btree ("predictionId", "createdAt");


--
-- Name: ResolutionMismatch_reviewedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResolutionMismatch_reviewedAt_idx" ON public."ResolutionMismatch" USING btree ("reviewedAt");


--
-- Name: ResolutionOverride_founderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResolutionOverride_founderId_idx" ON public."ResolutionOverride" USING btree ("founderId");


--
-- Name: ResolutionOverride_predictionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ResolutionOverride_predictionId_key" ON public."ResolutionOverride" USING btree ("predictionId");


--
-- Name: ResolutionOverride_resolvedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResolutionOverride_resolvedAt_idx" ON public."ResolutionOverride" USING btree ("resolvedAt");


--
-- Name: ResolutionRevision_resolutionId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResolutionRevision_resolutionId_createdAt_idx" ON public."ResolutionRevision" USING btree ("resolutionId", "createdAt");


--
-- Name: ResponseTriage_organizationId_archivedAt_severityValue_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResponseTriage_organizationId_archivedAt_severityValue_idx" ON public."ResponseTriage" USING btree ("organizationId", "archivedAt", "severityValue");


--
-- Name: ResponseTriage_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResponseTriage_organizationId_idx" ON public."ResponseTriage" USING btree ("organizationId");


--
-- Name: ResponseTriage_organizationId_label_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResponseTriage_organizationId_label_idx" ON public."ResponseTriage" USING btree ("organizationId", label);


--
-- Name: ResponseTriage_publicResponseId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ResponseTriage_publicResponseId_key" ON public."ResponseTriage" USING btree ("publicResponseId");


--
-- Name: ResponseTriage_senderHash_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ResponseTriage_senderHash_idx" ON public."ResponseTriage" USING btree ("senderHash");


--
-- Name: ReviewItem_noosphereId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ReviewItem_noosphereId_key" ON public."ReviewItem" USING btree ("noosphereId");


--
-- Name: ReviewItem_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewItem_organizationId_idx" ON public."ReviewItem" USING btree ("organizationId");


--
-- Name: RevisionEvent_organizationId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RevisionEvent_organizationId_createdAt_idx" ON public."RevisionEvent" USING btree ("organizationId", "createdAt");


--
-- Name: RevisionEvent_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RevisionEvent_organizationId_idx" ON public."RevisionEvent" USING btree ("organizationId");


--
-- Name: RevisionEvent_planId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RevisionEvent_planId_idx" ON public."RevisionEvent" USING btree ("planId");


--
-- Name: Session_founderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Session_founderId_idx" ON public."Session" USING btree ("founderId");


--
-- Name: Session_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Session_organizationId_idx" ON public."Session" USING btree ("organizationId");


--
-- Name: Session_token_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Session_token_key" ON public."Session" USING btree (token);


--
-- Name: SocialPost_bundleId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SocialPost_bundleId_idx" ON public."SocialPost" USING btree ("bundleId");


--
-- Name: SocialPost_organizationId_status_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SocialPost_organizationId_status_createdAt_idx" ON public."SocialPost" USING btree ("organizationId", status, "createdAt");


--
-- Name: SocialPost_platform_status_postedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SocialPost_platform_status_postedAt_idx" ON public."SocialPost" USING btree (platform, status, "postedAt");


--
-- Name: SocialPost_source_sourceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SocialPost_source_sourceId_idx" ON public."SocialPost" USING btree (source, "sourceId");


--
-- Name: SourceCredibilityUpdate_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceCredibilityUpdate_conclusionId_idx" ON public."SourceCredibilityUpdate" USING btree ("conclusionId");


--
-- Name: SourceCredibilityUpdate_organizationId_sourceId_conclusionI_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceCredibilityUpdate_organizationId_sourceId_conclusionI_idx" ON public."SourceCredibilityUpdate" USING btree ("organizationId", "sourceId", "conclusionId", kind, outcome);


--
-- Name: SourceCredibilityUpdate_organizationId_sourceId_observedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceCredibilityUpdate_organizationId_sourceId_observedAt_idx" ON public."SourceCredibilityUpdate" USING btree ("organizationId", "sourceId", "observedAt");


--
-- Name: SourceCredibilityUpdate_sourceId_observedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceCredibilityUpdate_sourceId_observedAt_idx" ON public."SourceCredibilityUpdate" USING btree ("sourceId", "observedAt");


--
-- Name: SourceStanding_organizationId_sourceId_observedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceStanding_organizationId_sourceId_observedAt_idx" ON public."SourceStanding" USING btree ("organizationId", "sourceId", "observedAt");


--
-- Name: SourceStanding_organizationId_status_observedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceStanding_organizationId_status_observedAt_idx" ON public."SourceStanding" USING btree ("organizationId", status, "observedAt");


--
-- Name: SourceStanding_sourceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceStanding_sourceId_idx" ON public."SourceStanding" USING btree ("sourceId");


--
-- Name: SourceTriageItem_conclusionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceTriageItem_conclusionId_idx" ON public."SourceTriageItem" USING btree ("conclusionId");


--
-- Name: SourceTriageItem_organizationId_decision_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceTriageItem_organizationId_decision_createdAt_idx" ON public."SourceTriageItem" USING btree ("organizationId", decision, "createdAt");


--
-- Name: SourceTriageItem_organizationId_trigger_decision_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceTriageItem_organizationId_trigger_decision_idx" ON public."SourceTriageItem" USING btree ("organizationId", trigger, decision);


--
-- Name: SourceTriageItem_sourceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceTriageItem_sourceId_idx" ON public."SourceTriageItem" USING btree ("sourceId");


--
-- Name: SourceTriageItem_standingId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceTriageItem_standingId_idx" ON public."SourceTriageItem" USING btree ("standingId");


--
-- Name: SourceTriageItem_verdictId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SourceTriageItem_verdictId_idx" ON public."SourceTriageItem" USING btree ("verdictId");


--
-- Name: Span_name_startedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Span_name_startedAt_idx" ON public."Span" USING btree (name, "startedAt");


--
-- Name: Span_startedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Span_startedAt_idx" ON public."Span" USING btree ("startedAt");


--
-- Name: Span_status_startedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Span_status_startedAt_idx" ON public."Span" USING btree (status, "startedAt");


--
-- Name: Span_traceId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Span_traceId_idx" ON public."Span" USING btree ("traceId");


--
-- Name: Subscriber_organizationId_email_scope_scopeKey_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Subscriber_organizationId_email_scope_scopeKey_key" ON public."Subscriber" USING btree ("organizationId", email, scope, "scopeKey");


--
-- Name: Subscriber_organizationId_status_cadence_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Subscriber_organizationId_status_cadence_idx" ON public."Subscriber" USING btree ("organizationId", status, cadence);


--
-- Name: Subscriber_scope_scopeKey_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Subscriber_scope_scopeKey_idx" ON public."Subscriber" USING btree (scope, "scopeKey");


--
-- Name: Subscriber_unsubscribeToken_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Subscriber_unsubscribeToken_key" ON public."Subscriber" USING btree ("unsubscribeToken");


--
-- Name: UploadChunk_uploadId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "UploadChunk_uploadId_idx" ON public."UploadChunk" USING btree ("uploadId");


--
-- Name: UploadChunk_uploadId_index_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "UploadChunk_uploadId_index_key" ON public."UploadChunk" USING btree ("uploadId", index);


--
-- Name: Upload_deletedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Upload_deletedAt_idx" ON public."Upload" USING btree ("deletedAt");


--
-- Name: Upload_founderId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Upload_founderId_idx" ON public."Upload" USING btree ("founderId");


--
-- Name: Upload_organizationId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Upload_organizationId_idx" ON public."Upload" USING btree ("organizationId");


--
-- Name: Upload_publishedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Upload_publishedAt_idx" ON public."Upload" USING btree ("publishedAt");


--
-- Name: Upload_slug_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Upload_slug_key" ON public."Upload" USING btree (slug);


--
-- Name: Upload_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Upload_status_idx" ON public."Upload" USING btree (status);


--
-- Name: Upload_visibility_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Upload_visibility_idx" ON public."Upload" USING btree (visibility);


--
-- Name: WatchedMarket_organizationId_status_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WatchedMarket_organizationId_status_createdAt_idx" ON public."WatchedMarket" USING btree ("organizationId", status, "createdAt");


--
-- Name: WatchedMarket_organizationId_url_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WatchedMarket_organizationId_url_key" ON public."WatchedMarket" USING btree ("organizationId", url);


--
-- Name: WatchedMarket_source_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WatchedMarket_source_status_idx" ON public."WatchedMarket" USING btree (source, status);


--
-- Name: algorithm_calibration_snapshot_algo_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX algorithm_calibration_snapshot_algo_at_idx ON public.algorithm_calibration_snapshot USING btree (algorithm_id, snapshot_at);


--
-- Name: algorithm_invocation_algorithm_invoked_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX algorithm_invocation_algorithm_invoked_idx ON public.algorithm_invocation USING btree (algorithm_id, invoked_at);


--
-- Name: algorithm_invocation_org_invoked_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX algorithm_invocation_org_invoked_idx ON public.algorithm_invocation USING btree (organization_id, invoked_at);


--
-- Name: algorithm_triage_recommendation_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX algorithm_triage_recommendation_status_idx ON public.algorithm_triage_recommendation USING btree (organization_id, status);


--
-- Name: bet_resolution_resolved_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bet_resolution_resolved_idx ON public.bet_resolution USING btree (resolved_at);


--
-- Name: bet_resolution_spec_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bet_resolution_spec_idx ON public.bet_resolution USING btree (bet_spec_id);


--
-- Name: bet_spec_horizon_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bet_spec_horizon_idx ON public.bet_spec USING btree (horizon_at);


--
-- Name: bet_spec_memo_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bet_spec_memo_idx ON public.bet_spec USING btree (created_by_memo_id);


--
-- Name: bet_spec_org_kind_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bet_spec_org_kind_status_idx ON public.bet_spec USING btree (organization_id, kind, status);


--
-- Name: contradiction_dispute_method_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_dispute_method_at_idx ON public.contradiction_dispute USING btree (detection_method, created_at);


--
-- Name: contradiction_lifecycle_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_lifecycle_status_idx ON public.contradiction_lifecycle USING btree (current_status, last_transition_at);


--
-- Name: contradiction_lifecycle_target_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_lifecycle_target_idx ON public.contradiction_lifecycle USING btree (contradiction_id);


--
-- Name: contradiction_result_method_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_result_method_at_idx ON public.contradiction_result USING btree (detection_method, detected_at);


--
-- Name: contradiction_result_pair_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_result_pair_idx ON public.contradiction_result USING btree (principle_a_id, principle_b_id);


--
-- Name: contradiction_test_task_pair_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_test_task_pair_idx ON public.contradiction_test_task USING btree (pair_key, enqueued_at);


--
-- Name: contradiction_test_task_status_priority_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contradiction_test_task_status_priority_idx ON public.contradiction_test_task USING btree (status, priority, enqueued_at);


--
-- Name: dialectic_contradiction_flag_kind_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dialectic_contradiction_flag_kind_idx ON public.dialectic_contradiction_flag USING btree (flag_kind);


--
-- Name: dialectic_contradiction_flag_utterance_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dialectic_contradiction_flag_utterance_idx ON public.dialectic_contradiction_flag USING btree (utterance_id);


--
-- Name: dialectic_session_org_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dialectic_session_org_status_idx ON public.dialectic_session USING btree (organization_id, status);


--
-- Name: dialectic_session_started_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dialectic_session_started_idx ON public.dialectic_session USING btree (started_at);


--
-- Name: dialectic_utterance_session_start_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dialectic_utterance_session_start_idx ON public.dialectic_utterance USING btree (session_id, start_time);


--
-- Name: dialectic_utterance_speaker_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dialectic_utterance_speaker_idx ON public.dialectic_utterance USING btree (speaker_id);


--
-- Name: graph_edge_reasoning_triple_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX graph_edge_reasoning_triple_idx ON public.graph_edge_reasoning USING btree (organization_id, src, dst, kind);


--
-- Name: graph_snapshot_org_snapat_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX graph_snapshot_org_snapat_idx ON public.graph_snapshot USING btree (organization_id, snapshot_at);


--
-- Name: investment_memo_org_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX investment_memo_org_created_idx ON public.investment_memo USING btree (organization_id, created_at);


--
-- Name: investment_memo_org_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX investment_memo_org_status_idx ON public.investment_memo USING btree (organization_id, status);


--
-- Name: investment_memo_slug_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX investment_memo_slug_idx ON public.investment_memo USING btree (slug);


--
-- Name: ix_adversarial_challenge_cluster_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_adversarial_challenge_cluster_fingerprint ON public.adversarial_challenge USING btree (cluster_fingerprint);


--
-- Name: ix_adversarial_challenge_conclusion_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_adversarial_challenge_conclusion_id ON public.adversarial_challenge USING btree (conclusion_id);


--
-- Name: ix_algorithm_calibration_snapshot_algorithm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_calibration_snapshot_algorithm_id ON public.algorithm_calibration_snapshot USING btree (algorithm_id);


--
-- Name: ix_algorithm_calibration_snapshot_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_calibration_snapshot_organization_id ON public.algorithm_calibration_snapshot USING btree (organization_id);


--
-- Name: ix_algorithm_input_observation_input_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_input_observation_input_name ON public.algorithm_input_observation USING btree (input_name);


--
-- Name: ix_algorithm_input_observation_invocation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_input_observation_invocation_id ON public.algorithm_input_observation USING btree (invocation_id);


--
-- Name: ix_algorithm_input_observation_source_artifact_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_input_observation_source_artifact_id ON public.algorithm_input_observation USING btree (source_artifact_id);


--
-- Name: ix_algorithm_invocation_algorithm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_invocation_algorithm_id ON public.algorithm_invocation USING btree (algorithm_id);


--
-- Name: ix_algorithm_invocation_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_invocation_organization_id ON public.algorithm_invocation USING btree (organization_id);


--
-- Name: ix_algorithm_triage_recommendation_algorithm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_triage_recommendation_algorithm_id ON public.algorithm_triage_recommendation USING btree (algorithm_id);


--
-- Name: ix_algorithm_triage_recommendation_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_triage_recommendation_organization_id ON public.algorithm_triage_recommendation USING btree (organization_id);


--
-- Name: ix_algorithm_triage_recommendation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_algorithm_triage_recommendation_status ON public.algorithm_triage_recommendation USING btree (status);


--
-- Name: ix_bet_resolution_bet_spec_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bet_resolution_bet_spec_id ON public.bet_resolution USING btree (bet_spec_id);


--
-- Name: ix_bet_spec_created_by_memo_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bet_spec_created_by_memo_id ON public.bet_spec USING btree (created_by_memo_id);


--
-- Name: ix_bet_spec_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bet_spec_kind ON public.bet_spec USING btree (kind);


--
-- Name: ix_bet_spec_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bet_spec_organization_id ON public.bet_spec USING btree (organization_id);


--
-- Name: ix_bet_spec_originating_algorithm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bet_spec_originating_algorithm_id ON public.bet_spec USING btree (originating_algorithm_id);


--
-- Name: ix_bet_spec_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bet_spec_status ON public.bet_spec USING btree (status);


--
-- Name: ix_cascade_edge_dst; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cascade_edge_dst ON public.cascade_edge USING btree (dst);


--
-- Name: ix_cascade_edge_relation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cascade_edge_relation ON public.cascade_edge USING btree (relation);


--
-- Name: ix_cascade_edge_retracted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cascade_edge_retracted_at ON public.cascade_edge USING btree (retracted_at);


--
-- Name: ix_cascade_edge_src; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cascade_edge_src ON public.cascade_edge USING btree (src);


--
-- Name: ix_cascade_node_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cascade_node_kind ON public.cascade_node USING btree (kind);


--
-- Name: ix_chunk_artifact_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chunk_artifact_id ON public.chunk USING btree (artifact_id);


--
-- Name: ix_citation_firm_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_firm_claim_id ON public.citation USING btree (firm_claim_id);


--
-- Name: ix_citation_voice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_voice_id ON public.citation USING btree (voice_id);


--
-- Name: ix_cluster_reindex_proposal_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cluster_reindex_proposal_status ON public.cluster_reindex_proposal USING btree (status);


--
-- Name: ix_coherence_pair_claim_a_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_coherence_pair_claim_a_id ON public.coherence_pair USING btree (claim_a_id);


--
-- Name: ix_coherence_pair_claim_b_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_coherence_pair_claim_b_id ON public.coherence_pair USING btree (claim_b_id);


--
-- Name: ix_coherence_result_cache_claim_a_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_coherence_result_cache_claim_a_id ON public.coherence_result_cache USING btree (claim_a_id);


--
-- Name: ix_coherence_result_cache_claim_b_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_coherence_result_cache_claim_b_id ON public.coherence_result_cache USING btree (claim_b_id);


--
-- Name: ix_contradiction_dispute_contradiction_result_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_dispute_contradiction_result_id ON public.contradiction_dispute USING btree (contradiction_result_id);


--
-- Name: ix_contradiction_dispute_detection_method; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_dispute_detection_method ON public.contradiction_dispute USING btree (detection_method);


--
-- Name: ix_contradiction_lifecycle_contradiction_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_lifecycle_contradiction_id ON public.contradiction_lifecycle USING btree (contradiction_id);


--
-- Name: ix_contradiction_lifecycle_current_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_lifecycle_current_status ON public.contradiction_lifecycle USING btree (current_status);


--
-- Name: ix_contradiction_result_detection_method; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_result_detection_method ON public.contradiction_result USING btree (detection_method);


--
-- Name: ix_contradiction_result_principle_a_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_result_principle_a_id ON public.contradiction_result USING btree (principle_a_id);


--
-- Name: ix_contradiction_result_principle_b_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_result_principle_b_id ON public.contradiction_result USING btree (principle_b_id);


--
-- Name: ix_contradiction_result_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_result_status ON public.contradiction_result USING btree (status);


--
-- Name: ix_contradiction_result_verdict; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_result_verdict ON public.contradiction_result USING btree (verdict);


--
-- Name: ix_contradiction_test_task_pair_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_test_task_pair_key ON public.contradiction_test_task USING btree (pair_key);


--
-- Name: ix_contradiction_test_task_principle_a_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_test_task_principle_a_id ON public.contradiction_test_task USING btree (principle_a_id);


--
-- Name: ix_contradiction_test_task_principle_b_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_test_task_principle_b_id ON public.contradiction_test_task USING btree (principle_b_id);


--
-- Name: ix_contradiction_test_task_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_test_task_priority ON public.contradiction_test_task USING btree (priority);


--
-- Name: ix_contradiction_test_task_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contradiction_test_task_status ON public.contradiction_test_task USING btree (status);


--
-- Name: ix_cut_outcome_cut_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cut_outcome_cut_id ON public.cut_outcome USING btree (cut_id);


--
-- Name: ix_cut_outcome_outcome_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cut_outcome_outcome_id ON public.cut_outcome USING btree (outcome_id);


--
-- Name: ix_dialectic_contradiction_flag_utterance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dialectic_contradiction_flag_utterance_id ON public.dialectic_contradiction_flag USING btree (utterance_id);


--
-- Name: ix_dialectic_session_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dialectic_session_organization_id ON public.dialectic_session USING btree (organization_id);


--
-- Name: ix_dialectic_utterance_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dialectic_utterance_session_id ON public.dialectic_utterance USING btree (session_id);


--
-- Name: ix_dialectic_utterance_speaker_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dialectic_utterance_speaker_id ON public.dialectic_utterance USING btree (speaker_id);


--
-- Name: ix_embedding_model_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_model_name ON public.embedding USING btree (model_name);


--
-- Name: ix_embedding_model_version_effective_from; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_model_version_effective_from ON public.embedding_model_version USING btree (effective_from);


--
-- Name: ix_embedding_ref_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_ref_claim_id ON public.embedding USING btree (ref_claim_id);


--
-- Name: ix_embedding_retry_model_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_retry_model_name ON public.embedding_retry USING btree (model_name);


--
-- Name: ix_embedding_retry_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_retry_source_id ON public.embedding_retry USING btree (source_id);


--
-- Name: ix_embedding_retry_source_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_retry_source_kind ON public.embedding_retry USING btree (source_kind);


--
-- Name: ix_embedding_retry_text_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_retry_text_sha256 ON public.embedding_retry USING btree (text_sha256);


--
-- Name: ix_embedding_text_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_embedding_text_sha256 ON public.embedding USING btree (text_sha256);


--
-- Name: ix_entity_canonical_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_canonical_key ON public.entity USING btree (canonical_key);


--
-- Name: ix_graph_edge_reasoning_dst; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_graph_edge_reasoning_dst ON public.graph_edge_reasoning USING btree (dst);


--
-- Name: ix_graph_edge_reasoning_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_graph_edge_reasoning_kind ON public.graph_edge_reasoning USING btree (kind);


--
-- Name: ix_graph_edge_reasoning_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_graph_edge_reasoning_organization_id ON public.graph_edge_reasoning USING btree (organization_id);


--
-- Name: ix_graph_edge_reasoning_src; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_graph_edge_reasoning_src ON public.graph_edge_reasoning USING btree (src);


--
-- Name: ix_graph_snapshot_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_graph_snapshot_organization_id ON public.graph_snapshot USING btree (organization_id);


--
-- Name: ix_graph_snapshot_snapshot_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_graph_snapshot_snapshot_at ON public.graph_snapshot USING btree (snapshot_at);


--
-- Name: ix_investment_memo_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_investment_memo_organization_id ON public.investment_memo USING btree (organization_id);


--
-- Name: ix_investment_memo_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_investment_memo_slug ON public.investment_memo USING btree (slug);


--
-- Name: ix_investment_memo_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_investment_memo_status ON public.investment_memo USING btree (status);


--
-- Name: ix_investment_memo_synthesizer_result_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_investment_memo_synthesizer_result_id ON public.investment_memo USING btree (synthesizer_result_id);


--
-- Name: ix_ledger_entry_method_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ledger_entry_method_id ON public.ledger_entry USING btree (method_id);


--
-- Name: ix_ledger_entry_prev_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ledger_entry_prev_hash ON public.ledger_entry USING btree (prev_hash);


--
-- Name: ix_ledger_entry_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ledger_entry_timestamp ON public.ledger_entry USING btree ("timestamp");


--
-- Name: ix_logical_algorithm_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logical_algorithm_name ON public.logical_algorithm USING btree (name);


--
-- Name: ix_logical_algorithm_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logical_algorithm_organization_id ON public.logical_algorithm USING btree (organization_id);


--
-- Name: ix_logical_algorithm_provenance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logical_algorithm_provenance ON public.logical_algorithm USING btree (provenance);


--
-- Name: ix_logical_algorithm_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logical_algorithm_status ON public.logical_algorithm USING btree (status);


--
-- Name: ix_memo_dispatch_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memo_dispatch_agent_id ON public.memo_dispatch USING btree (agent_id);


--
-- Name: ix_memo_dispatch_memo_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memo_dispatch_memo_id ON public.memo_dispatch USING btree (memo_id);


--
-- Name: ix_memo_dispatch_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memo_dispatch_organization_id ON public.memo_dispatch USING btree (organization_id);


--
-- Name: ix_memo_dispatch_outcome_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memo_dispatch_outcome_action ON public.memo_dispatch USING btree (outcome_action);


--
-- Name: ix_method_invocation_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_method_invocation_correlation_id ON public.method_invocation USING btree (correlation_id);


--
-- Name: ix_method_invocation_method_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_method_invocation_method_id ON public.method_invocation USING btree (method_id);


--
-- Name: ix_method_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_method_status ON public.method USING btree (status);


--
-- Name: ix_object_policy_binding_object_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_object_policy_binding_object_id ON public.object_policy_binding USING btree (object_id);


--
-- Name: ix_object_policy_binding_policy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_object_policy_binding_policy_id ON public.object_policy_binding USING btree (policy_id);


--
-- Name: ix_portfolio_agent_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_agent_kind ON public.portfolio_agent USING btree (kind);


--
-- Name: ix_portfolio_agent_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_agent_organization_id ON public.portfolio_agent USING btree (organization_id);


--
-- Name: ix_portfolio_agent_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_agent_status ON public.portfolio_agent USING btree (status);


--
-- Name: ix_prediction_resolution_predictive_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_prediction_resolution_predictive_claim_id ON public.prediction_resolution USING btree (predictive_claim_id);


--
-- Name: ix_predictive_claim_artifact_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_predictive_claim_artifact_id ON public.predictive_claim USING btree (artifact_id);


--
-- Name: ix_predictive_claim_author_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_predictive_claim_author_key ON public.predictive_claim USING btree (author_key);


--
-- Name: ix_predictive_claim_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_predictive_claim_status ON public.predictive_claim USING btree (status);


--
-- Name: ix_principle_cluster_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_principle_cluster_cluster_id ON public.principle_cluster USING btree (cluster_id);


--
-- Name: ix_quantitative_formalisation_principle_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quantitative_formalisation_principle_id ON public.quantitative_formalisation USING btree (principle_id);


--
-- Name: ix_quantitative_formalisation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quantitative_formalisation_status ON public.quantitative_formalisation USING btree (status);


--
-- Name: ix_quantitative_test_result_formalisation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quantitative_test_result_formalisation_id ON public.quantitative_test_result USING btree (formalisation_id);


--
-- Name: ix_quantitative_test_result_principle_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quantitative_test_result_principle_id ON public.quantitative_test_result USING btree (principle_id);


--
-- Name: ix_quantitative_test_result_run_stamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quantitative_test_result_run_stamp ON public.quantitative_test_result USING btree (run_stamp);


--
-- Name: ix_quantitative_test_result_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quantitative_test_result_status ON public.quantitative_test_result USING btree (status);


--
-- Name: ix_rebuttal_finding_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rebuttal_finding_id ON public.rebuttal USING btree (finding_id);


--
-- Name: ix_rebuttal_report_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rebuttal_report_id ON public.rebuttal USING btree (report_id);


--
-- Name: ix_revalidation_object_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_revalidation_object_id ON public.revalidation USING btree (object_id);


--
-- Name: ix_review_item_claim_a_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_review_item_claim_a_id ON public.review_item USING btree (claim_a_id);


--
-- Name: ix_review_item_claim_b_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_review_item_claim_b_id ON public.review_item USING btree (claim_b_id);


--
-- Name: ix_review_report_conclusion_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_review_report_conclusion_id ON public.review_report USING btree (conclusion_id);


--
-- Name: ix_rigor_submission_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rigor_submission_author_id ON public.rigor_submission USING btree (author_id);


--
-- Name: ix_rigor_submission_intended_venue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rigor_submission_intended_venue ON public.rigor_submission USING btree (intended_venue);


--
-- Name: ix_synthesizer_memo_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_memo_organization_id ON public.synthesizer_memo USING btree (organization_id);


--
-- Name: ix_synthesizer_memo_synthesizer_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_memo_synthesizer_version ON public.synthesizer_memo USING btree (synthesizer_version);


--
-- Name: ix_synthesizer_task_current_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_task_current_event_id ON public.synthesizer_task USING btree (current_event_id);


--
-- Name: ix_synthesizer_task_invocation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_task_invocation_id ON public.synthesizer_task USING btree (invocation_id);


--
-- Name: ix_synthesizer_task_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_task_organization_id ON public.synthesizer_task USING btree (organization_id);


--
-- Name: ix_synthesizer_task_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_task_status ON public.synthesizer_task USING btree (status);


--
-- Name: ix_synthesizer_task_trigger; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_synthesizer_task_trigger ON public.synthesizer_task USING btree (trigger);


--
-- Name: ix_topic_membership_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_topic_membership_cluster_id ON public.topic_membership USING btree (cluster_id);


--
-- Name: ix_transfer_study_method_ref_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_transfer_study_method_ref_name ON public.transfer_study USING btree (method_ref_name);


--
-- Name: ix_transfer_study_method_ref_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_transfer_study_method_ref_version ON public.transfer_study USING btree (method_ref_version);


--
-- Name: ix_voice_canonical_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_voice_canonical_key ON public.voice USING btree (canonical_key);


--
-- Name: ix_voice_phase_voice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_voice_phase_voice_id ON public.voice_phase USING btree (voice_id);


--
-- Name: memo_dispatch_agent_outcome_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX memo_dispatch_agent_outcome_idx ON public.memo_dispatch USING btree (agent_id, outcome_action);


--
-- Name: memo_dispatch_memo_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX memo_dispatch_memo_idx ON public.memo_dispatch USING btree (memo_id);


--
-- Name: memo_dispatch_org_dispatched_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX memo_dispatch_org_dispatched_idx ON public.memo_dispatch USING btree (organization_id, dispatched_at);


--
-- Name: portfolio_agent_org_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX portfolio_agent_org_status_idx ON public.portfolio_agent USING btree (organization_id, status);


--
-- Name: principle_cluster_cluster_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX principle_cluster_cluster_idx ON public.principle_cluster USING btree (cluster_id, assigned_at);


--
-- Name: synthesizer_memo_org_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX synthesizer_memo_org_created_idx ON public.synthesizer_memo USING btree (organization_id, created_at);


--
-- Name: synthesizer_task_org_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX synthesizer_task_org_status_idx ON public.synthesizer_task USING btree (organization_id, status);


--
-- Name: synthesizer_task_status_enqueued_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX synthesizer_task_status_enqueued_idx ON public.synthesizer_task USING btree (status, enqueued_at);


--
-- Name: ix_realtime_subscription_entity; Type: INDEX; Schema: realtime; Owner: -
--

CREATE INDEX ix_realtime_subscription_entity ON realtime.subscription USING btree (entity);


--
-- Name: messages_inserted_at_topic_index; Type: INDEX; Schema: realtime; Owner: -
--

CREATE INDEX messages_inserted_at_topic_index ON ONLY realtime.messages USING btree (inserted_at DESC, topic) WHERE ((extension = 'broadcast'::text) AND (private IS TRUE));


--
-- Name: subscription_subscription_id_entity_filters_action_filter_key; Type: INDEX; Schema: realtime; Owner: -
--

CREATE UNIQUE INDEX subscription_subscription_id_entity_filters_action_filter_key ON realtime.subscription USING btree (subscription_id, entity, filters, action_filter);


--
-- Name: bname; Type: INDEX; Schema: storage; Owner: -
--

CREATE UNIQUE INDEX bname ON storage.buckets USING btree (name);


--
-- Name: bucketid_objname; Type: INDEX; Schema: storage; Owner: -
--

CREATE UNIQUE INDEX bucketid_objname ON storage.objects USING btree (bucket_id, name);


--
-- Name: buckets_analytics_unique_name_idx; Type: INDEX; Schema: storage; Owner: -
--

CREATE UNIQUE INDEX buckets_analytics_unique_name_idx ON storage.buckets_analytics USING btree (name) WHERE (deleted_at IS NULL);


--
-- Name: idx_multipart_uploads_list; Type: INDEX; Schema: storage; Owner: -
--

CREATE INDEX idx_multipart_uploads_list ON storage.s3_multipart_uploads USING btree (bucket_id, key, created_at);


--
-- Name: idx_objects_bucket_id_name; Type: INDEX; Schema: storage; Owner: -
--

CREATE INDEX idx_objects_bucket_id_name ON storage.objects USING btree (bucket_id, name COLLATE "C");


--
-- Name: idx_objects_bucket_id_name_lower; Type: INDEX; Schema: storage; Owner: -
--

CREATE INDEX idx_objects_bucket_id_name_lower ON storage.objects USING btree (bucket_id, lower(name) COLLATE "C");


--
-- Name: name_prefix_search; Type: INDEX; Schema: storage; Owner: -
--

CREATE INDEX name_prefix_search ON storage.objects USING btree (name text_pattern_ops);


--
-- Name: vector_indexes_name_bucket_id_idx; Type: INDEX; Schema: storage; Owner: -
--

CREATE UNIQUE INDEX vector_indexes_name_bucket_id_idx ON storage.vector_indexes USING btree (name, bucket_id);


--
-- Name: subscription tr_check_filters; Type: TRIGGER; Schema: realtime; Owner: -
--

CREATE TRIGGER tr_check_filters BEFORE INSERT OR UPDATE ON realtime.subscription FOR EACH ROW EXECUTE FUNCTION realtime.subscription_check_filters();


--
-- Name: buckets enforce_bucket_name_length_trigger; Type: TRIGGER; Schema: storage; Owner: -
--

CREATE TRIGGER enforce_bucket_name_length_trigger BEFORE INSERT OR UPDATE OF name ON storage.buckets FOR EACH ROW EXECUTE FUNCTION storage.enforce_bucket_name_length();


--
-- Name: buckets protect_buckets_delete; Type: TRIGGER; Schema: storage; Owner: -
--

CREATE TRIGGER protect_buckets_delete BEFORE DELETE ON storage.buckets FOR EACH STATEMENT EXECUTE FUNCTION storage.protect_delete();


--
-- Name: objects protect_objects_delete; Type: TRIGGER; Schema: storage; Owner: -
--

CREATE TRIGGER protect_objects_delete BEFORE DELETE ON storage.objects FOR EACH STATEMENT EXECUTE FUNCTION storage.protect_delete();


--
-- Name: objects update_objects_updated_at; Type: TRIGGER; Schema: storage; Owner: -
--

CREATE TRIGGER update_objects_updated_at BEFORE UPDATE ON storage.objects FOR EACH ROW EXECUTE FUNCTION storage.update_updated_at_column();


--
-- Name: identities identities_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.identities
    ADD CONSTRAINT identities_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: mfa_amr_claims mfa_amr_claims_session_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_amr_claims
    ADD CONSTRAINT mfa_amr_claims_session_id_fkey FOREIGN KEY (session_id) REFERENCES auth.sessions(id) ON DELETE CASCADE;


--
-- Name: mfa_challenges mfa_challenges_auth_factor_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_challenges
    ADD CONSTRAINT mfa_challenges_auth_factor_id_fkey FOREIGN KEY (factor_id) REFERENCES auth.mfa_factors(id) ON DELETE CASCADE;


--
-- Name: mfa_factors mfa_factors_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.mfa_factors
    ADD CONSTRAINT mfa_factors_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: oauth_authorizations oauth_authorizations_client_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_authorizations
    ADD CONSTRAINT oauth_authorizations_client_id_fkey FOREIGN KEY (client_id) REFERENCES auth.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: oauth_authorizations oauth_authorizations_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_authorizations
    ADD CONSTRAINT oauth_authorizations_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: oauth_consents oauth_consents_client_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_consents
    ADD CONSTRAINT oauth_consents_client_id_fkey FOREIGN KEY (client_id) REFERENCES auth.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: oauth_consents oauth_consents_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.oauth_consents
    ADD CONSTRAINT oauth_consents_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: one_time_tokens one_time_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.one_time_tokens
    ADD CONSTRAINT one_time_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_session_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens
    ADD CONSTRAINT refresh_tokens_session_id_fkey FOREIGN KEY (session_id) REFERENCES auth.sessions(id) ON DELETE CASCADE;


--
-- Name: saml_providers saml_providers_sso_provider_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.saml_providers
    ADD CONSTRAINT saml_providers_sso_provider_id_fkey FOREIGN KEY (sso_provider_id) REFERENCES auth.sso_providers(id) ON DELETE CASCADE;


--
-- Name: saml_relay_states saml_relay_states_flow_state_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.saml_relay_states
    ADD CONSTRAINT saml_relay_states_flow_state_id_fkey FOREIGN KEY (flow_state_id) REFERENCES auth.flow_state(id) ON DELETE CASCADE;


--
-- Name: saml_relay_states saml_relay_states_sso_provider_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.saml_relay_states
    ADD CONSTRAINT saml_relay_states_sso_provider_id_fkey FOREIGN KEY (sso_provider_id) REFERENCES auth.sso_providers(id) ON DELETE CASCADE;


--
-- Name: sessions sessions_oauth_client_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.sessions
    ADD CONSTRAINT sessions_oauth_client_id_fkey FOREIGN KEY (oauth_client_id) REFERENCES auth.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: sessions sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: sso_domains sso_domains_sso_provider_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.sso_domains
    ADD CONSTRAINT sso_domains_sso_provider_id_fkey FOREIGN KEY (sso_provider_id) REFERENCES auth.sso_providers(id) ON DELETE CASCADE;


--
-- Name: webauthn_challenges webauthn_challenges_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.webauthn_challenges
    ADD CONSTRAINT webauthn_challenges_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: webauthn_credentials webauthn_credentials_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.webauthn_credentials
    ADD CONSTRAINT webauthn_credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: Addendum Addendum_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Addendum"
    ADD CONSTRAINT "Addendum_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: AnchorRevision AnchorRevision_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AnchorRevision"
    ADD CONSTRAINT "AnchorRevision_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ApiKey ApiKey_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ApiKey"
    ADD CONSTRAINT "ApiKey_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ApiKey ApiKey_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ApiKey"
    ADD CONSTRAINT "ApiKey_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: AttentionAction AttentionAction_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AttentionAction"
    ADD CONSTRAINT "AttentionAction_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: AttentionAction AttentionAction_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AttentionAction"
    ADD CONSTRAINT "AttentionAction_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: AuditEvent AuditEvent_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AuditEvent"
    ADD CONSTRAINT "AuditEvent_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: AuditEvent AuditEvent_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AuditEvent"
    ADD CONSTRAINT "AuditEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: AuditEvent AuditEvent_uploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."AuditEvent"
    ADD CONSTRAINT "AuditEvent_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: CalibrationModel CalibrationModel_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CalibrationModel"
    ADD CONSTRAINT "CalibrationModel_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: CitationVerdict CitationVerdict_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CitationVerdict"
    ADD CONSTRAINT "CitationVerdict_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ConclusionDeletionRequest ConclusionDeletionRequest_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionDeletionRequest"
    ADD CONSTRAINT "ConclusionDeletionRequest_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ConclusionDeletionRequest ConclusionDeletionRequest_requesterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionDeletionRequest"
    ADD CONSTRAINT "ConclusionDeletionRequest_requesterId_fkey" FOREIGN KEY ("requesterId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ConclusionMethod ConclusionMethod_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionMethod"
    ADD CONSTRAINT "ConclusionMethod_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ConclusionMethod ConclusionMethod_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionMethod"
    ADD CONSTRAINT "ConclusionMethod_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ConclusionSource ConclusionSource_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionSource"
    ADD CONSTRAINT "ConclusionSource_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ConclusionSource ConclusionSource_uploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ConclusionSource"
    ADD CONSTRAINT "ConclusionSource_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Conclusion Conclusion_attributedFounderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Conclusion"
    ADD CONSTRAINT "Conclusion_attributedFounderId_fkey" FOREIGN KEY ("attributedFounderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Conclusion Conclusion_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Conclusion"
    ADD CONSTRAINT "Conclusion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: Contradiction Contradiction_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Contradiction"
    ADD CONSTRAINT "Contradiction_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: Contradiction Contradiction_resolvedById_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Contradiction"
    ADD CONSTRAINT "Contradiction_resolvedById_fkey" FOREIGN KEY ("resolvedById") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Contradiction Contradiction_sourceUploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Contradiction"
    ADD CONSTRAINT "Contradiction_sourceUploadId_fkey" FOREIGN KEY ("sourceUploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: CritiqueBountyPayout CritiqueBountyPayout_confirmedById_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueBountyPayout"
    ADD CONSTRAINT "CritiqueBountyPayout_confirmedById_fkey" FOREIGN KEY ("confirmedById") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: CritiqueBountyPayout CritiqueBountyPayout_critiqueSubmissionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueBountyPayout"
    ADD CONSTRAINT "CritiqueBountyPayout_critiqueSubmissionId_fkey" FOREIGN KEY ("critiqueSubmissionId") REFERENCES public."CritiqueSubmission"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: CritiqueBountyPayout CritiqueBountyPayout_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueBountyPayout"
    ADD CONSTRAINT "CritiqueBountyPayout_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: CritiqueSubmission CritiqueSubmission_decidedById_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueSubmission"
    ADD CONSTRAINT "CritiqueSubmission_decidedById_fkey" FOREIGN KEY ("decidedById") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: CritiqueSubmission CritiqueSubmission_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CritiqueSubmission"
    ADD CONSTRAINT "CritiqueSubmission_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: CurrentEvent CurrentEvent_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CurrentEvent"
    ADD CONSTRAINT "CurrentEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: DashboardDismissal DashboardDismissal_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DashboardDismissal"
    ADD CONSTRAINT "DashboardDismissal_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: DashboardDismissal DashboardDismissal_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DashboardDismissal"
    ADD CONSTRAINT "DashboardDismissal_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: DeletionRequest DeletionRequest_requesterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DeletionRequest"
    ADD CONSTRAINT "DeletionRequest_requesterId_fkey" FOREIGN KEY ("requesterId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: DeletionRequest DeletionRequest_uploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DeletionRequest"
    ADD CONSTRAINT "DeletionRequest_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: DomainBoundVerdict DomainBoundVerdict_anchorRevisionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DomainBoundVerdict"
    ADD CONSTRAINT "DomainBoundVerdict_anchorRevisionId_fkey" FOREIGN KEY ("anchorRevisionId") REFERENCES public."AnchorRevision"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: DomainBoundVerdict DomainBoundVerdict_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DomainBoundVerdict"
    ADD CONSTRAINT "DomainBoundVerdict_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: DomainBoundVerdict DomainBoundVerdict_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DomainBoundVerdict"
    ADD CONSTRAINT "DomainBoundVerdict_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: DriftEvent DriftEvent_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."DriftEvent"
    ADD CONSTRAINT "DriftEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: EventOpinion EventOpinion_eventId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EventOpinion"
    ADD CONSTRAINT "EventOpinion_eventId_fkey" FOREIGN KEY ("eventId") REFERENCES public."CurrentEvent"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: EventOpinion EventOpinion_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."EventOpinion"
    ADD CONSTRAINT "EventOpinion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: FollowUpMessage FollowUpMessage_sessionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."FollowUpMessage"
    ADD CONSTRAINT "FollowUpMessage_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES public."FollowUpSession"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: FollowUpSession FollowUpSession_opinionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."FollowUpSession"
    ADD CONSTRAINT "FollowUpSession_opinionId_fkey" FOREIGN KEY ("opinionId") REFERENCES public."EventOpinion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastBet ForecastBet_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastBet"
    ADD CONSTRAINT "ForecastBet_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ForecastBet ForecastBet_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastBet"
    ADD CONSTRAINT "ForecastBet_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ForecastCitation ForecastCitation_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastCitation"
    ADD CONSTRAINT "ForecastCitation_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastFollowUpMessage ForecastFollowUpMessage_sessionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastFollowUpMessage"
    ADD CONSTRAINT "ForecastFollowUpMessage_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES public."ForecastFollowUpSession"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastFollowUpSession ForecastFollowUpSession_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastFollowUpSession"
    ADD CONSTRAINT "ForecastFollowUpSession_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastMarket ForecastMarket_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastMarket"
    ADD CONSTRAINT "ForecastMarket_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ForecastPortfolioState ForecastPortfolioState_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastPortfolioState"
    ADD CONSTRAINT "ForecastPortfolioState_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ForecastPrediction ForecastPrediction_marketId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastPrediction"
    ADD CONSTRAINT "ForecastPrediction_marketId_fkey" FOREIGN KEY ("marketId") REFERENCES public."ForecastMarket"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastPrediction ForecastPrediction_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastPrediction"
    ADD CONSTRAINT "ForecastPrediction_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ForecastResolution ForecastResolution_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastResolution"
    ADD CONSTRAINT "ForecastResolution_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastTrace ForecastTrace_marketId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastTrace"
    ADD CONSTRAINT "ForecastTrace_marketId_fkey" FOREIGN KEY ("marketId") REFERENCES public."ForecastMarket"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ForecastTrace ForecastTrace_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastTrace"
    ADD CONSTRAINT "ForecastTrace_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ForecastTrace ForecastTrace_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ForecastTrace"
    ADD CONSTRAINT "ForecastTrace_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Founder Founder_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Founder"
    ADD CONSTRAINT "Founder_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: MethodTrackRecord MethodTrackRecord_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodTrackRecord"
    ADD CONSTRAINT "MethodTrackRecord_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: MethodVersion MethodVersion_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodVersion"
    ADD CONSTRAINT "MethodVersion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: MethodologyProfile MethodologyProfile_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyProfile"
    ADD CONSTRAINT "MethodologyProfile_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: MethodologyProfile MethodologyProfile_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyProfile"
    ADD CONSTRAINT "MethodologyProfile_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: MethodologyProfile MethodologyProfile_uploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyProfile"
    ADD CONSTRAINT "MethodologyProfile_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: MethodologyQualityScore MethodologyQualityScore_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyQualityScore"
    ADD CONSTRAINT "MethodologyQualityScore_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: MethodologyQualityScore MethodologyQualityScore_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."MethodologyQualityScore"
    ADD CONSTRAINT "MethodologyQualityScore_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: OpenQuestion OpenQuestion_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OpenQuestion"
    ADD CONSTRAINT "OpenQuestion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: OpenQuestion OpenQuestion_sourceUploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OpenQuestion"
    ADD CONSTRAINT "OpenQuestion_sourceUploadId_fkey" FOREIGN KEY ("sourceUploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: OperatorState OperatorState_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OperatorState"
    ADD CONSTRAINT "OperatorState_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: OpinionCitation OpinionCitation_opinionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OpinionCitation"
    ADD CONSTRAINT "OpinionCitation_opinionId_fkey" FOREIGN KEY ("opinionId") REFERENCES public."EventOpinion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Principle Principle_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Principle"
    ADD CONSTRAINT "Principle_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: PublicReply PublicReply_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicReply"
    ADD CONSTRAINT "PublicReply_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: PublicReply PublicReply_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicReply"
    ADD CONSTRAINT "PublicReply_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: PublicReply PublicReply_publicResponseId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicReply"
    ADD CONSTRAINT "PublicReply_publicResponseId_fkey" FOREIGN KEY ("publicResponseId") REFERENCES public."PublicResponse"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: PublicResponse PublicResponse_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicResponse"
    ADD CONSTRAINT "PublicResponse_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: PublicResponse PublicResponse_publishedConclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicResponse"
    ADD CONSTRAINT "PublicResponse_publishedConclusionId_fkey" FOREIGN KEY ("publishedConclusionId") REFERENCES public."PublishedConclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: PublicationReview PublicationReview_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicationReview"
    ADD CONSTRAINT "PublicationReview_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: PublicationReview PublicationReview_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicationReview"
    ADD CONSTRAINT "PublicationReview_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: PublicationReview PublicationReview_reviewerFounderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicationReview"
    ADD CONSTRAINT "PublicationReview_reviewerFounderId_fkey" FOREIGN KEY ("reviewerFounderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: PublicationSignature PublicationSignature_publishedConclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublicationSignature"
    ADD CONSTRAINT "PublicationSignature_publishedConclusionId_fkey" FOREIGN KEY ("publishedConclusionId") REFERENCES public."PublishedConclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: PublishedConclusion PublishedConclusion_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PublishedConclusion"
    ADD CONSTRAINT "PublishedConclusion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: RecalibrationOverride RecalibrationOverride_conclusionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RecalibrationOverride"
    ADD CONSTRAINT "RecalibrationOverride_conclusionId_fkey" FOREIGN KEY ("conclusionId") REFERENCES public."Conclusion"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: RecalibrationOverride RecalibrationOverride_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RecalibrationOverride"
    ADD CONSTRAINT "RecalibrationOverride_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: RecalibrationOverride RecalibrationOverride_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RecalibrationOverride"
    ADD CONSTRAINT "RecalibrationOverride_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ResearchSuggestion ResearchSuggestion_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResearchSuggestion"
    ADD CONSTRAINT "ResearchSuggestion_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ResearchSuggestion ResearchSuggestion_sourceUploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResearchSuggestion"
    ADD CONSTRAINT "ResearchSuggestion_sourceUploadId_fkey" FOREIGN KEY ("sourceUploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: ResearchSuggestion ResearchSuggestion_suggestedForFounderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResearchSuggestion"
    ADD CONSTRAINT "ResearchSuggestion_suggestedForFounderId_fkey" FOREIGN KEY ("suggestedForFounderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: ResolutionMismatch ResolutionMismatch_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResolutionMismatch"
    ADD CONSTRAINT "ResolutionMismatch_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ResolutionOverride ResolutionOverride_predictionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResolutionOverride"
    ADD CONSTRAINT "ResolutionOverride_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES public."ForecastPrediction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ResolutionRevision ResolutionRevision_resolutionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResolutionRevision"
    ADD CONSTRAINT "ResolutionRevision_resolutionId_fkey" FOREIGN KEY ("resolutionId") REFERENCES public."ForecastResolution"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ResponseTriage ResponseTriage_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResponseTriage"
    ADD CONSTRAINT "ResponseTriage_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ResponseTriage ResponseTriage_publicResponseId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ResponseTriage"
    ADD CONSTRAINT "ResponseTriage_publicResponseId_fkey" FOREIGN KEY ("publicResponseId") REFERENCES public."PublicResponse"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewItem ReviewItem_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewItem"
    ADD CONSTRAINT "ReviewItem_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: ReviewItem ReviewItem_resolvedByFounderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewItem"
    ADD CONSTRAINT "ReviewItem_resolvedByFounderId_fkey" FOREIGN KEY ("resolvedByFounderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: RevisionEvent RevisionEvent_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RevisionEvent"
    ADD CONSTRAINT "RevisionEvent_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: RevisionEvent RevisionEvent_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RevisionEvent"
    ADD CONSTRAINT "RevisionEvent_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: Session Session_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Session"
    ADD CONSTRAINT "Session_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Session Session_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Session"
    ADD CONSTRAINT "Session_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: SocialPost SocialPost_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SocialPost"
    ADD CONSTRAINT "SocialPost_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: SourceCredibilityUpdate SourceCredibilityUpdate_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SourceCredibilityUpdate"
    ADD CONSTRAINT "SourceCredibilityUpdate_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: SourceStanding SourceStanding_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SourceStanding"
    ADD CONSTRAINT "SourceStanding_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: SourceTriageItem SourceTriageItem_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SourceTriageItem"
    ADD CONSTRAINT "SourceTriageItem_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: Subscriber Subscriber_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Subscriber"
    ADD CONSTRAINT "Subscriber_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: UploadChunk UploadChunk_uploadId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."UploadChunk"
    ADD CONSTRAINT "UploadChunk_uploadId_fkey" FOREIGN KEY ("uploadId") REFERENCES public."Upload"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Upload Upload_founderId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Upload"
    ADD CONSTRAINT "Upload_founderId_fkey" FOREIGN KEY ("founderId") REFERENCES public."Founder"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: Upload Upload_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Upload"
    ADD CONSTRAINT "Upload_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: WatchedMarket WatchedMarket_organizationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WatchedMarket"
    ADD CONSTRAINT "WatchedMarket_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES public."Organization"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: objects objects_bucketId_fkey; Type: FK CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.objects
    ADD CONSTRAINT "objects_bucketId_fkey" FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id);


--
-- Name: s3_multipart_uploads s3_multipart_uploads_bucket_id_fkey; Type: FK CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.s3_multipart_uploads
    ADD CONSTRAINT s3_multipart_uploads_bucket_id_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id);


--
-- Name: s3_multipart_uploads_parts s3_multipart_uploads_parts_bucket_id_fkey; Type: FK CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.s3_multipart_uploads_parts
    ADD CONSTRAINT s3_multipart_uploads_parts_bucket_id_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id);


--
-- Name: s3_multipart_uploads_parts s3_multipart_uploads_parts_upload_id_fkey; Type: FK CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.s3_multipart_uploads_parts
    ADD CONSTRAINT s3_multipart_uploads_parts_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES storage.s3_multipart_uploads(id) ON DELETE CASCADE;


--
-- Name: vector_indexes vector_indexes_bucket_id_fkey; Type: FK CONSTRAINT; Schema: storage; Owner: -
--

ALTER TABLE ONLY storage.vector_indexes
    ADD CONSTRAINT vector_indexes_bucket_id_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets_vectors(id);


--
-- Name: audit_log_entries; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.audit_log_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: flow_state; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.flow_state ENABLE ROW LEVEL SECURITY;

--
-- Name: identities; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.identities ENABLE ROW LEVEL SECURITY;

--
-- Name: instances; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.instances ENABLE ROW LEVEL SECURITY;

--
-- Name: mfa_amr_claims; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.mfa_amr_claims ENABLE ROW LEVEL SECURITY;

--
-- Name: mfa_challenges; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.mfa_challenges ENABLE ROW LEVEL SECURITY;

--
-- Name: mfa_factors; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.mfa_factors ENABLE ROW LEVEL SECURITY;

--
-- Name: one_time_tokens; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.one_time_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: refresh_tokens; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.refresh_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: saml_providers; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.saml_providers ENABLE ROW LEVEL SECURITY;

--
-- Name: saml_relay_states; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.saml_relay_states ENABLE ROW LEVEL SECURITY;

--
-- Name: schema_migrations; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.schema_migrations ENABLE ROW LEVEL SECURITY;

--
-- Name: sessions; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.sessions ENABLE ROW LEVEL SECURITY;

--
-- Name: sso_domains; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.sso_domains ENABLE ROW LEVEL SECURITY;

--
-- Name: sso_providers; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.sso_providers ENABLE ROW LEVEL SECURITY;

--
-- Name: users; Type: ROW SECURITY; Schema: auth; Owner: -
--

ALTER TABLE auth.users ENABLE ROW LEVEL SECURITY;

--
-- Name: messages; Type: ROW SECURITY; Schema: realtime; Owner: -
--

ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;

--
-- Name: buckets; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.buckets ENABLE ROW LEVEL SECURITY;

--
-- Name: buckets_analytics; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.buckets_analytics ENABLE ROW LEVEL SECURITY;

--
-- Name: buckets_vectors; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.buckets_vectors ENABLE ROW LEVEL SECURITY;

--
-- Name: migrations; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.migrations ENABLE ROW LEVEL SECURITY;

--
-- Name: objects; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

--
-- Name: s3_multipart_uploads; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.s3_multipart_uploads ENABLE ROW LEVEL SECURITY;

--
-- Name: s3_multipart_uploads_parts; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.s3_multipart_uploads_parts ENABLE ROW LEVEL SECURITY;

--
-- Name: vector_indexes; Type: ROW SECURITY; Schema: storage; Owner: -
--

ALTER TABLE storage.vector_indexes ENABLE ROW LEVEL SECURITY;

--
-- Name: supabase_realtime; Type: PUBLICATION; Schema: -; Owner: -
--

CREATE PUBLICATION supabase_realtime WITH (publish = 'insert, update, delete, truncate');


--
-- Name: issue_graphql_placeholder; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER issue_graphql_placeholder ON sql_drop
         WHEN TAG IN ('DROP EXTENSION')
   EXECUTE FUNCTION extensions.set_graphql_placeholder();


--
-- Name: issue_pg_cron_access; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER issue_pg_cron_access ON ddl_command_end
         WHEN TAG IN ('CREATE EXTENSION')
   EXECUTE FUNCTION extensions.grant_pg_cron_access();


--
-- Name: issue_pg_graphql_access; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER issue_pg_graphql_access ON ddl_command_end
         WHEN TAG IN ('CREATE FUNCTION')
   EXECUTE FUNCTION extensions.grant_pg_graphql_access();


--
-- Name: issue_pg_net_access; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER issue_pg_net_access ON ddl_command_end
         WHEN TAG IN ('CREATE EXTENSION')
   EXECUTE FUNCTION extensions.grant_pg_net_access();


--
-- Name: pgrst_ddl_watch; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER pgrst_ddl_watch ON ddl_command_end
   EXECUTE FUNCTION extensions.pgrst_ddl_watch();


--
-- Name: pgrst_drop_watch; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER pgrst_drop_watch ON sql_drop
   EXECUTE FUNCTION extensions.pgrst_drop_watch();


--
-- PostgreSQL database dump complete
--

\unrestrict Kap6rjto6knbRZTQkvaYA7u0AqxeuqbgCajh0bFtbpJVESMuTzrf7jYTeqs8dho

