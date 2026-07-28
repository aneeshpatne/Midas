
from langchain_deepseek import ChatDeepSeek

deepseek_model = ChatDeepSeek(
    model="deepseek-v4-pro",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # api_key="...",
    # other params...
)
