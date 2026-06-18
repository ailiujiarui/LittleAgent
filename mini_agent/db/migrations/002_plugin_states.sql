create table if not exists plugin_states (
    source text not null,
    name text not null,
    enabled integer not null,
    locked integer not null default 0,
    last_loaded_at text,
    last_error text not null default '',
    updated_at text not null default current_timestamp,
    primary key (source, name)
);
