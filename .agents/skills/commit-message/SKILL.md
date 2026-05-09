---
name: commit-message
description: Best practices and guidelines for writing clear, concise, and informative git commit messages. Trigger when user asks to write, suggest, or improve a git commit message. When you are about to commit code changes on behalf of the user. Reviewing a commit message for quality or convention compliance and Setting up commit message templates or guidelines for a project
---

## Core Principles

1. **A commit message explains WHY, not just WHAT.** The diff already shows what changed — the message must explain the intent.
2. **Atomic commits** — each commit should represent one logical change.
3. **Present tense, imperative mood** — "Add feature" not "Added feature" or "Adds feature".
4. **Subject line ≤ 72 characters** — enforced by most Git tools.
5. **Blank line between subject and body** — required for proper Git parsing.

---

## Commit Message Format

```
<type>(<scope>): <short summary>

[optional body — wrap at 72 chars]

[optional footer(s)]
```

### Types (Conventional Commits)

| Type       | When to Use                                                   |
|------------|---------------------------------------------------------------|
| `feat`     | A new feature visible to users or consumers                   |
| `fix`      | A bug fix                                                     |
| `docs`     | Documentation-only changes                                    |
| `style`    | Formatting, whitespace, missing semicolons (no logic change)  |
| `refactor` | Code restructuring without changing behavior                  |
| `perf`     | Performance improvements                                      |
| `test`     | Adding or fixing tests                                        |
| `build`    | Build system or dependency changes (webpack, npm, etc.)       |
| `ci`       | CI/CD configuration changes                                   |
| `chore`    | Maintenance tasks that don't modify src or test files         |
| `revert`   | Reverts a previous commit                                     |

### Scope (optional)

A noun describing the section of the codebase: `auth`, `api`, `ui`, `db`, `config`, etc.

---

## Subject Line Rules

- Use imperative mood: **"Fix"**, **"Add"**, **"Remove"**, **"Update"**, **"Refactor"**
- Do **not** end with a period
- Capitalize the first letter after the type/scope
- Keep it under 72 characters
- Be specific — avoid vague messages like `fix bug` or `update stuff`

### ✅ Good Examples
```
feat(auth): add JWT refresh token rotation
fix(api): handle null response from payment gateway
refactor(db): extract query builder into separate module
docs: add setup instructions for local development
```

### ❌ Bad Examples
```
fixed stuff
WIP
update
changes to auth
```

---

## Body Guidelines

Include a body when:
- The change is non-obvious or has important context
- You are fixing a tricky bug (explain root cause)
- There is a trade-off or design decision worth noting
- The change may have side effects

Body rules:
- Separate from subject with a **blank line**
- Wrap lines at **72 characters**
- Use bullet points for multiple points
- Explain **why** the change was made, not just what

### Example with Body
```
fix(auth): prevent session fixation on login

Previously, the session ID was not regenerated after a successful
login, allowing an attacker who obtained a pre-auth session ID to
hijack the authenticated session.

Regenerate the session ID immediately after credential validation
to mitigate session fixation attacks (CWE-384).
```

---

## Footer Guidelines

Use footers for:
- **Breaking changes**: `BREAKING CHANGE: <description>`
- **Issue references**: `Closes #123`, `Fixes #456`, `Refs #789`
- **Co-authors**: `Co-authored-by: Name <email>`

### Example with Footer
```
feat(api): add rate limiting to public endpoints

Apply token bucket rate limiting (100 req/min) to all unauthenticated
API routes to prevent abuse and reduce server load.

BREAKING CHANGE: Clients exceeding the rate limit will now receive
HTTP 429 instead of HTTP 200 with an error body.
Closes #301
```

---

## Decision Guide: Subject-Only vs. Subject + Body

| Situation                          | Format                  |
|------------------------------------|-------------------------|
| Trivial, self-explanatory change   | Subject only            |
| Bug fix with non-obvious root cause| Subject + Body          |
| New feature with design rationale  | Subject + Body          |
| Breaking change                    | Subject + Body + Footer |
| Issue-linked work                  | Subject + Footer        |
| Revert of a previous commit        | Use `revert` type + Body referencing the reverted SHA |

---

## Revert Commits

```
revert: feat(auth): add JWT refresh token rotation

This reverts commit a1b2c3d4e5f because the refresh token
implementation introduced a race condition under high concurrency.
```

---

## Checklist Before Finalizing a Commit Message

- [ ] Subject line ≤ 72 characters
- [ ] Imperative mood used ("Add", not "Added")
- [ ] No trailing period on subject line
- [ ] Correct type chosen from the table above
- [ ] Scope added if it narrows down the changed area
- [ ] Body included if the "why" isn't obvious
- [ ] Relevant issue numbers referenced in footer
- [ ] `BREAKING CHANGE` footer added if applicable
