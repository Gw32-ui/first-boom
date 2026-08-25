# AGENTS.md

## Purpose

This repo provides a lightweight vision helper for agents without native image input. When an image cannot be read directly, use `vision.js` to convert it into text through a configured vision API.

## When to use

- Image path: `node vision.js "<absolute image path>" "<prompt>"`
- Image URL: `node vision.js --url "<image url>" "<prompt>"`
- Pasted image with no accessible path/URL: `node vision.js --clipboard "<prompt>"`

Fallback rules:

- If a local path does not exist, or no path/URL is provided, `vision.js` automatically tries the system clipboard.
- Pass `--no-fallback` to disable automatic clipboard fallback and fail with an explicit error.

## Configuration

Credentials come from `DASHSCOPE_API_KEY`, `VISION_MODEL`, and `DASHSCOPE_BASE_URL`, either as environment variables or a `.env` file next to `vision.js`. Never commit `.env`.

## Rules

- Always use the absolute path to `vision.js`.
- Never print or share the API key.
- If the API call fails, report the error and ask the user to check the key, model, or base URL.
