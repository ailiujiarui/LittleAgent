# Group Message Reader Design

## Goal

Add a plugin that archives recent messages from configured QQ groups and exposes
them to the agent through a `read_group_messages` tool, without replying to
ordinary group chatter.

## Behavior

- Only groups configured under `[onebot.groups]` are observed.
- Existing `allow_from` rules continue to restrict which senders are observed.
- Every allowed message from a configured group emits a `group_message` plugin
  event, even when `require_at = true` and the bot was not mentioned.
- `require_at` continues to control whether a message enters the AgentLoop and
  can produce a reply.
- The built-in group-message plugin keeps the latest 200 messages per group in
  plugin KV storage.
- The plugin registers `read_group_messages(group_id?, limit=20)`.
- In a group turn, `group_id` may be omitted and is inferred from the current
  `gqq:<group_id>` chat context.
- The tool returns at most 100 recent messages per call.

## Data Flow

1. NapCat sends a OneBot group message event.
2. `OneBotQQChannel` validates the configured group and `allow_from`.
3. The channel emits normalized message data to plugins as `group_message`.
4. The group-message plugin appends the normalized message to its rolling
   archive.
5. The channel separately applies `require_at`. Only actionable messages are
   published to the inbound bus and processed by the AgentLoop.
6. During an actionable turn, the LLM can call `read_group_messages` to inspect
   the archive.

## Storage And Privacy

The archive contains group ID, sender ID, sender display name when available,
text, message ID, and OneBot timestamp. It only covers messages observed while
the bot is online. It does not request older history from NapCat. The existing
workspace SQLite database stores the plugin KV data.

## Error Handling

- Unconfigured groups and disallowed senders are ignored and not archived.
- Calling the tool outside a group chat without an explicit `group_id` returns
  a tool error.
- Plugin handler failures remain isolated by the existing `PluginManager.emit`
  behavior and do not stop OneBot message processing.

## Verification

- A configured group message without an `@bot` is archived but not published to
  the AgentLoop.
- An `@bot` group message is archived and still published for reply.
- Unconfigured or disallowed messages are not archived.
- The tool reads recent messages, infers the current group, and enforces the
  rolling archive and query limits.
