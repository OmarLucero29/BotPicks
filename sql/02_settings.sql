create table if not exists settings (
  key text primary key,
  value text not null,
  updated_at timestamptz default now()
);
insert into settings(key, value) values('bankroll','500')
on conflict (key) do nothing;
