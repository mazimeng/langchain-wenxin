"""wrapper wenxin client"""
import json
import logging
import time
from typing import Any, AsyncGenerator, Generator, List, Optional, Tuple

import aiohttp
import requests
import sseclient

logger = logging.getLogger(__name__)


class WenxinClient:
    WENXIN_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    WENXIN_CHAT_URL = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{endpoint}"
    WENXIN_EMBEDDINGS_URL = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/embeddings/{model}"

    def __init__(self, baidu_api_key: str, baidu_secret_key: str,
                 request_timeout: Optional[int] = None):
        self.baidu_api_key = baidu_api_key
        self.baidu_secret_key = baidu_secret_key
        self.request_timeout = request_timeout

        self.access_token = ""
        self.access_token_expires = 0

    def completions_url(self, model: str) -> str:
        """Get the URL for the completions endpoint."""
        if model in ["eb-instant", "ernie-bot-turbo"]:
            endpoint = "eb-instant"
        elif model in  ["wenxin", "ernie-bot"]:
            endpoint = "completions"
        else:
            endpoint = model
        return self.WENXIN_CHAT_URL.format(endpoint=endpoint)

    def grant_token(self) -> str:
        """Grant access token from Baidu Cloud."""
        now_timestamp = int(time.time())
        if self.access_token and now_timestamp < self.access_token_expires:
            return self.access_token

        r = requests.get(
            url=self.WENXIN_TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": self.baidu_api_key,
                "client_secret": self.baidu_secret_key,
            },
            timeout=5,
        )
        r.raise_for_status()
        response = r.json()
        self.access_token = response["access_token"]
        self.access_token_expires = now_timestamp + response["expires_in"]
        return self.access_token

    async def async_grant_token(self) -> str:
        """Async grant access token from Baidu Cloud."""
        now_timestamp = int(time.time())
        if self.access_token and now_timestamp < self.access_token_expires:
            return self.access_token

        # Here we are using aiohttp to make the request.
        # It is used in a context manager fashion to ensure cleanup.
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=self.WENXIN_TOKEN_URL,
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.baidu_api_key,
                    "client_secret": self.baidu_secret_key,
                },
                timeout=5,
            ) as r:
                r.raise_for_status()
                response = await r.json()

        self.access_token = response["access_token"]
        self.access_token_expires = now_timestamp + response["expires_in"]
        return self.access_token

    @staticmethod
    def construct_message(prompt: str, history: List[Tuple[str, str]]) -> List[Any]:
        messages = []
        for human, ai in history:
            messages.append({"role": "user", "content": human})
            messages.append({"role": "assistant", "content": ai})
        messages.append({"role": "user", "content": prompt})
        return messages

    def completion(self, model: str, prompt: str, history: List[Tuple[str, str]], **params) -> Any:
        """Call out to Wenxin's generate endpoint.

        Args:
            model: The model to use.
            prompt: The prompt to pass into the model.
            **params: Additional parameters to pass to the API.

        Returns:
            The response generated by the model.
        """
        params["messages"] = self.construct_message(prompt, history)
        params["stream"] = False
        url = self.completions_url(model)
        logger.debug(f"call wenxin: url[{url}], params[{params}]")
        r = requests.post(
            url=url,
            params={"access_token": self.grant_token()},
            json=params,
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        response = r.json()
        error_code = response.get("error_code", 0)
        if error_code != 0:
            error_msg = response.get("error_msg", "Unknown error")
            msg = f"call wenxin failed, error_code: {error_code}, error_msg: {error_msg}"
            raise Exception(msg)

        return response

    async def acompletion(self, model: str, prompt: str, history: List[Tuple[str, str]], **params) -> Any:
        """Async all out to Wenxin's generate endpoint.

        Args:
            model: The model to use.
            prompt: The prompt to pass into the model.
            **params: Additional parameters to pass to the API.

        Returns:
            The response generated by the model.
        """
        import aiohttp
        params["messages"] = self.construct_message(prompt, history)
        params["stream"] = False
        url = self.completions_url(model)
        logger.debug(f"async call wenxin: url[{url}], params[{params}]")

        # Here we are using aiohttp to make the request.
        # It is used in a context manager fashion to ensure cleanup.
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=url,
                params={"access_token": await self.async_grant_token()},
                json=params,
                timeout=self.request_timeout,
            ) as r:
                r.raise_for_status()
                response = await r.json()

        error_code = response.get("error_code", 0)
        if error_code != 0:
            error_msg = response.get("error_msg", "Unknown error")
            msg = f"call wenxin failed, error_code: {error_code}, error_msg: {error_msg}"
            raise Exception(msg)

        return response

    def completion_stream(self, model: str, prompt: str,
                          history: List[Tuple[str, str]], **params) -> Generator:
        """Call out to Wenxin's generate endpoint.

        Args:
            model: The model to use.
            prompt: The prompt to pass into the model.
            **params: Additional parameters to pass to the API.

        Returns:
            Generator: The response generated by the model.
        """
        params["messages"] = self.construct_message(prompt, history)
        params["stream"] = True
        url = self.completions_url(model)
        logger.debug(f"call wenxin: url[{url}], params[{params}]")
        r = requests.post(
            url=self.completions_url(model),
            params={"access_token": self.grant_token()},
            json=params,
            timeout=self.request_timeout,
            stream=True,
        )
        r.raise_for_status()
        if not r.headers.get("Content-Type", "").startswith("text/event-stream"):
            response = r.json()
            error_code = response.get("error_code", 0)
            if error_code != 0:
                error_msg = response.get("error_msg", "Unknown error")
                msg = f"call wenxin failed, error_code: {error_code}, error_msg: {error_msg}"
                raise Exception(msg)
            return response

        client = sseclient.SSEClient(r) # type: ignore
        for event in client.events():
            data = json.loads(event.data)
            yield data

    async def acompletion_stream(self, model: str, prompt: str,
                          history: List[Tuple[str, str]], **params) -> AsyncGenerator:
        """Async call out to Wenxin's generate endpoint.

        Args:
            model: The model to use.
            prompt: The prompt to pass into the model.
            **params: Additional parameters to pass to the API.

        Returns:
            Generator: The response generated by the model.
        """
        params["messages"] = self.construct_message(prompt, history)
        params["stream"] = True
        url = self.completions_url(model)
        logger.debug(f"call wenxin: url[{url}], params[{params}]")

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url=self.completions_url(model),
                params={"access_token": await self.async_grant_token()},
                json=params,
            ) as r:
                r.raise_for_status()
                if not r.headers.get("Content-Type", "").startswith("text/event-stream"):
                    response = await r.json()
                    error_code = response.get("error_code", 0)
                    if error_code != 0:
                        error_msg = response.get("error_msg", "Unknown error")
                        msg = f"call wenxin failed, error_code: {error_code}, error_msg: {error_msg}"
                        raise Exception(msg)
                    yield response

                async def read(content):
                    data = b""
                    async for chunk in content:
                        data += chunk
                        if data.endswith((b"\r\r", b"\n\n", b"\r\n\r\n")):
                            yield data
                            data = b""
                    if data:
                        yield data

                async for line in read(r.content):
                    line_decoded = line.decode("utf-8")
                    if not line_decoded.startswith("data:"):
                        continue
                    event_data = line_decoded[5:].strip()
                    data = json.loads(event_data)
                    yield data

    def embed(self, model: str, texts: List[str], truncate: Optional[str] = None):
        """Call out to Wenxin's embedding endpoint."""
        url = self.WENXIN_EMBEDDINGS_URL.format(model=model)
        batch_size_limit = 16
        chars_limit = 384
        if len(texts) > batch_size_limit:
            err = "texts batch_size must less than 16."
            raise ValueError(err)
        sentences = []
        for t in texts:
            if truncate == "START":
                sentences.append(t[-chars_limit:])
            elif truncate == "END":
                sentences.append(t[:chars_limit])
            else:
                if len(t) > chars_limit:
                    err = f"input text length {len(t)} is greater than 384."
                    raise ValueError(err)
                sentences.append(t)
        payload = {
            "input": sentences,
        }
        r = requests.post(
            url,
            params={"access_token": self.grant_token()},
            json=payload,
            timeout=self.request_timeout,
            )
        r.raise_for_status()
        response = r.json()
        error_code = response.get("error_code", 0)
        if error_code != 0:
            error_msg = response.get("error_msg", "Unknown error")
            msg = f"call wenxin failed, error_code: {error_code}, error_msg: {error_msg}, input {input}"
            raise Exception(msg)

        return response
