# Kimi K2 / K2.5 API Research

> Compiled: 2026-02-13 | Sources: HuggingFace model card, GitHub repo, API endpoint probing

## ⚠️ Important Clarification: K2 vs K2.5

The open-source model is **Kimi K2** (not K2.5). The model names `kimi-k2.5` and `kimi-k2.5-instant` may be **platform-specific hosted variants** on `platform.moonshot.ai` that are not identical to the open-source K2-Instruct. The platform docs are JS-rendered SPAs that couldn't be scraped, so some details below are inferred from the open-source K2 documentation + API probing.

---

## 1. Base URLs

### International (platform.moonshot.ai)
```
https://api.moonshot.ai/v1
```
- Confirmed working endpoint (returns proper OpenAI-style 401 error with `"Incorrect API key provided"`)

### Chinese (platform.moonshot.cn)  
```
https://api.moonshot.cn/v1
```
- Also confirmed working (returns proper error responses)

Both endpoints appear to serve the same API with OpenAI-compatible format.

## 2. Authentication

Standard **Bearer token** in the `Authorization` header:

```
Authorization: Bearer sk-xxxxxxxxxxxxxxxx
```

API keys are obtained from:
- International: https://platform.moonshot.ai/console/api-keys
- Chinese: https://platform.moonshot.cn/console/api-keys

## 3. Model Names

### Hosted API models (platform.moonshot.ai):
- `kimi-k2.5` — thinking/reasoning model variant
- `kimi-k2.5-instant` — non-thinking, fast variant

### Open-source / self-hosted:
- `kimi-k2` or custom `--served-model-name` in vLLM/SGLang

**Note:** The exact model name strings for the hosted API should be verified against the platform's model list. The K2.5 naming may indicate a post-trained or updated version beyond the open-source K2.

## 4. Chat Completions Format

Fully **OpenAI-compatible** `/v1/chat/completions` endpoint.

### Basic Request

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-key-here",
    base_url="https://api.moonshot.ai/v1"
)

response = client.chat.completions.create(
    model="kimi-k2.5",  # or "kimi-k2.5-instant"
    messages=[
        {"role": "system", "content": "You are Kimi, an AI assistant created by Moonshot AI."},
        {"role": "user", "content": "Hello, introduce yourself briefly."}
    ],
    temperature=0.6,
    max_tokens=256
)
print(response.choices[0].message.content)
```

### cURL Example

```bash
curl -X POST https://api.moonshot.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-your-key-here" \
  -d '{
    "model": "kimi-k2.5",
    "messages": [
      {"role": "system", "content": "You are Kimi, an AI assistant created by Moonshot AI."},
      {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.6,
    "max_tokens": 256
  }'
```

## 5. System Message Handling

Standard `role: "system"` messages work normally. The recommended default system prompt is:

```
You are Kimi, an AI assistant created by Moonshot AI.
```

The `name` field in messages is also supported (added 2025-08-11).

## 6. Tool / Function Calling

Fully supported with OpenAI-compatible tool calling format.

### Tool Definition

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Retrieve current weather information.",
        "parameters": {
            "type": "object",
            "required": ["city"],
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Name of the city"
                }
            }
        }
    }
}]
```

### Multi-turn Tool Call Flow

```python
# Step 1: Send request with tools
response = client.chat.completions.create(
    model="kimi-k2.5",
    messages=[
        {"role": "system", "content": "You are Kimi, an AI assistant created by Moonshot AI."},
        {"role": "user", "content": "What's the weather in Beijing?"}
    ],
    tools=tools,
    temperature=0.6
)

# Step 2: Model returns tool_calls
msg = response.choices[0].message
# msg.tool_calls[0].function.name == "get_weather"
# msg.tool_calls[0].function.arguments == '{"city": "Beijing"}'

# Step 3: Execute tool, send result back
messages.append(msg)  # assistant message with tool_calls
messages.append({
    "role": "tool",
    "tool_call_id": msg.tool_calls[0].id,
    "content": '{"weather": "Sunny", "temperature": "25°C"}'
})

# Step 4: Get final response
final = client.chat.completions.create(
    model="kimi-k2.5",
    messages=messages,
    tools=tools,
    temperature=0.6
)
```

### Self-hosted tool call parser
When self-hosting with vLLM or SGLang, you must use `--tool-call-parser kimi_k2` to enable proper tool call parsing.

## 7. Thinking Mode vs Instant

Based on available information, the distinction is **model name only**:
- `kimi-k2.5` — thinking/reasoning model (may use extended thinking internally)
- `kimi-k2.5-instant` — no thinking, faster responses

Previously mentioned parameters for thinking mode:
- `temperature=1.0, top_p=0.95` — may be required or recommended for the thinking model
- The thinking model may return reasoning traces in the response

**For the non-thinking model (Instruct):**
- Recommended `temperature=0.6`

## 8. Streaming

Standard SSE streaming is supported:

```python
response = client.chat.completions.create(
    model="kimi-k2.5",
    messages=messages,
    stream=True,
    temperature=0.6
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

SSE format follows OpenAI convention:
```
data: {"id":"...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0}]}

data: [DONE]
```

## 9. Anthropic-Compatible API

The HuggingFace page mentions:
> "We provide OpenAI/Anthropic-compatible API for you."
> "The Anthropic-compatible API maps temperature by `real_temperature = request_temperature * 0.6`"

This suggests the platform also offers an Anthropic-format endpoint. Details unknown but the temperature mapping is important if using that path.

## 10. Key Quirks & Notes

1. **Context length:** 128K tokens (not 256K as initially believed — the HF card and model summary both say 128K)
2. **Architecture:** Uses DeepSeek-V3 architecture internally (`DeepSeekV3CausalLM`), with `model_type: "kimi_k2"`
3. **Chat template:** Has special tokens for media (`<|media_begin|>`) but these are for the chat template format, not needed when using the API
4. **Default system prompt:** Was updated/modified in July 2025 updates; using the recommended one above is safest
5. **Multi-turn tool calls:** A bug was fixed in the chat template (2025-07-18) — use latest version
6. **Temperature:** Recommended 0.6 for Instruct. Don't go too low.
7. **Anthropic temp mapping:** If using Anthropic-compatible endpoint, your temperature gets multiplied by 0.6
8. **No vision in K2:** The open-source K2 is text-only despite media tokens in tokenizer

## 11. Integration Summary for OpenClaw/LiteLLM

For integrating via LiteLLM or similar OpenAI-compatible proxy:

```python
# Provider config
provider = "openai"  # Use generic OpenAI-compatible provider
base_url = "https://api.moonshot.ai/v1"
api_key = "sk-..."

# For non-thinking (fast):
model = "kimi-k2.5-instant"
temperature = 0.6

# For thinking (reasoning):
model = "kimi-k2.5"
temperature = 0.6  # or 1.0 if thinking mode requires it

# Features supported:
# ✅ System messages
# ✅ Tool/function calling (OpenAI format)
# ✅ Streaming (SSE)
# ✅ Multi-turn conversations
# ✅ name field in messages
```

## Sources

1. HuggingFace model card: https://huggingface.co/moonshotai/Kimi-K2-Instruct
2. GitHub repo: https://github.com/moonshotai/Kimi-K2
3. Deployment guide: https://github.com/moonshotai/Kimi-K2/blob/main/docs/deploy_guidance.md
4. API endpoint probing: `api.moonshot.ai/v1` returns OpenAI-compatible error format
5. Platform: https://platform.moonshot.ai

## Gaps / Needs Verification

- [ ] Exact model name strings on the hosted API (`kimi-k2.5` vs `kimi-k2` vs something else)
- [ ] Whether thinking mode has special parameters beyond model name
- [ ] Rate limits and pricing
- [ ] Whether the Anthropic-compatible endpoint has a different base URL
- [ ] Max output token limits
- [ ] Whether `kimi-k2.5` is actually a different model from open-source K2 or just a hosted alias
