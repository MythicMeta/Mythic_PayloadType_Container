#!/usr/bin/env python3
import aio_pika
import os
import sys
import traceback
import base64
import json
import asyncio
import socket
from . import MythicCommandBase
from . import PayloadBuilder
from pathlib import Path
from importlib import import_module, invalidate_caches
from .config import settings
from functools import partial

# set the global hostname variable
hostname = ""
output = ""
exchange = None
channel = None
queue = None
connection = None
operating_environment = "production"
container_files_path = ""

container_version = "11"
PyPi_version = "0.1.0"


def print_flush(msg, override: bool = False):
    global operating_environment
    if operating_environment in ["development", "testing", "staging"] or override:
        print(msg)
        sys.stdout.flush()


def import_all_agent_functions():
    import glob

    # Get file paths of all modules.
    modules = glob.glob("agent_functions/*.py")
    invalidate_caches()
    for x in modules:
        if not x.endswith("__init__.py") and x[-3:] == ".py":
            module = import_module("agent_functions." + Path(x).stem)
            for el in dir(module):
                if "__" not in el:
                    globals()[el] = getattr(module, el)


async def send_status(message="", command="", status="", username="", reference_id=""):
    global exchange
    # status is success or error
    try:
        message_body = aio_pika.Message(message.encode())
        # Sending the message
        await exchange.publish(
            message_body,
            routing_key="pt.status.{}.{}.{}.{}.{}.{}".format(
                hostname, command, reference_id, status, username, container_version
            ),
        )
    except Exception as e:
        print_flush("Exception in send_status: {}".format(str(traceback.format_exc())))
        sys.exit(1)


async def initialize_task(command_class: MythicCommandBase.CommandBase, message_json: dict, command: str, reference_id: str, username: str) -> MythicCommandBase.MythicTask:
    task = MythicCommandBase.MythicTask(
        message_json["task"],
        args=command_class.argument_class(command_line=message_json["params"], tasking_location=message_json["tasking_location"]),
    )
    try:
        # if tasking came from the command_line or an unknown source, call parse_arguments to deal with unknown text
        if task.args.tasking_location == "command_line":
            await task.args.parse_arguments()
        else:
            # tasking didn't come from command line, so if we have a special function to parse dictionary entries, use it
            if hasattr(task.args, 'parse_dictionary') and callable(task.args.parse_dictionary):
                # if we got tasking from a modal popup or from tab complete, then the task.args.command_line is a dictionary
                await task.args.parse_dictionary(json.loads(message_json['params']))
            else:
                # otherwise, we still just have to call the parse_arguments function
                # this way we don't break any existing command parsing
                await task.args.parse_arguments()
    except Exception as pa:
        message = {"task": task.to_json(), 
            "message": f"[-] {hostname} failed to parse arguments for {message_json['command']}: \n" + str(traceback.format_exc())}
        await send_status(
            message=json.dumps(message),
            command=command,
            status="parse_arguments_error",
            reference_id=reference_id,
            username=username
        )
        return None
    try:
        await task.args.verify_required_args_have_values()
    except Exception as va:
        message = {"task": task.to_json(), 
            "message": f"[-] {message_json['command']} has arguments with invalid values: \n" + str(traceback.format_exc())}
        await send_status(
            message=json.dumps(message),
            command=command,
            status="verify_arguments_error",
            reference_id=reference_id,
            username=username
        )
        return None
    task.parameter_group_name = task.args.get_parameter_group_name()
    return task

async def callback(message: aio_pika.IncomingMessage):
    global hostname
    global container_files_path
    async with message.process():
        # messages of the form: pt.task.PAYLOAD_TYPE.command
        pieces = message.routing_key.split(".")
        command = pieces[3]
        username = pieces[5]
        reference_id = pieces[4]
        if command == "create_payload_with_code":
            try:
                # pt.task.PAYLOAD_TYPE.create_payload_with_code.UUID
                message_json = json.loads(
                    message.body, strict=False
                )
                # go through all the data from rabbitmq to make the proper classes
                c2info_list = []
                for c2 in message_json["c2_profile_parameters"]:
                    params = c2.pop("parameters", None)
                    c2info_list.append(
                        PayloadBuilder.C2ProfileParameters(parameters=params, c2profile=c2)
                    )
                commands = PayloadBuilder.CommandList(message_json["commands"])
                for cls in PayloadBuilder.PayloadType.__subclasses__():
                    agent_builder = cls(
                        uuid=message_json["uuid"],
                        agent_code_path=Path(container_files_path),
                        c2info=c2info_list,
                        selected_os=message_json["selected_os"],
                        commands=commands,
                        wrapped_payload=message_json["wrapped_payload"],
                    )
                try:
                    await agent_builder.set_and_validate_build_parameters(
                        message_json["build_parameters"]
                    )
                    build_resp = await agent_builder.build()
                except Exception as b:
                    resp_message = {
                        "status": "error",
                        "build_message": "",
                        "build_stdout": "",
                        "build_stderr": "Error in agent creation: " + str(traceback.format_exc()),
                        "payload": "",
                    }
                    await send_status(
                        message=json.dumps(resp_message),
                        command="create_payload_with_code",
                        status="error",
                        reference_id=reference_id,
                        username=username,
                    )
                    return
                # we want to capture the build message as build_resp.get_build_message()
                # we also want to capture the final values the agent used for creating the payload, so collect them
                build_instances = agent_builder.get_build_instance_values()
                resp_message = {
                    "status": build_resp.get_status(),
                    "build_message": build_resp.get_build_message(),
                    "build_stdout": build_resp.get_build_stdout(),
                    "build_stderr": build_resp.get_build_stderr(),
                    "build_parameter_instances": build_instances,
                    "payload": base64.b64encode(build_resp.get_payload()).decode(
                        "utf-8"
                    ),
                }
                await send_status(
                    message=json.dumps(resp_message),
                    command="create_payload_with_code",
                    reference_id=reference_id,
                    status="success",
                    username=username,
                )

            except Exception as e:
                resp_message = {
                    "status": "error",
                    "build_message": "",
                    "build_stdout": "",
                    "build_stderr": str(traceback.format_exc()),
                    "payload": "",
                }
                await send_status(
                    message=json.dumps(resp_message),
                    command="create_payload_with_code",
                    status="error",
                    reference_id=reference_id,
                    username=username,
                )
        elif command == "command_transform":
            try:
                task = None
                # pt.task.PAYLOAD_TYPE.command_transform.taskID
                message_json = json.loads(
                    message.body, strict=False
                )
                final_task = None
                if "tasking_location" not in message_json:
                    message_json["tasking_location"] = "command_line"
                for cls in MythicCommandBase.CommandBase.__subclasses__():
                    if getattr(cls, "cmd") == message_json["command"]:
                        Command = cls(Path(container_files_path))
                        task = await initialize_task(command_class=Command, message_json=message_json, command=command, reference_id=reference_id, username=username)
                        if task is None:
                            return
                        if 'opsec_class' in dir(Command) and Command.opsec_class is not None and callable(Command.opsec_class.opsec_pre):
                            # the opsec_pre function is defined
                            if task.opsec_pre_blocked is None:
                                # this means we haven't run the function to see if it's been blocked or not
                                #   opsec_pre updates task itself
                                try:
                                    await Command.opsec_class().opsec_pre(task)
                                except Exception as ct:
                                    message = {"task": task.to_json()}
                                    if type(ct).__name__ == "Exception":
                                        # we're looking at a generic exception, probably one raised on purpose by the function
                                        message["message"] = f"[-] {hostname} ran into an error processing an opsec_pre check for {message_json['command']}: \n" + str(ct)
                                        await send_status(
                                            message=json.dumps(message),
                                            command="command_transform",
                                            status="opsec_pre_error",
                                            reference_id=reference_id,
                                            username=username
                                        )
                                    else:
                                        # we're probably looking at an actual error
                                        message["message"] = f"[-] {hostname} ran into an error processing and opsec_pre check for {message_json['command']}: \n" + str(ct) + "\n" + str(traceback.format_exc())
                                        await send_status(
                                            message=json.dumps(message),
                                            command="command_transform",
                                            status="opsec_pre_error",
                                            reference_id=reference_id,
                                            username=username
                                        )
                                    return
                                if task.opsec_pre_blocked is True:
                                    # the opsec_pre function decided to block the task
                                    if not task.opsec_pre_bypassed:
                                        # and not provide a bypass
                                        # send our current result and indicate we were blocked at opsec_pre
                                        message = {"task": task.to_json(), 
                                        "message": ""}
                                        await send_status(
                                            message=json.dumps(message),
                                            command="command_transform",
                                            status="opsec_pre_success",
                                            reference_id=reference_id,
                                            username=username
                                        )
                                        return
                                    # we threw up a block, but also set bypassed to true, so continue on
                            elif task.opsec_pre_blocked is True and not task.opsec_pre_bypassed:
                                # we already sent our opsec_pre data, we're blocked and not bypassed, just return
                                return
                        try:
                            final_task = await Command.create_tasking(task)
                        except Exception as ct:
                            message = {"task": task.to_json()}
                            if type(ct).__name__ == "Exception":
                                # we're looking at a generic exception, probably one raised on purpose by the function
                                message["message"] = f"[-] {hostname} ran into an error processing {message_json['command']}: \n" + str(ct)
                                await send_status(
                                    message=json.dumps(message),
                                    command="command_transform",
                                    status="create_tasking_error",
                                    reference_id=reference_id,
                                    username=username
                                )
                            else:
                                # we're probably looking at an actual error
                                message["message"] = f"[-] {hostname} ran into an error processing {message_json['command']}: \n" + str(ct) + "\n" + str(traceback.format_exc())
                                await send_status(
                                    message=json.dumps(message),
                                    command="command_transform",
                                    status="create_tasking_error",
                                    reference_id=reference_id,
                                    username=username
                                )
                            return
                        if "opsec_class" in dir(Command) and Command.opsec_class is not None and callable(Command.opsec_class.opsec_post):
                            # the opsec_post function is defined
                            if task.opsec_post_blocked is None:
                                # this means we haven't run the function to see if it's been blocked or not
                                #   opsec_post updates task itself
                                try:
                                    await Command.opsec_class().opsec_post(task)
                                except Exception as ct:
                                    message = {"task": task.to_json()}
                                    if type(ct).__name__ == "Exception":
                                        # we're looking at a generic exception, probably one raised on purpose by the function
                                        message["message"] = f"[-] {hostname} ran into an error processing an opsec_post check for {message_json['command']}: \n" + str(ct)
                                        await send_status(
                                            message=json.dumps(message),
                                            command="command_transform",
                                            status="opsec_post_error",
                                            reference_id=reference_id,
                                            username=username
                                        )
                                    else:
                                        # we're probably looking at an actual error
                                        message["message"] = f"[-] {hostname} ran into an error processing an opsec_post check for {message_json['command']}: \n" + str(ct) + "\n" + str(traceback.format_exc())
                                        await send_status(
                                            message=json.dumps(message),
                                            command="command_transform",
                                            status="opsec_post_error",
                                            reference_id=reference_id,
                                            username=username
                                        )
                                    return
                                if task.opsec_post_blocked and not task.opsec_post_bypassed:
                                    # send the results of the check
                                    message = {"task": task.to_json(), "message": ""}
                                    await send_status(
                                        message=json.dumps(message),
                                        command="command_transform",
                                        status="opsec_post_success",
                                        reference_id=reference_id,
                                        username=username
                                    )
                                    return
                        message = {"task": task.to_json(), "message": ""}
                        await send_status(
                            message=json.dumps(message),
                            command="command_transform",
                            status=final_task.status if final_task.status != "preprocessing" else "success",
                            reference_id=reference_id,
                            username=username
                        )
                        break
                if final_task is None:
                    message = {"task": task.to_json(),  "message": "Failed to find class where command_name = " + message_json["command"]}
                    await send_status(
                        message=json.dumps(message),
                        command="command_transform",
                        status="error_not_found",
                        reference_id=reference_id,
                        username=username
                    )
            except Exception as e:
                message = {"task": task.to_json() if task is not None else message_json["task"], "message": "[-] Mythic error while creating/running create_tasking: \n" + str(e)}
                await send_status(
                    message=json.dumps(message),
                    command="command_transform",
                    status="general_error",
                    reference_id=reference_id,
                    username=username
                )
                return
        elif command == "sync_classes":
            await sync_classes(reference_id)
            pass
        elif command == "process_container":
            try:
                # pt.task.PAYLOAD_TYPE.command_transform.taskID
                message_json = json.loads(message.body)
                final_task = None
                for cls in MythicCommandBase.CommandBase.__subclasses__():
                    if getattr(cls, "cmd") == message_json["command"]:
                        Command = cls(Path(container_files_path))
                        task = await initialize_task(command_class=Command, message_json=message_json, command=command, reference_id=reference_id, username=username)
                        if task is None:
                            return
                        agentResponse = MythicCommandBase.AgentResponse(task=task, response=message_json["response"])
                        await Command.process_response(agentResponse)
                        break
            except Exception as e:
                await send_status(
                    message="[-] Error while running process_response: \n" + str(e),
                    command="process_container",
                    status="error",
                    reference_id=reference_id,
                    username=username
                )
                return
        elif command == "exit_container":
            print_flush("[*] Got exit container command, exiting!", override=True)
            print_flush("[*] Container versions and information can be found at: https://docs.mythic-c2.net/customizing/payload-type-development/container-syncing#current-payloadtype-versions",override=True)
            print_flush("[*] If this is unexpected, check the Mythic UI for logs as to why this container is tasked to exit", override=True)
            sys.exit(0)
        elif command == "task_callback_function":
            try:
                # pt.task.PAYLOAD_TYPE.task_callback_function.taskID
                message_json = json.loads(
                    message.body, strict=False
                )
                task = None
                final_task = None
                for cls in MythicCommandBase.CommandBase.__subclasses__():
                    if getattr(cls, "cmd") == message_json["command"]:
                        Command = cls(Path(container_files_path))
                        task = await initialize_task(command_class=Command, message_json=message_json, command=command, reference_id=reference_id, username=username)
                        if task is None:
                            return
                        if hasattr(Command, message_json["function_name"]) and callable(getattr(Command, message_json["function_name"])):
                            # the message_json["function_name"] function is defined in the Command.callback_class and is callable
                            try:
                                final_task = await getattr(Command, message_json["function_name"])(task, message_json["subtask"], message_json["subtask_group_name"])
                            except Exception as fn:
                                message = {"task": task.to_json(),  
                                "updating_task": message_json["updating_task"],
                                "updating_piece": message_json["updating_piece"],
                                "message": f"[-] {hostname} hit an exception in callback function, {message_json['function_name']} for {message_json['command']}: \n" + str(traceback.format_exc())}
                                await send_status(
                                    message=json.dumps(message),
                                    command="task_callback_function",
                                    status="handler_error",
                                    reference_id=reference_id,
                                    username=username
                                )
                                return
                            # send the results of the check
                            message = {"task": final_task.to_json(),
                                "updating_task": message_json["updating_task"],
                                "updating_piece": message_json["updating_piece"],
                                "message": ""}
                            await send_status(
                                message=json.dumps(message),
                                command="task_callback_function",
                                status=final_task.status if final_task.status != "preprocessing" else "success",
                                reference_id=reference_id,
                                username=username
                            )
                        else:
                            message = {"task": task.to_json(), 
                            "updating_task": message_json["updating_task"],
                            "updating_piece": message_json["updating_piece"],
                            "message": f"[-] {hostname} failed to find callback function, {message_json['function_name']} for {message_json['command']}"}
                            await send_status(
                                message=json.dumps(message),
                                command="task_callback_function",
                                status="not_found_error",
                                reference_id=reference_id,
                                username=username
                            )
                            return
            except Exception as e:
                message = {"task": task.to_json() if task is not None else message_json["task"],
                    "message": "[-] Mythic error while creating/running task_callback_function: \n" + str(traceback.format_exc())}
                await send_status(
                    message=json.dumps(message),
                    command="task_callback_function",
                    status="generic_error",
                    reference_id=reference_id,
                    username=username
                )
                return
        else:
            print("Unknown command: {}".format(command))


async def sync_classes(reference_id: str = ""):
    try:
        commands = {}
        payload_type = {}
        print_flush("[*] About to import all of the agent's functions")
        import_all_agent_functions()
        print_flush("[*] Agent function import completed. Now to parse the Payload and Command information")
        for cls in PayloadBuilder.PayloadType.__subclasses__():
            payload_type = cls(agent_code_path=Path(container_files_path)).to_json()
            break
        for cls in MythicCommandBase.CommandBase.__subclasses__():
            commands[cls.cmd] = cls(Path(container_files_path)).to_json()
        payload_type["commands"] = commands
        print_flush("[*] Payload and Command parsing completed. Now sending sync to Mythic")
        await send_status(json.dumps(payload_type), command="sync_classes", status="success", username="", reference_id=reference_id)
    except Exception as e:
        print_flush("[-] Failed to sync classes, exiting container!\n" + str(traceback.format_exc()), override=True)
        await send_status(
            message="Error while syncing info: " + str(traceback.format_exc()),
            command="sync_classes",
            status="error",
            username="",
            reference_id=reference_id
        )
        sys.exit(1)


async def connect_to_rabbitmq():
    global hostname
    global exchange
    global channel
    global queue
    global connection
    global container_files_path
    if queue is not None:
        return
    hostname = settings.get("name", "hostname")
    if hostname == "hostname":
        hostname = socket.gethostname()
        print_flush("[*] Hostname specified as default 'hostname' value, thus will fetch and use the current hostname of the Docker container or computer\n", override=True)
    print_flush("[*] Setting hostname (which should match payload type name exactly) to: " + hostname, override=True)
    container_files_path = os.path.abspath(settings.get("container_files_path", "/Mythic/"))
    if not os.path.exists(container_files_path):
        print_flush(f"[-] Specified mythic_container_files_path, {container_files_path},  does not exist", override=True)
        print_flush(f"[-] If this isn't in a Docker container, then this should be the path to your PayloadType folder", override=True)
        print_flush(f"[-] ex: C:\\Users\\username\\Desktop\\AgentName\\", override=True)
        print_flush(f"[-] ex: /Users/username/AgentName/", override=True)
        os.exit(1)
    while True:
        try:
            print_flush("[*] Trying to connect to rabbitmq at: " + settings.get("host", "127.0.0.1") + ":" + str(settings.get("port", 5672)),  override=True)
            connection = await aio_pika.connect_robust(
                host=settings.get("host", "127.0.0.1"),
                port=settings.get("port", 5672),
                login=settings.get("username", "mythic_user"),
                password=settings.get("password", "mythic_password"),
                virtualhost=settings.get("virtual_host", "mythic_vhost"),
            )
            print_flush("[*] connecting to channel, then declaring exchange")
            channel = await connection.channel()
            # declare our heartbeat exchange that everybody will publish to, but only the mythic server will are about
            print_flush("[*] declaring exchange, then declaring queue")
            exchange = await channel.declare_exchange(
                "mythic_traffic", aio_pika.ExchangeType.TOPIC
            )
            # get a random queue that only the mythic server will use to listen on to catch all heartbeats
            queue = await channel.declare_queue(hostname + "_tasking")
            print_flush("[*] binding to exchange, then ready to go")
            # bind the queue to the exchange so we can actually catch messages
            await queue.bind(
                exchange="mythic_traffic", routing_key="pt.task.{}.#".format(hostname)
            )

            # just want to handle one message at a time so we can clean up and be ready
            await channel.set_qos(prefetch_count=int(settings.get("queue_prefetch", "10")))
            print_flush("[+] Ready to go!",  override=True)
            return
        except Exception as e:
            print_flush(str(e))
            await asyncio.sleep(2)
            continue


async def heartbeat():
    global exchange
    global queue
    global channel
    global hostname
    try:
        if exchange is not None:
            while True:
                try:
                    queue = await channel.get_queue(hostname + "_tasking")
                    await exchange.publish(
                        aio_pika.Message("".encode()),
                        routing_key="pt.heartbeat.{}.{}.{}".format(hostname, container_version, str(queue.declaration_result.consumer_count)),
                    )
                    await asyncio.sleep(10)
                except Exception as e:
                    print_flush("[*] heartbeat - exception in heartbeat message loop:\n " + str(traceback.format_exc()), override=True)
                    sys.exit(1)
        else:
            print_flush("[-] Failed to process heartbeat functionality, exiting container:\n " + str(traceback.format_exc()), override=True)
            sys.exit(1)
    except Exception as h:
        print_flush("[-] Failed to process heartbeat functionality, exiting container:\n " + str(traceback.format_exc()), override=True)
        sys.exit(1)


async def mythic_service():
    global hostname
    global queue

    try:
        print_flush("[*] mythic_service - Waiting for messages in mythic_service with version {}.".format(container_version), override=True)
        task = queue.consume(callback)
        print_flush("[*] mythic_service - total instances of {} container running: {}".format(hostname, queue.declaration_result.consumer_count + 1), override=True)
        print_flush("[*] Now parsing agent_functions python files to sync with Mythic server")
        await sync_classes()
        print_flush("[*] Successfuly synced with Mythic server, waiting for tasking")
        result = await asyncio.wait_for(task, None)
    except Exception as e:
        print_flush("[-] mythic_service - exception, exiting container\n " + str(traceback.format_exc()))
        sys.exit(1)


async def rabbit_mythic_rpc_callback(
    exchange: aio_pika.Exchange, message: aio_pika.IncomingMessage
):
    async with message.process():
        try:
            message_json = json.loads(message.body.decode())
            # request = { "action": "function_name", "command": "command name"}
            response = {"status": "error", "error": "command's dynamic_query_function not found or not callable"}
            for cls in MythicCommandBase.CommandBase.__subclasses__():
                if getattr(cls, "cmd") == message_json["command"]:
                    Command = cls(Path(container_files_path))
                    CommandArgs = Command.argument_class("")
                    # now iterate over the args to find the one with name=request["action"]
                    for command_param in CommandArgs.args:
                        if command_param.name == message_json["action"] and callable(command_param.dynamic_query_function):
                            response = await command_param.dynamic_query_function(message_json["callback"])
                    break
        except Exception as e:
            print_flush("[-] Exception trying to respond to dynamic_query_function:\n" + str(traceback.format_exc()), override=True)
            response = {"status": "error", "error": str(e)}
        try:
            await exchange.publish(
                aio_pika.Message(body=json.dumps(response).encode(), correlation_id=message.correlation_id),
                routing_key=message.reply_to,
            )
        except Exception as e:
            print_flush(
                "[-] Exception trying to send message back to container for rpc! " + str(sys.exc_info()[-1].tb_lineno) + " " + str(e), override=True
            )

async def connect_and_consume_mythic_rpc():
    global channel
    global hostname
    # get a random queue that only the apfell server will use to listen on to catch all heartbeats
    print_flush("[*] Declaring container specific rpc queue in connect_and_consume_mythic_rpc")
    queue = await channel.declare_queue("{}_mythic_rpc_queue".format(hostname), auto_delete=True)
    await channel.set_qos(prefetch_count=int(settings.get("queue_prefetch_rpc", "10")))
    try:
        print_flush("[*] Starting to consume messages in connect_and_consume_mythic_rpc")
        task = await queue.consume(
            partial(rabbit_mythic_rpc_callback, channel.default_exchange)
        )
    except Exception as e:
        print_flush("[-] Exception in connect_and_consume_mythic_rpc .consume: {}".format(str(sys.exc_info()[-1].tb_lineno) + " " + str(e)), override=True)
        sys.exit(1)

# start our service
def start_service_and_heartbeat(**kwargs):
    global operating_environment
    if "debug" in kwargs:
        print_flush("[*] the `debug` argument is deprecated, instead set the `MYTHIC_ENVIRONMENT` variable directly for the container or for Mythic/.env", override=True)
    operating_environment = settings.get("environment", "production")
    if "debug" in kwargs and kwargs["debug"]:
        operating_environment = "testing"
        print_flush("[*] Setting MYTHIC_ENVIRONMENT=Testing based on deprecated debug=True argument", override=True)
    if operating_environment == "production":
        print_flush("[*] To enable debug logging, set `MYTHIC_ENVIRONMENT` variable to `testing`", override=True)
    get_version_info()
    loop = asyncio.get_event_loop()
    connect_task = loop.create_task(connect_to_rabbitmq())
    loop.run_until_complete(connect_task)
    asyncio.gather(heartbeat(), mythic_service(), connect_and_consume_mythic_rpc())
    loop.run_forever()

def get_version_info():
    print_flush("[*] Mythic PayloadType Version: " + container_version, override=True)
    print_flush("[*] PayloadType PyPi Version: " + PyPi_version, override=True)
