cat > sql/tables.sql <<'SQL'
-- sql/tables.sql
-- Ejecutar en Supabase SQL editor para crear las tablas mínimas

create table if not exists public.next_events (
  id uuid default gen_random_uuid() primary key,
  fecha timestamptz,
  deporte text,
  liga text,
  home_team text,
  away_team text,
  odds_home numeric,
  odds_draw numeric,
  odds_away numeric,
  meta jsonb
);

create table if not exists public.historical_matches (
  id uuid default gen_random_uuid() primary key,
  fecha timestamptz,
  deporte text,
  liga text,
  home_team text,
  away_team text,
  home_goals integer,
  away_goals integer,
  outcome text,
  odds_home numeric,
  odds_draw numeric,
  odds_away numeric,
  meta jsonb
);

create table if not exists public.picks (
  id uuid primary key,
  fecha timestamptz,
  deporte text,
  partido text,
  mercado text,
  pick text,
  cuota numeric,
  stake numeric
);
SQL
