from aio_pika import connect_robust, IncomingMessage, Message
from aio_pika.patterns import RPC
import asyncio
import uuid
from . import MythicCommandBase
import json
import base64
import pathlib
import sys
from .config import settings

connection = None
rpc = None

class RPCResponse:
    def __init__(self, resp: dict):
        self._raw_resp = resp
        if resp["status"] == "success":
            self.status = MythicCommandBase.MythicStatus.Success
            self.response = resp["response"] if "response" in resp else ""
            self.error = None
        else:
            self.status = MythicCommandBase.MythicStatus.Error
            self.error = resp["error"]
            self.response = None

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        self._status = status

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, error):
        self._error = error

    @property
    def response(self):
        return self._response

    @response.setter
    def response(self, response):
        self._response = response

    def __str__(self):
        return json.dumps(self._raw_resp)


class MythicBaseRPC:
    async def connect(self):
        global connection
        global rpc
        if connection is None:
            connection = await connect_robust(
                host=settings.get("host", "127.0.0.1"),
                login=settings.get("username", "mythic_user"),
                password=settings.get("password", "mythic_password"),
                virtualhost=settings.get("virtual_host", "mythic_vhost"),       
            )
            channel = await connection.channel()
            try:
                rpc = await RPC.create(channel)
            except Exception as e:
                print("Failed to create rpc\n" + str(e))
                sys.stdout.flush()
        return self


class MythicRPC(MythicBaseRPC):
    async def get_functions(self) -> RPCResponse:
        global rpc
        await self.connect()
        try:
            output = await rpc.proxy.get_rpc_functions()
            return RPCResponse(output)
        except Exception as e:
            print(str(sys.exc_info()[-1].tb_lineno) +str(e))
            sys.stdout.flush()
            return RPCResponse({"status": "error", "error": "Failed to find function and call it in RPC, does it exist?\n" + str(e)})

    async def execute(self, function_name: str, **func_kwargs) -> RPCResponse:
        global rpc
        await self.connect()
        try:
            func = getattr(rpc.proxy, function_name)
            if func is not None and callable(func):
                output = await func(**func_kwargs)
            else:
                output = await rpc.call(function_name, kwargs=dict(**func_kwargs))
            return RPCResponse(output)
        except Exception as e:
            print(str(sys.exc_info()[-1].tb_lineno) +str(e))
            sys.stdout.flush()
            return None