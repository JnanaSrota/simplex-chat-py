# PR to submit to simplex-chat/simplex-chat
# File: bots/README.md
# Section: ## Useful bots
# Add this line after the last entry in the list:

* [simplex-chat-py](https://github.com/JnanaSrota/simplex-chat-py) (Python) - Python client library with a high-level decorator API, supporting direct messages, group messages, moderation, and file transfers. Includes an AI bot example using Groq + Llama 3.

---

# PR details:
# Title: Add simplex-chat-py Python client library to useful bots
# Base branch: stable
# Description:
"""
## Summary

This PR adds [simplex-chat-py](https://github.com/JnanaSrota/simplex-chat-py) to the list of useful bots.

`simplex-chat-py` is a Python client library for the SimpleX Chat bot API that:

- Wraps the full WebSocket bot API documented in `bots/api/COMMANDS.md`
- Provides a high-level `SimplexBot` class with decorator-based event handlers
- Covers all documented commands: messages, groups, files, moderation, address management
- Includes three working examples: echo bot, AI bot (Groq + Llama 3), moderation bot
- Published on PyPI as `simplex-chat-py`
- Full test suite covering command string formatting against `COMMANDS.md`

## Motivation

The existing bots list has no Python library. This fills that gap and makes
SimpleX bot development accessible to the Python community.

## Testing

```bash
pip install simplex-chat-py
python -c "from simplex_chat import SimplexBot; print('ok')"
```
"""
