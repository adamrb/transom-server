# Automations feature (`src/features/automations`)

Entry: `AutomationsPage` (route `#/automations`, loaded on demand). Frame: `SectionAppBar`
(auto-hidden when embedded) plus a scroll container with `pt-(--content-top-pad)
pb-(--content-bottom-pad)`, 24 px gutters (16 px on phone), inner max width 860 px.

Reference behaviour: `app/static/index.html` on `main` (`loadAutomations`, `loadRoutes`, `loadLog`,
the route editor modal). Visual target: `shot-automations-*` and `shot-automations-activity-*`.

## What it does (from SPEC.md)

- **Status banner** (`Banner`): `useRouterStatus` → success "Automations are on. Two of three rules
  are turned on · last run Today 2:48 AM" or warning when turned off / not set up. User words only;
  never the model id.
- **Rules list** (`useRoutes`): one card per rule with a leading action icon (`send` for webhook,
  `description` for markdown, `block` for none), name, `Switch` (toggle `enabled` via
  `useUpdateRoute` with the full body), description (`Markdown` or plain), footer with a
  `StatusChip tone="tag"` describing the action in user words ("Sends to the agent", "Saves a note
  in Inbox", "Just decides"), text **Edit** and text-danger **Delete** (to the right, `ConfirmDialog
danger`). Turned-off rules are dimmed. "Add rule" is a tonal `Button` in the section header.
- **Rule editor** (`Dialog`): name, description (multiline `TextField`), action as a
  `SegmentedButton` or radio list in user words (Send to a webhook / Save a markdown note / Just
  decide), per-action fields: webhook URL + secret header as a password field with a reveal button
  and the placeholder "Set. Leave blank to keep it." when editing. The server rebuilds
  `action_config` from the body on every PUT, so when the field is left blank resend the route's
  current `action_config.auth_header` (the old dashboard did exactly this, with a "Clear the header"
  checkbox to drop it); markdown folder. Server validation errors come back as
  `ApiError.detail` sentences; show them inline.
- **Try it on a recording**: preview a rule set against a recording (`usePreviewAutomations`) and
  show the decision in a dialog.
- **Activity log** (`useRoutingLog`, polls every 15 s): runs grouped by day, each a card with the
  recording title (clickable → `#/rec/<id>`; "Deleted recording" when `recording_deleted`), time,
  "Your note: …" when `instructions` is set, decision lines (`wand_stars` per matched rule with the
  reason; `check_circle` "Nothing matched" with the reason), delivery rows (tonal, name + result
  summary + time; `StatusChip tone="failed"` + tries + outlined **Retry** via `useRetryDelivery`
  when failed or `result_status === 'unknown'`), and "Earlier runs (n)" disclosure when a recording
  has several runs. Refresh icon button in the section header.

## Where things go

```
automations/
  AutomationsPage.tsx     route component: banner, Rules section, Activity section (all hidden
                          behind the banner when the server has no automations endpoint)
  StatusBanner.tsx        on / turned off / not set up / too old, plus rulesSummary()
  SectionHeader.tsx       "Rules" / "Activity" header with sentence and trailing actions
  rules/
    actionWords.ts        ACTION_KINDS, actionIcon(), actionChip()  (type → user words)
    RulesSection.tsx      list, toggle (optimistic PUT), delete confirm, opens the editor
    RuleCard.tsx          glyph, name, Switch, description, chip, Edit / Delete
    RuleEditor.tsx        draft state, buildRouteBody() validation, save; `Dialog size="md" fullScreen`
                          (560 px card on desktop, full-screen with a top bar on phone)
    ActionKindField.tsx   `RadioGroup` in user words: Send it to the agent / Save a note / Just record
    WebhookFields.tsx     Agent address + secret header (password, Show/Hide, Remove chip)
    MarkdownFields.tsx    Folder in your vault
    TryItPanel.tsx        `Select` of recent recordings → POST route/preview → matches[] with reasons
  activity/
    groupRuns.ts          groupRuns(), runTitle() ("Deleted recording"), runRecordedAt(), runCanOpen()
    ActivitySection.tsx   useRoutingLog (15 s), Refresh, empty / error states, cards
    ActivityCard.tsx      title (opens #/rec/<id> unless deleted), times, note, decisions, outcomes
    RunDecisions.tsx      DecisionLine per matched rule, "Nothing matched", run error + Details
    DecisionLine.tsx      glyph + rule name + reason behind "Why?" (or inline for previews)
    OutcomeLine.tsx       a delivery: chip only Working/Failed, tries, Retry, outcome sentence
    GroupedRuns.tsx       "Earlier runs (n)" disclosure
  automations.test.tsx    banner states, chip mapping, toggle optimistic + revert, delete, empties
  ruleEditor.test.tsx     validation, secret-header semantics, 409 inline, Try it (matches[])
  activity.test.tsx       grouping, titles, Why?, Earlier runs, Retry, navigation
```

Hooks (`src/api/hooks/automations.ts`): `useRoutes`, `useCreateRoute`, `useUpdateRoute` (optimistic
cache update, rolled back on error), `useDeleteRoute`, `useRouterStatus`, `useRoutingLog`,
`useRetryDelivery`, `usePreviewAutomations`, `routeBody(route, patch)`. Errors:
`errorMessage(err, fallback)` through `useSnackbar()`; 5xx never leak their text (the fallback shows).

Design-system pieces this feature relies on: `Dialog` (`size`, `fullScreen`), `RadioGroup`,
`Select` (opens its list inside the editor's `<dialog>`), `Switch`, `TextField`, `Banner`,
`StatusChip`, `ConfirmDialog danger`. The page itself is loaded on demand (see `shell/routes.tsx`).
