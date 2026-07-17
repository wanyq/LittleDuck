# API module boundaries

WI-003 should add one folder per accepted architecture module:

- `user-auth`
- `admin-auth`
- `conversations`
- `generations`
- `llm-config`
- `admin-topics`
- `llm-provider`
- `jobs`

Routes call application services; application services call repositories or provider ports. A route must not query another module's tables directly.
