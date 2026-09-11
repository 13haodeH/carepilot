-- CarePilot v0.3: Supabase Auth profiles, role boundaries, and demo-order access.
-- Apply after 007. It removes only the obsolete local-demo identity tables;
-- no tickets, Agent Runs, policy snapshots, or audit records are deleted.

begin;

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    display_name varchar(120) not null default '新用户',
    role varchar(16) not null default 'user' check (role in ('user', 'admin', 'superadmin')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.demo_order_entitlements (
    user_id uuid not null references public.profiles(id) on delete cascade,
    order_id varchar(48) not null,
    created_at timestamptz not null default now(),
    primary key (user_id, order_id)
);

-- app_users/app_sessions were created exclusively for the retired local demo
-- password flow. Supabase Auth is now the sole password authority.
drop table if exists public.app_sessions;
drop table if exists public.app_users;

create or replace function public.create_profile_for_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, display_name, role)
    values (
        new.id,
        coalesce(nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''), '新用户'),
        'user'
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created_carepilot on auth.users;
create trigger on_auth_user_created_carepilot
    after insert on auth.users
    for each row execute procedure public.create_profile_for_new_auth_user();

-- Backfill Profiles for any Auth users that existed before this migration.
-- Every backfilled account is a normal user until a project owner explicitly promotes it.
insert into public.profiles (id, display_name, role)
select
    users.id,
    coalesce(nullif(trim(users.raw_user_meta_data ->> 'display_name'), ''), split_part(users.email, '@', 1), '新用户'),
    'user'
from auth.users as users
on conflict (id) do nothing;

alter table public.profiles enable row level security;
alter table public.demo_order_entitlements enable row level security;

revoke all on table public.profiles, public.demo_order_entitlements from anon, authenticated;
grant select on table public.profiles to authenticated;
grant all on table public.profiles, public.demo_order_entitlements to service_role;

drop policy if exists "carepilot_profiles_read_own" on public.profiles;
create policy "carepilot_profiles_read_own"
on public.profiles for select to authenticated
using (id = auth.uid());

-- Role changes are deliberately not exposed through RLS. Use the controlled
-- promotion statements below in Supabase SQL Editor after the accounts exist.

-- Demo role promotion templates (replace the email after the account is created):
-- update public.profiles set role = 'superadmin'
-- where id = (select id from auth.users where email = 'your-superadmin@example.com');
-- update public.profiles set role = 'admin'
-- where id = (select id from auth.users where email = 'your-admin@example.com');

comment on table public.profiles is 'Server-controlled CarePilot role profile for Supabase Auth users. Registration always creates role=user.';
comment on table public.demo_order_entitlements is 'Controlled simulated-order access for authenticated demo users; not a production order connector.';

commit;
