# JARVIS - Phase 1: Basic Chat & LLM Integration

This phase sets up the basic structure for a conversational AI agent (JARVIS) with the following capabilities:

*   Respond to user text using an LLM (local or API).
*   Maintain a simple in-memory conversation history (no persistence yet).

## Project Structure

```
OS/
├── config.json          # Configuration for LLM and conversation settings
├── run.py               # Entry point to run the JARVIS agent interactively
├── test_agent.py        # Simple test script to demonstrate the agent
└── src/
    └── agent.py         # Core Agent class implementation
```

## Configuration (`config.json`)

```json
{
  "llm": {
    "provider": "openai",   // LLM provider (e.g., openai, huggingface, local)
    "model": "gpt-3.5-turbo", // Model name
    "api_key": "",          // API key for the LLM service (required for real responses)
    "temperature": 0.7,     // Sampling temperature
    "max_tokens": 150       // Maximum tokens in response
  },
  "conversation": {
    "max_history": 10       // Number of conversation turns to remember
  }
}
```

## Usage

1.  **Set up your API key** (if using a real LLM):
    Edit `config.json` and add your API key to the `api_key` field.

2.  **Run the agent interactively**:
    ```bash
    python run.py
    ```
    Then chat with JARVIS in the console. Type `exit` or `quit` to end the session.

3.  **Run the test script**:
    ```bash
    python test_agent.py
    ```
    This demonstrates the agent's functionality with mock responses (when no API key is provided).

## How It Works

- The `Agent` class in `src/agent.py` loads the configuration, manages conversation history, and provides a method to get responses from the LLM.
- If no API key is provided, the agent returns a mock response for demonstration purposes.
- When an API key is provided, the agent is ready to integrate with the specified LLM service (currently set up for OpenAI's API as an example).

## Next Steps

This completes Phase 1. Future phases could include:
- Adding persistence to conversation history.
- Implementing voice input/output.
- Adding skills or tool use (e.g., accessing files, web search).
- Improving the LLM integration with more providers and settings.

Let me know if you'd like to proceed to the next phase or make any adjustments!