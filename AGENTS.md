# Agent Guidelines

## User Interaction

- MUST call the `/polish` skill on every new user message before any other work begins, and output it, then use the rewritten request as the source of truth for the current turn only
- NEVER ask for info that can be inferred or fetched via tools
- NEVER assume completeness—check for missing inputs and request them explicitly
- NEVER exectue tasks with incomplete inputs; prompt the user instead
- MUST recommend next steps after task completion based on the current context and user goals; next steps MUST be actionable, relevant, and clearly communicated to the user

## Writing Style and Tone

- Use clear naming and organization for easy access and future reference
- Keep the content concise and beginner-friendly
- Use clear, simple language and avoid unnecessary jargon
- Maintain a warm and encouraging tone throughout, never cold and clinical
- Use emojis sparingly to improve readability and visual clarity, without overusing them
- Add colored Mermaid diagrams or other visual aids when they help explain complex concepts more clearly
- Use numbered steps or sequence markers in diagrams to make flows easier to understand
- Avoid Markdown-sensitive syntax in Mermaid diagrams; use plain text labels such as `1: run task` instead of `1. run task`

## Documentation

- MUST use English for all documentation
- `docs` folder is for user-facing documentation, such as guides(`*-guide.md`), specifications(`*-spec.md`), adrs(`*-adr.md`), and other reference materials
- NEVER implement a new feature or make a significant change without first creating an ADR and Specification for it, and linking to them in the relevant documentation
- NEVER make changes to the codebase without updating the relevant documentation, including ADRs, specifications, and user guides, to reflect the changes accurately
- MUST read and understand the relevant documentation before making changes to ensure consistency and correctness in implementation
- ONLY read the documentation that is relevant to the task at hand; avoid getting bogged down in unrelated details
- MUST document todo items and open questions in the relevant ADRs and specifications, and link to them in the user guides for visibility
- BEFORE opening a PR, MUST update *README.md* with a docs index and keep it in sync with any doc changes.
  
## Development

- NEVER mark a coding task as "done" until all tests and linting checks have passed successfully
- MUST treat warnings as errors and address them promptly to maintain code quality and prevent technical debt
- MUST treat codebase as the ONLY source of truth for implementation details; avoid relying on memory or assumptions about how things work
- MUST define models using Pydantic for clear data validation and type safety
