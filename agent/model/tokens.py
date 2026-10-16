"""Request sizing; exact llama.cpp counting or a labelled portable estimate."""
import json

from .request_messages import model_image_ids, request_messages


def count_request_tokens(client, messages, tools, context, *, method="estimate", images=None, read_images=False):
    if method == "llama_cpp":
        outgoing = request_messages(messages, images, read_images=read_images)
        body = {"messages": outgoing, "add_generation_prompt": True}
        if tools:
            body["tools"] = tools
        prompt = client.post_json("/apply-template", body, context)["prompt"]
        return len(client.post_json("/tokenize", {"content": prompt, "add_special": False}, context)["tokens"])
    if method != "estimate":
        raise ValueError(f"Unknown token counter: {method}")
    # Do not count Base64 characters as text tokens. Image cost is approximate;
    # this is a trigger estimate, not a provider's hard context limit.
    payload = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False)
    return (len(payload.encode("utf-8")) + 2) // 3 + 4096 * len(model_image_ids(messages))
