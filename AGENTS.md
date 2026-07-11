# AGENTS.md

Instructions and institutional context for AI coding assistants working in this repo (Claude Code, Cursor, Copilot, Codex, and others that read this file).

## Recent changes (auto-updated by PandaBear on every push)

<!-- pandabear:auto-changelog:start -->

### 2026-07-11 23:41 UTC · mariiaivanovacs · `7c94ff8` on `master`
**Files:** + `new-file_Rules.md`
- A new file `new-file_Rules.md` was added to test the accuracy of the `AGENTS.md` filename.
- The file contains a single line indicating it's a test for filename correctness.
- This change is likely part of a process to verify file naming conventions or documentation structure.
- The addition may help ensure consistency in how files are named and referenced within the project.
- No functional changes are introduced by this commit.

### 2026-07-11 23:30 UTC · mariiaivanovacs · `ba1f9a4` on `master`
- A new `AGENTS.md` file was added to document AI assistant setup and project context, with auto-updating via a GitHub webhook for real-time updates.  
- The webhook uses local `git diff` to track changes securely without exposing code or API tokens, and stores secrets in a vault.  
- A new `/agents` route was added to the admin panel to display the auto-updated `AGENTS.md` timeline of changes in a formatted HTML view.  
- A new `Rules.md` file was created with basic guidelines for behavior, though it contains a typo in "hte" which should be corrected.

### 2026-07-11 23:29 UTC · mariiaivanovacs · `3a14c87` on `master`
- A new `AGENTS.md` file was added to document AI assistant setup and project context, with auto-updating via a GitHub webhook for real-time updates.  
- The webhook uses local `git diff` to track changes securely without exposing code or API tokens, and stores secrets in a vault.  
- The `/agents` route was added to the admin panel to display the auto-updated `AGENTS.md` timeline of changes in a formatted HTML view.  
- The code now includes regex parsing logic to extract and structure changelog entries from `AGENTS.md` for display in the admin interface.

### 2026-07-11 22:41 UTC · mariiaivanovacs · `2379c5f` on `master`
- Added documentation on setting up a GitHub webhook to keep `AGENTS.md` updated automatically.  
- Webhook uses local `git diff` to track changes without exposing code or using GitHub API tokens.  
- Changes are appended to `AGENTS.md`, ensuring AI tools and users get real-time updates without manual maintenance.  
- Webhook secret is stored in a vault, enhancing security.  
- Webhook endpoint is `/webhooks/github/push` and triggers on `push` events.

### 2026-07-11 22:31 UTC · mariiaivanovacs · `8b586a5` on `master`
- Added comprehensive README with architecture overview, module map, and run instructions, improving onboarding and understanding of the project structure.  
- Introduced a modular design with clear separation of concerns between policy checks, tool execution, and credential management, enhancing security and maintainability.  
- Included detailed documentation for running the application, testing, and integrating with Telegram and GitHub, making it easier for new contributors to get started.  
- Emphasized security through Fernet-encrypted credential vaults, subprocess isolation, and append-only audit logs, ensuring sensitive data is never exposed to models.  
- Added support for role-based chat interactions in Telegram, allowing users to switch personas dynamically, which is useful for demonstrating permission differences.

<!-- pandabear:auto-changelog:end -->
