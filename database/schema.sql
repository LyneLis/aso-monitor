create extension if not exists pgcrypto;

create table if not exists public.monitor_users (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    chat_id text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.tracked_apps (
    id uuid primary key default gen_random_uuid(),
    package_id text not null,
    platform text not null check (platform in ('android', 'ios')),
    owner_chat_id text not null references public.monitor_users(chat_id) on update cascade on delete restrict,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (package_id, owner_chat_id)
);

create table if not exists public.tracked_locales (
    id uuid primary key default gen_random_uuid(),
    app_id uuid not null references public.tracked_apps(id) on delete cascade,
    geo text not null,
    title text not null default '',
    summary text not null default '',
    description text not null default '',
    icon text not null default '',
    header_image text not null default '',
    screenshots jsonb not null default '[]'::jsonb,
    last_checked_at timestamptz,
    last_status text,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (app_id, geo)
);

create table if not exists public.snapshots (
    id uuid primary key default gen_random_uuid(),
    locale_id uuid not null references public.tracked_locales(id) on delete cascade,
    title text not null default '',
    summary text not null default '',
    description text not null default '',
    icon text not null default '',
    header_image text not null default '',
    screenshots jsonb not null default '[]'::jsonb,
    source text not null default 'manual' check (source in ('import', 'bot', 'site', 'manual')),
    captured_at timestamptz not null default now()
);

create table if not exists public.check_runs (
    id uuid primary key default gen_random_uuid(),
    source text not null check (source in ('bot', 'site', 'import')),
    status text not null default 'running' check (status in ('running', 'success', 'partial', 'error')),
    checked_count integer not null default 0,
    changed_count integer not null default 0,
    error_count integer not null default 0,
    message text,
    started_at timestamptz not null default now(),
    finished_at timestamptz
);

create table if not exists public.check_logs (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references public.check_runs(id) on delete set null,
    locale_id uuid not null references public.tracked_locales(id) on delete cascade,
    status text not null,
    error text,
    meta jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.change_events (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references public.check_runs(id) on delete set null,
    locale_id uuid not null references public.tracked_locales(id) on delete cascade,
    old_snapshot_id uuid references public.snapshots(id) on delete set null,
    new_snapshot_id uuid references public.snapshots(id) on delete set null,
    changed_fields text[] not null default '{}'::text[],
    is_rollback boolean not null default false,
    source text not null check (source in ('bot', 'site')),
    created_at timestamptz not null default now()
);

create table if not exists public.aso_audits (
    id uuid primary key default gen_random_uuid(),
    app_id uuid not null references public.tracked_apps(id) on delete cascade,
    audit_text text not null,
    source text not null default 'site' check (source in ('site', 'import')),
    created_at timestamptz not null default now()
);

create table if not exists public.notification_queue (
    id uuid primary key default gen_random_uuid(),
    chat_id text not null,
    kind text not null,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'pending' check (status in ('pending', 'sent', 'error')),
    attempts integer not null default 0,
    last_error text,
    available_at timestamptz not null default now(),
    sent_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists tracked_apps_owner_idx
    on public.tracked_apps(owner_chat_id);

create index if not exists tracked_locales_app_idx
    on public.tracked_locales(app_id);

create index if not exists snapshots_locale_captured_idx
    on public.snapshots(locale_id, captured_at desc);

create index if not exists check_logs_locale_created_idx
    on public.check_logs(locale_id, created_at desc);

create index if not exists change_events_locale_created_idx
    on public.change_events(locale_id, created_at desc);

create index if not exists aso_audits_app_created_idx
    on public.aso_audits(app_id, created_at desc);

create index if not exists notification_queue_status_available_idx
    on public.notification_queue(status, available_at);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists monitor_users_set_updated_at on public.monitor_users;
create trigger monitor_users_set_updated_at
before update on public.monitor_users
for each row execute function public.set_updated_at();

drop trigger if exists tracked_apps_set_updated_at on public.tracked_apps;
create trigger tracked_apps_set_updated_at
before update on public.tracked_apps
for each row execute function public.set_updated_at();

drop trigger if exists tracked_locales_set_updated_at on public.tracked_locales;
create trigger tracked_locales_set_updated_at
before update on public.tracked_locales
for each row execute function public.set_updated_at();

alter table public.monitor_users enable row level security;
alter table public.tracked_apps enable row level security;
alter table public.tracked_locales enable row level security;
alter table public.snapshots enable row level security;
alter table public.check_runs enable row level security;
alter table public.check_logs enable row level security;
alter table public.change_events enable row level security;
alter table public.aso_audits enable row level security;
alter table public.notification_queue enable row level security;
