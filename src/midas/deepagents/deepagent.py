from deepagents import create_deep_agent

from .model import deepseek_model
from .tools import MIDAS_TOOLS

agent = create_deep_agent(model=deepseek_model, tools=MIDAS_TOOLS)
