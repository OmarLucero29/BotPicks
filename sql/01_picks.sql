create extension if not exists pgcrypto;
create table if not exists picks (
  id uuid primary key default gen_random_uuid(),
  fecha timestamptz not null,
  deporte text not null,
  liga text not null,
  partido text not null,
  mercado text not null,
  pick text not null,
  cuota numeric not null,
  prob_modelo numeric not null,
  brier numeric,
  stake numeric,
  stake_pct numeric,
  confianza text,
  ev numeric,
  resultado text,
  roi numeric,
  kelly_raw numeric,
  kelly_fraction numeric,
  extra jsonb,
  created_at timestamptz default now()
);
create index if not exists idx_picks_fecha on picks(fecha);
create index if not exists idx_picks_deporte_liga on picks(deporte, liga);
