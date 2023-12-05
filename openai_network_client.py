from http.client import HTTPSConnection, HTTPResponse
from typing import Optional, List, Dict
from .cacher import Cacher
import sublime
import json
from .errors.OpenAIException import ContextLengthExceededException, UnknownException
from .assistant_settings import AssistantSettings, PromptMode
from base64 import b64encode

class NetworkClient():

    def __init__(self, settings: sublime.Settings) -> None:
        self.settings = settings
        self.headers = {
            'Content-Type': "application/json",
            'Authorization': f'Bearer {self.settings.get("token")}',
            'cache-control': "no-cache",
        }

        proxy_settings = self.settings.get('proxy')
        if isinstance(proxy_settings, dict):
            address = proxy_settings.get('address')
            port = proxy_settings.get('port')
            proxy_username = proxy_settings.get('username')
            proxy_password = proxy_settings.get('password')
            proxy_auth = b64encode(bytes(f'{proxy_username}:{proxy_password}', 'utf-8')).strip().decode('ascii')
            headers = {'Proxy-Authorization': f'Basic {proxy_auth}'} if len(proxy_auth) > 0 else {}
            if address and len(address) > 0 and port:

                self.connection = HTTPSConnection(
                    host=address,
                    port=port,
                )
                self.connection.set_tunnel(
                    "api.openai.com",
                    headers=headers
                )
            else:
                self.connection = HTTPSConnection("api.openai.com")

    def prepare_payload(self, assitant_setting: AssistantSettings, messages: List[Dict[str, str]]):
        if assitant_setting.prompt_mode == PromptMode.panel.value:
            ## FIXME:  This is error prone and should be rewritten
            #  Messages shouldn't be written in cache and passing as an attribute, should use either one.
            internal_messages = Cacher().read_all() + messages
        internal_messages.append({"role": "system", "content": assitant_setting.assistant_role})

        return json.dumps({
            # Todo add uniq name for each output panel (e.g. each window)
            "messages": internal_messages,
            "model": assitant_setting.chat_model,
            "temperature": assitant_setting.temperature,
            "max_tokens": assitant_setting.max_tokens,
            "top_p": assitant_setting.top_p,
            "stream": True
        })

    def prepare_request(self, json_payload):
        self.connection.request(method="POST", url="/v1/chat/completions", body=json_payload, headers=self.headers)

    def prepare_request_deprecated(self, gateway, json_payload):
        self.connection.request(method="POST", url=gateway, body=json_payload, headers=self.headers)

    def execute_response(self) -> Optional[HTTPResponse]:
        return self._execute_network_request()

    def _execute_network_request(self) -> Optional[HTTPResponse]:
        response = self.connection.getresponse()
        # handle 400-499 client errors and 500-599 server errors
        if 400 <= response.status < 600:
            error_object = response.read().decode('utf-8')
            error_data = json.loads(error_object)
            if error_data.get('error', {}).get('code') == 'context_length_exceeded':
                raise ContextLengthExceededException(error_data['error']['message'])
            raise UnknownException(error_data.get('error').get('message'))
        return response
