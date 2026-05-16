# DeskPilot Routine Catalog Index

Generated from `routine_packs/` routine definitions. Regenerate this
file with `desktop-agent generate-routine-docs` after routine metadata
changes.

## Catalog Summary

- Total routines: 37
- Packs: browser 8, native 8, social-content 21
- Safety classes: high 7, low 20, medium 10
- Approval policies: confirm 10, manifest_required 7, none 20
- Schedule policies: manual 37
- Windows proof required: 37
- Quarantined routines: 0
- Approval gaps: none

## Routine Index

| ID | Pack | Name | Surface | Safety | Approval | Schedule | Gates | Status | Reference |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| browser.download-open | browser | Browser open downloads | browser, downloads | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/download-open.yaml |
| browser.extract-visible-text | browser | Browser extract visible text | browser, extraction | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/extract-visible-text.yaml |
| browser.form-fill-basic | browser | Browser fill basic form | browser, forms | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/form-fill-basic.yaml |
| browser.navigation-open-page | browser | Browser open page | browser, navigation | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/navigation-open-page.yaml |
| browser.read-page | browser | Browser read page | browser, reading | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/read-page.yaml |
| browser.search-web | browser | Browser web search | browser, search | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/search-web.yaml |
| browser.settings-open | browser | Browser open settings | browser, settings | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/settings-open.yaml |
| browser.writing-surface-draft | browser | Browser draft writing surface | browser, writing, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/browser/tasks/writing-surface-draft.yaml |
| native.app-switch | native | App switch | native, app-switching | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/app-switch.yaml |
| native.calculator-basic | native | Calculator basic calculation | native, calculator | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/calculator-basic.yaml |
| native.clipboard-copy | native | Clipboard copy selection | native, clipboard | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/clipboard-copy.yaml |
| native.file-explorer-open | native | File Explorer open folder | native, files | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/file-explorer-open.yaml |
| native.notepad-draft | native | Notepad draft | native, notepad, writing | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/notepad-draft.yaml |
| native.office-like-draft | native | Office-like draft | native, office, writing | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/office-like-draft.yaml |
| native.settings-open | native | Windows open settings | native, settings | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/settings-open.yaml |
| native.window-manage | native | Window maximize | native, window-management | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/native/tasks/window-manage.yaml |
| social-content.facebook-approved-publish | social-content | Facebook approved publish | social, facebook, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.facebook-draft | social-content | Facebook draft | social, facebook, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.facebook-read | social-content | Facebook read-only review | social, facebook, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |
| social-content.instagram-approved-publish | social-content | Instagram approved publish | social, instagram, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.instagram-draft | social-content | Instagram draft | social, instagram, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.instagram-read | social-content | Instagram read-only review | social, instagram, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |
| social-content.linkedin-approved-publish | social-content | LinkedIn approved publish | social, linkedin, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.linkedin-draft | social-content | LinkedIn draft | social, linkedin, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.linkedin-read | social-content | LinkedIn read-only review | social, linkedin, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |
| social-content.medium-approved-publish | social-content | Medium approved publish | social, medium, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.medium-draft | social-content | Medium draft | social, medium, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.medium-read | social-content | Medium read-only review | social, medium, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |
| social-content.tiktok-approved-publish | social-content | TikTok approved publish | social, tiktok, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.tiktok-draft | social-content | TikTok draft | social, tiktok, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.tiktok-read | social-content | TikTok read-only review | social, tiktok, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |
| social-content.x-twitter-approved-publish | social-content | X/Twitter approved publish | social, x-twitter, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.x-twitter-draft | social-content | X/Twitter draft | social, x-twitter, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.x-twitter-read | social-content | X/Twitter read-only review | social, x-twitter, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |
| social-content.youtube-approved-publish | social-content | YouTube approved publish | social, youtube, publish | high | manifest_required | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/approved-publish-surface.yaml |
| social-content.youtube-draft | social-content | YouTube draft | social, youtube, draft | medium | confirm | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/draft-surface.yaml |
| social-content.youtube-read | social-content | YouTube read-only review | social, youtube, read-only | low | none | manual | schema_validation,dry_run,fixture_test,trace_replay_review,documentation,windows_proof | active | task:routine_packs/social-content/tasks/read-only-surface.yaml |

## Search Coverage

The local catalog search indexes routine IDs, names, tags, required app,
required site, descriptions, goals, inputs, and outputs. Use these
query seeds when checking deep catalog search behavior:

- `browser`
- `native`
- `social-content`
- `social`
- `draft`
- `publish`
- `read-only`
- `facebook`
- `instagram`
- `linkedin`
- `medium`
- `tiktok`
- `writing`
- `facebook.com`
- `instagram.com`
- `linkedin.com`
- `medium.com`
- `tiktok.com`
- `x.com`
- `youtube.com`
- `Browser`
- `Windows desktop`
- `Calculator`
- `File Explorer`
- `Notepad`
- `Office-like editor`
- `Settings`

## Monitoring Fields

- Promotion gates: schema validation, dry-run, fixture test, trace
  replay review, documentation, and Windows proof when applicable.
- Report metadata: routine ID, name, tags, safety class, schedule
  policy, approval policy, expected duration, reference kind, failed
  evidence count, quarantine status, and promotion gates.
- Quarantine rule: routines are quarantined when explicitly marked or
  when failed evidence count reaches three.
