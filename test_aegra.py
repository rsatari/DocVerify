import asyncio
from langgraph_sdk import get_client

async def main():
    client = get_client(url="http://localhost:8000")

    assistants = await client.assistants.search(graph_id="agent")
    assistant = assistants[0]
    print(f"Using assistant: {assistant['assistant_id']}")

    thread = await client.threads.create()
    print(f"Thread: {thread['thread_id']}")
    print("Running full pipeline... (this takes 15-25 minutes)")

    result = await client.runs.wait(
        thread_id=thread["thread_id"],
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"type": "human", "content": "evaluate"}]},
    )

    for msg in result.get("messages", []):
        if msg.get("type") == "ai":
            print("\n" + msg["content"])

asyncio.run(main())
