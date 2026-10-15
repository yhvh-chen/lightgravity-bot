#!/usr/bin/env bash
# QA-r2 helper: run a command with credential/real-model-gate env vars removed.
# Never reads .env.
unset_env() {
  env \
    -u DEEPSEEK_API_KEY -u OPENAI_API_KEY -u GEMINI_API_KEY -u GOOGLE_API_KEY \
    -u ANTIGRAVITY_API_KEY -u ANTHROPIC_API_KEY -u LG020_REAL_DEEPSEEK \
    -u LG_REAL_DEEPSEEK -u DEEPSEEK_BASE_URL -u OPENAI_BASE_URL \
    "$@"
}
unset_env "$@"
