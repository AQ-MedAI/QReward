import json
import asyncio
import os
from datetime import datetime
from typing import Dict, List, Optional


from qreward.client import OpenAIChatProxy


class RewardMultiturn:

    def __init__(self, base_url: str, api_key: str):
        self._openai_proxy = OpenAIChatProxy(
            base_url=base_url,
            api_key=api_key,
        )

    async def call_r1_model(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        request_timeout: int = 300,
    ):
        """
        Call r1 model to get reward score.

        :param messages: messages for r1 model
        :param temperature: temperature for r1 model
        :param request_timeout: request timeout for r1 model
        :return: R1 answer
        """
        model_name = "DeepSeek-R1"

        # Example: default chat_resp is completion.choices[0].message.content
        chat_resp = await self._openai_proxy.chat_completion(
            model=model_name,
            messages=messages,
            temperature=temperature,
            timeout=request_timeout,
            stream=False,
        )

        # Example: parse think and answer from chat_resp
        if "</think>" in chat_resp:
            think, answer = chat_resp.split("</think>", 1)
            think += "</think>"
            answer = answer.strip()
        else:
            think = ""
            answer = chat_resp.strip()

        return think, answer

    @staticmethod
    async def convert_messages_to_dialogue(
        messages: List[Dict[str, str]],
    ) -> str:
        dialogue = []

        # ignore your messages process
        # Here is a simple example for convert messages to dialogue
        for item in messages:
            if item["role"] == "user":
                dialogue.append(f"User: {item['content']}")
            elif item["role"] == "assistant":
                dialogue.append(f"Assistant: {item['content']}")
            elif item["role"] == "system":
                dialogue.append(f"System: {item['content']}")
            else:
                raise ValueError(f"role:{item['role']} is not supported!")

        return "\n".join(dialogue)

    async def generative_reward_r1(
        self,
        messages: List[Dict[str, str]],
    ) -> Optional[float]:

        async def get_single_reward(messages, retry_num=5):
            while retry_num > 0:
                try:
                    if isinstance(messages, list):
                        dialogue = self.convert_messages_to_dialogue(messages)
                    elif isinstance(messages, str):
                        dialogue = messages
                    else:
                        raise TypeError(f"messages:{messages} is not list or str!")

                    think, resp = await self.call_r1_model(
                        messages=[
                            {"role": "user", "content": dialogue},
                        ],
                    )

                    resp = json.loads(resp.replace("json", "").replace("```", ""))
                    score_list = [x["score"] for x in resp.values()]

                    # example for calculate reward score
                    return score_list[0] / 4 + score_list[1] / 2 + score_list[2] / 10
                except Exception:
                    retry_num -= 1
            return 0

        return await get_single_reward(messages, retry_num=5)

    async def calculate_rewards(
        self,
        messages: List[Dict[str, str]],
    ):
        pass


# Verl custom_reward_function entry point
async def compute_score(
    messages,
    ground_truth=None,
    extra_info=None,
):
    start_time = datetime.now().strftime("%H:%M:%S")
    calculator = RewardMultiturn(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    tasks = []
    for i in range(len(messages)):
        # insert task
        tasks.append(
            asyncio.create_task(
                calculator.calculate_rewards(
                    messages=messages[i],
                ),
            ),
        )

    results = await asyncio.gather(*tasks)
    end_time = datetime.now().strftime("%H:%M:%S")
    print(
        f"start_time: {start_time}, "
        f"end_time: {end_time}, "
        f"batch_size: {len(messages)}, "
        f"execution: {len(results)} / {len(messages)}"
    )
    return results
