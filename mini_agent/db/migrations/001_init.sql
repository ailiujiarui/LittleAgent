create table if not exists sessions (
    id text primary key,
    channel text not null,
    chat_id text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists messages (
    id integer primary key autoincrement,
    session_id text not null,
    role text not null,
    content text not null,
    created_at text not null default current_timestamp
);

create table if not exists tool_events (
    id integer primary key autoincrement,
    session_id text,
    tool_name text not null,
    arguments_json text not null default '{}',
    result_json text not null default '{}',
    created_at text not null default current_timestamp
);

create table if not exists runtime_events (
    id integer primary key autoincrement,
    event_type text not null,
    payload_json text not null default '{}',
    created_at text not null default current_timestamp
);

create table if not exists memory_items (
    id integer primary key autoincrement,
    kind text not null,
    content text not null,
    keywords text not null default '',
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists proactive_items (
    id integer primary key autoincrement,
    source text not null,
    item_key text not null,
    title text not null default '',
    url text not null default '',
    judged_at text,
    pushed_at text,
    unique(source, item_key)
);

create table if not exists drift_runs (
    id integer primary key autoincrement,
    started_at text not null default current_timestamp,
    finished_at text,
    status text not null,
    summary text not null default ''
);

create table if not exists plugin_kv (
    plugin_name text not null,
    key text not null,
    value_json text not null,
    updated_at text not null default current_timestamp,
    primary key (plugin_name, key)
);
