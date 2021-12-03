from abc import abstractmethod, ABCMeta
import json
from enum import Enum
import base64
import uuid
from pathlib import Path
from .PayloadBuilder import SupportedOS


class MythicStatus():
    Error = "error"
    Completed = "completed"
    Processed = "processed"
    Processing = "processing"
    Preprocessing = "preprocessing"
    Delegating = "delegating subtasks"
    CallbackError = "task callback error"
    Success = "success"
    def __init__(self, status: str):
        self.status = status
    def __str__(self):
        return self.status

class MythicRPCStatus():
    Success = "success"
    Error = "error"
    def __init__(self, status: str):
        self.status = status
    def __str__(self):
        return self.status

class ParameterType(str, Enum):
    String = "String"
    Boolean = "Boolean"
    File = "File"
    Array = "Array"
    ChooseOne = "Choice"
    ChooseMultiple = "ChoiceMultiple"
    Credential_JSON = "Credential-JSON"
    Credential_Account = "Credential-Account"
    Credential_Realm = "Credential-Realm"
    Credential_Type = "Credential-Type"
    Credential_Value = "Credential-Credential"
    Number = "Number"
    Payload = "PayloadList"
    ConnectionInfo = "AgentConnect"
    LinkInfo = "LinkInfo"

class CommandAttributes():
    def __init__(self,
        spawn_and_injectable: bool = False,
        supported_os: [SupportedOS] = None,
        builtin: bool = False,
        suggested_command: bool = False,
        load_only: bool = False,
        filter_by_build_parameter: dict = {},
        **kwargs):
        self.spawn_and_injectable = spawn_and_injectable
        self.supported_os = supported_os
        self.builtin = builtin
        self.suggested_command = suggested_command
        self.load_only = load_only
        self.filter_by_build_parameter = filter_by_build_parameter
        self.additional_items = {}
        for k,v in kwargs.items():
            self.additional_items[k] = v
    
    def to_json(self):
        r = {}
        if self.spawn_and_injectable is not None:
            r["spawn_and_injectable"] = self.spawn_and_injectable
        else:
            r["spawn_and_injectable"] = False
        if self.supported_os is not None:
            r["supported_os"] = [str(x) for x in self.supported_os]
        else:
            r["supported_os"] = []
        r["builtin"] = self.builtin
        r["suggested_command"] = self.suggested_command
        r["load_only"] = self.load_only
        r["filter_by_build_parameter"] = self.filter_by_build_parameter
        r = {**r, **self.additional_items}
        return r

class ParameterGroupInfo:
    def __init__(
        self,
        required: bool = True,
        group_name: str = "Default",
        ui_position: int = None,
        **kwargs
    ):  
        self.required = required 
        self.group_name = group_name 
        self.ui_position = ui_position
        self.additional_info = {}
        for k,v in kwargs.items():
            self.additional_info[k] = v

    def to_json(self):
        r = {}
        r["required"] = self.required 
        r["group_name"] = self.group_name 
        r["ui_position"] = self.ui_position
        r = {**r, **self.additional_info}
        return r

class CommandParameter:
    def __init__(
        self,
        name: str,
        type: ParameterType,
        display_name: str = None,
        cli_name: str = None,
        description: str = "",
        choices: [any] = None,
        default_value: any = None,
        validation_func: callable = None,
        value: any = None,
        supported_agents: [str] = None,
        supported_agent_build_parameters: dict = None,
        choice_filter_by_command_attributes: dict = None,
        choices_are_all_commands: bool = False,
        choices_are_loaded_commands: bool = False,
        dynamic_query_function: callable = None,
        parameter_group_info: [ParameterGroupInfo] = None
    ):
        self.name = name
        if display_name is None:
            self.display_name = name
        else:
            self.display_name = display_name
        if cli_name is None:
            self.cli_name = name 
        else:
            self.cli_name = cli_name
        self.type = type
        self.user_supplied = False # keep track of if this is using the default value or not
        self.description = description
        if choices is None:
            self.choices = []
        else:
            self.choices = choices
        self.validation_func = validation_func
        if value is None:
            self._value = default_value
        else:
            self.value = value
        self.default_value = default_value
        self.supported_agents = supported_agents if supported_agents is not None else []
        self.supported_agent_build_parameters = supported_agent_build_parameters if supported_agent_build_parameters is not None else {}
        self.choice_filter_by_command_attributes = choice_filter_by_command_attributes if choice_filter_by_command_attributes is not None else {}
        self.choices_are_all_commands = choices_are_all_commands
        self.choices_are_loaded_commands = choices_are_loaded_commands
        self.dynamic_query_function = dynamic_query_function
        if not callable(dynamic_query_function) and dynamic_query_function is not None:
            raise Exception("dynamic_query_function is not callable")
        self.parameter_group_info = parameter_group_info
        if self.parameter_group_info is None:
            self.parameter_group_info = [ParameterGroupInfo()]

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, type):
        self._type = type

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, description):
        self._description = description

    @property
    def choices(self):
        return self._choices

    @choices.setter
    def choices(self, choices):
        self._choices = choices

    @property
    def validation_func(self):
        return self._validation_func

    @validation_func.setter
    def validation_func(self, validation_func):
        self._validation_func = validation_func

    @property
    def supported_agents(self):
        return self._supported_agents

    @supported_agents.setter
    def supported_agents(self, supported_agents):
        self._supported_agents = supported_agents
        
    @property
    def supported_agent_build_parameters(self):
        return self._supported_agent_build_parameters

    @supported_agent_build_parameters.setter
    def supported_agent_build_parameters(self, supported_agent_build_parameters):
        self._supported_agent_build_parameters = supported_agent_build_parameters

    @property
    def dynamic_query_func(self):
        return self._dynamic_query_func

    @dynamic_query_func.setter
    def dynamic_query_func(self, dynamic_query_func):
        self._dynamic_query_func = dynamic_query_func

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if value is not None:
            type_validated = TypeValidators().validate(self.type, value)
            if self.validation_func is not None:
                try:
                    self.validation_func(type_validated)
                    self._value = type_validated
                except Exception as e:
                    raise ValueError(
                        "Failed validation check for parameter {} with value {}".format(
                            self.name, str(value)
                        )
                    )
                self.user_supplied = True
                return
            else:
                # now we do some verification ourselves based on the type
                self._value = type_validated
                self.user_supplied = True
                return
        self._value = value
        self.user_supplied = True 
        return

    @property
    def parameter_group_info(self):
        return self._parameter_group_info

    @parameter_group_info.setter
    def parameter_group_info(self, parameter_group_info):
        self._parameter_group_info = parameter_group_info
    

    def to_json(self):
        return {
            "name": self._name,
            "display_name": self.display_name,
            "cli_name": self.cli_name.replace(" ", "-"),
            "type": self._type.value,
            "description": self._description,
            "choices": "\n".join(self._choices),
            "default_value": self.default_value,
            "value": self.value,
            "supported_agents": ",".join(self._supported_agents),
            "supported_agent_build_parameters": self._supported_agent_build_parameters,
            "choices_are_loaded_commands": self.choices_are_loaded_commands,
            "choices_are_all_commands": self.choices_are_all_commands,
            "choice_filter_by_command_attributes": self.choice_filter_by_command_attributes,
            "dynamic_query_function": self.dynamic_query_function.__name__ if callable(self.dynamic_query_function) else None,
            "parameter_group_info": [x.to_json() for x in self.parameter_group_info] if self.parameter_group_info is not None else [ParameterGroupInfo().to_json()]
        }

class TypeValidators:
    def validateString(self, val):
        return str(val)

    def validateNumber(self, val):
        try:
            return int(val)
        except:
            return float(val)

    def validateBoolean(self, val):
        if isinstance(val, bool):
            return val
        else:
            raise ValueError("Value isn't bool")

    def validateFile(self, val):
        try:  # check if the file is actually a file-id
            uuid_obj = uuid.UUID(val, version=4)
            return str(uuid_obj)
        except ValueError:
            pass
        return base64.b64decode(val)

    def validateArray(self, val):
        if isinstance(val, list):
            return val
        else:
            raise ValueError("value isn't array")

    def validateCredentialJSON(self, val):
        if isinstance(val, dict):
            return val
        else:
            raise ValueError("value ins't a dictionary")

    def validatePass(self, val):
        return val

    def validateChooseMultiple(self, val):
        if isinstance(val, list):
            return val
        else:
            raise ValueError("Choices aren't in a list")

    def validatePayloadList(self, val):
        return str(uuid.UUID(val, version=4))

    def validateAgentConnect(self, val):
        if isinstance(val, dict):
            return val
        else:
            raise ValueError("Not instance of dictionary")

    switch = {
        "String": validateString,
        "Number": validateNumber,
        "Boolean": validateBoolean,
        "File": validateFile,
        "Array": validateArray,
        "Credential-JSON": validateCredentialJSON,
        "Credential-Account": validatePass,
        "Credential-Realm": validatePass,
        "Credential-Type": validatePass,
        "Credential-Credential": validatePass,
        "Choice": validatePass,
        "ChoiceMultiple": validateChooseMultiple,
        "PayloadList": validatePayloadList,
        "AgentConnect": validateAgentConnect,
        "LinkInfo": validateAgentConnect
    }

    def validate(self, type: ParameterType, val: any):
        return self.switch[type.value](self, val)

class TaskArguments(metaclass=ABCMeta):
    def __init__(self, command_line: str, tasking_location: str = "command_line"):
        self.command_line = str(command_line)
        self.tasking_location = tasking_location

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    def get_arg(self, key: str):
        for arg in self.args:
            if arg.name == key:
                return arg.value
        return None

    def has_arg(self, key: str) -> bool:
        for arg in self.args:
            if arg.name == key:
                return True
        return False

    def get_commandline(self) -> str:
        return self.command_line

    def get_tasking_location(self) -> str:
        return self.tasking_location

    def is_empty(self) -> bool:
        return len(self.args) == 0

    def add_arg(self, key: str, value, type: ParameterType = None, parameter_group_info: [ParameterGroupInfo] = [ParameterGroupInfo()]):
        found = False
        for arg in self.args:
            if arg.name == key:
                arg.value = value 
                if type is not None:
                    arg.type = type 
                found = True
        if not found:
            if type is not None:
                self.args.append(CommandParameter(name=key, type=type, value=value, parameter_group_info=parameter_group_info))
            else:
                self.args.append(CommandParameter(name=key, type=ParameterType.String, value=value, parameter_group_info=parameter_group_info))

    def set_arg(self, key: str, value):
        found = False 
        for arg in self.args:
            if arg.name == key:
                arg.value = value 
                found = True 
        if not found:
            self.add_arg(key, value)

    def rename_arg(self, old_key: str, new_key: str):
        for arg in self.args:
            if arg.name == old_key:
                arg.name = new_key
                return
        raise Exception("{} not a valid parameter name".format(old_key))

    def remove_arg(self, key: str):
        self.args = [x for x in self.args if x.name != key]

    def to_json(self):
        return [x.to_json() for x in self.args]

    def load_args_from_json_string(self, command_line: str) -> None:
        temp_dict = json.loads(command_line)
        for k, v in temp_dict.items():
            for arg in self.args:
                if arg.name == k or arg.cli_name == k:
                    arg.value = v

    def load_args_from_dictionary(self, dictionary) -> None:
        for k, v in dictionary.items():
            for arg in self.args:
                if arg.name == k or arg.cli_name == k:
                    arg.value = v

    def get_parameter_group_name(self) -> str:
        groupNameOptions = []
        suppliedArgNames = []
        if len(self.args) == 0:
            return "Default"
        for arg in self.args:
            for group_info in arg.parameter_group_info:
                if group_info.group_name not in groupNameOptions:
                    groupNameOptions.append(group_info.group_name)
        for arg in self.args:
            # when determining the group we're in, only look at arguments that have values that were set by the user
            # default values don't count
            if arg.value is not None and arg.user_supplied:
                suppliedArgNames.append(arg.name)
                groupNameIntersection = []
                for group_info in arg.parameter_group_info:
                    if group_info.group_name in groupNameOptions:
                        groupNameIntersection.append(group_info.group_name)
                groupNameOptions = groupNameIntersection
        if len(groupNameOptions) == 0:
            raise ValueError(f"Supplied Arguments, {suppliedArgNames}, don't match any parameter group") 
        elif len(groupNameOptions) > 1:
            raise ValueError(f"Supplied Arguments, {suppliedArgNames}, match more than one parameter group: {groupNameOptions}")
        else:
            return groupNameOptions[0]

    def get_parameter_group_arguments(self) -> [CommandParameter]:
        groupName = self.get_parameter_group_name()
        group_arguments = []
        for arg in self.args:
            matched_arg = False
            for group_info in arg.parameter_group_info:
                if group_info.group_name == groupName:
                    matched_arg = True 
            if matched_arg:
                group_arguments.append(arg)
        return group_arguments

    async def verify_required_args_have_values(self) -> bool:
        # first we have to establish which parameter group we're in
        groupName = self.get_parameter_group_name()
        for arg in self.args:
            matched_arg = False
            arg_required = False
            for group_info in arg.parameter_group_info:
                if group_info.group_name == groupName:
                    matched_arg = True 
                    arg_required = group_info.required 
            if matched_arg:
                if arg.value is None:
                    arg.value = arg.default_value
                if arg_required and arg.value is None:
                    raise ValueError("Required arg {} has no value".format(arg.name))
        return True

    def __str__(self) -> str:
        if len(self.args) > 0:
            try:
                groupName = self.get_parameter_group_name()
            except Exception as e:
                return self.command_line
            temp = {}
            for arg in self.args:
                matched_arg = False
                for group_info in arg.parameter_group_info:
                    if group_info.group_name == groupName:
                        matched_arg = True 
                if matched_arg:
                    if isinstance(arg.value, bytes):
                        temp[arg.name] = base64.b64encode(arg.value).decode()
                    else:
                        temp[arg.name] = arg.value
            return json.dumps(temp)
        else:
            return self.command_line

    @abstractmethod
    async def parse_arguments(self) -> None:
        pass

class Callback:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class BrowserScript:
    # if a browserscript is specified as part of a PayloadType, then it's a support script
    # if a browserscript is specified as part of a command, then it's for that command
    def __init__(self, script_name: str, author: str = None, for_new_ui: bool = False):
        self.script_name = script_name
        self.author = author
        self.for_new_ui = for_new_ui

    def to_json(self, base_path: Path):
        try:
            code_file = (
                base_path
                / "mythic"
                / "browser_scripts"
                / "{}.js".format(self.script_name)
            )
            if code_file.exists():
                code = code_file.read_bytes()
                code = base64.b64encode(code).decode()
            else:
                raise Exception("Code for Browser Script, " + self.script_name + ", does not exist on disk at path: " + str(code_file))
                code = ""
            return {"script": code, "name": self.script_name, "author": self.author, "for_new_ui": self.for_new_ui}
        except Exception as e:
            return {"script": str(e), "name": self.script_name, "author": self.author, "for_new_ui": self.for_new_ui}

class MythicTask:
    def __init__(
        self, taskinfo: dict, args: TaskArguments, status: MythicStatus = None
    ):
        self.id = taskinfo["id"]
        self.original_params = taskinfo["original_params"]
        self.completed = taskinfo["completed"]
        self.callback = Callback(**taskinfo["callback"])
        self.agent_task_id = taskinfo["agent_task_id"]
        self.token = taskinfo["token"]
        self.operator = taskinfo["operator"]
        self.opsec_pre_blocked = taskinfo["opsec_pre_blocked"]
        self.opsec_pre_message = taskinfo["opsec_pre_message"]
        self.opsec_pre_bypassed = taskinfo["opsec_pre_bypassed"]
        self.opsec_pre_bypass_role = taskinfo["opsec_pre_bypass_role"]
        self.opsec_pre_bypass_user = taskinfo["opsec_pre_bypass_user"]
        self.opsec_post_blocked = taskinfo["opsec_post_blocked"]
        self.opsec_post_message = taskinfo["opsec_post_message"]
        self.opsec_post_bypassed = taskinfo["opsec_post_bypassed"]
        self.opsec_post_bypass_role = taskinfo["opsec_post_bypass_role"]
        self.opsec_post_bypass_user = taskinfo["opsec_post_bypass_user"]
        self.display_params = taskinfo["display_params"]
        self.command_name = taskinfo["command_name"]
        self.args = args
        self.manual_args = None
        self.status = MythicStatus.Preprocessing
        if status is not None:
            self.status = MythicStatus(status)
        self.tasking_location = taskinfo["tasking_location"] if "tasking_location" in taskinfo else "command_line"
        self.stdout = taskinfo["stdout"] if "stdout" in taskinfo else ""
        self.stderr = taskinfo["stderr"] if "stderr" in taskinfo else ""
        self.subtask_callback_function = taskinfo["subtask_callback_function"]
        self.group_callback_function = taskinfo["group_callback_function"]
        self.completed_callback_function = taskinfo["completed_callback_function"]
        self.subtask_group_name = taskinfo["subtask_group_name"]
        # self.tags is an array of tags to associate with the task
        self.tags = taskinfo["tags"]

    def get_status(self) -> MythicStatus:
        return self.status

    def set_status(self, status: MythicStatus):
        self.status = status
        
    def set_stdout(self, stdout: str):
        self.stdout = stdout
    
    def set_stderr(self, stderr: str):
        self.stderr = stderr

    # if you call override_args with your own values, then we won't use the standard JSON string from self.args
    #   this combined with command_name can allow you to completely set what gets sent to your agent
    def override_args(self, args: str):
        self.manual_args = args

    def __str__(self):
        return json.dumps(self.to_json())

    def to_json(self):
        subtask_callback_function = self.subtask_callback_function
        if callable(subtask_callback_function):
            subtask_callback_function = subtask_callback_function.__name__
        group_callback_function = self.group_callback_function
        if callable(group_callback_function):
            group_callback_function = group_callback_function.__name__
        completed_callback_function = self.completed_callback_function
        if callable(completed_callback_function):
            completed_callback_function = completed_callback_function.__name__
        command_args = str(self.args)
        if self.manual_args is not None:
            command_args = self.manual_args
        return {
            "args": command_args,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "opsec_pre_blocked": self.opsec_pre_blocked,
            "opsec_pre_message": self.opsec_pre_message,
            "opsec_pre_bypass_role": self.opsec_pre_bypass_role,
            "opsec_pre_bypassed": self.opsec_pre_bypassed,
            "opsec_post_blocked": self.opsec_post_blocked,
            "opsec_post_message": self.opsec_post_message,
            "opsec_post_bypass_role": self.opsec_post_bypass_role,
            "opsec_post_bypassed": self.opsec_post_bypassed,
            "display_params": self.display_params,
            "subtask_callback_function": subtask_callback_function,
            "group_callback_function": group_callback_function,
            "completed_callback_function": completed_callback_function,
            "subtask_group_name": self.subtask_group_name,
            "command_name": self.command_name,
            "tags": self.tags
                          }

class AgentResponse:
    def __init__(self, response: any, task: MythicTask):
        self.response = response
        self.task = task

class CommandOPSEC(metaclass=ABCMeta):
    def __init__(self, 
        injection_method: str = "",
        process_creation: str = "",
        authentication: str = "",
        **kwargs):
        self.injection_method = injection_method
        self.process_creation = process_creation
        self.authentication = authentication
        self.additional_items = {}
        for k,v in kwargs.items():
            self.additional_items[k] = v

    @property
    @abstractmethod
    def injection_method(self):
        pass

    @property
    @abstractmethod
    def process_creation(self):
        pass

    @property
    @abstractmethod
    def authentication(self):
        pass

    def to_json(self):
        temp = {}
        temp["injection_method"] = self.injection_method
        temp["process_creation"] = self.process_creation
        temp["authentication"] = self.authentication
        temp = {**temp, **self.additional_items}
        return temp

    @abstractmethod
    async def opsec_pre(self, task: MythicTask):
        pass

    @abstractmethod
    async def opsec_post(self, task: MythicTask):
        pass

class CommandBase(metaclass=ABCMeta):
    def __init__(self, agent_code_path: Path):
        self.base_path = agent_code_path
        self.agent_code_path = agent_code_path / "agent_code"

    @property
    @abstractmethod
    def cmd(self):
        pass

    @property
    @abstractmethod
    def needs_admin(self):
        pass

    @property
    @abstractmethod
    def help_cmd(self):
        pass

    @property
    @abstractmethod
    def description(self):
        pass

    @property
    @abstractmethod
    def version(self):
        pass

    @property
    def supported_ui_features(self):
        pass

    @property
    @abstractmethod
    def author(self):
        pass

    @property
    @abstractmethod
    def argument_class(self):
        pass

    @property
    @abstractmethod
    def attackmapping(self):
        pass

    @property
    def browser_script(self):
        pass
    
    @property
    def attributes(self):
        pass
    
    @property
    def opsec_class(self):
        pass

    @property
    def script_only(self):
        pass

    @abstractmethod
    async def create_tasking(self, task: MythicTask) -> MythicTask:
        pass

    @abstractmethod
    async def process_response(self, response: AgentResponse):
        pass

    def to_json(self):
        params = self.argument_class("").to_json()
        opsec = self.opsec_class().to_json() if self.opsec_class is not None else {}
        if self.browser_script is not None:
            if isinstance(self.browser_script, list):
                bscript = {"browser_script": [x.to_json(self.base_path) for x in self.browser_script]}
            else:
                bscript = {"browser_script": [self.browser_script.to_json(self.base_path)]}
        else:
            bscript = {"browser_script": []}
        if self.attributes is None:
            attributes = CommandAttributes()
        else:
            attributes = self.attributes
        return {
            "cmd": self.cmd,
            "needs_admin": self.needs_admin,
            "help_cmd": self.help_cmd,
            "description": self.description,
            "version": self.version,
            "supported_ui_features": self.supported_ui_features if self.supported_ui_features is not None else [],
            "author": self.author,
            "attack": [{"t_num": a} for a in self.attackmapping],
            "parameters": params,
            "opsec": opsec,
            "attributes": attributes.to_json(),
            "script_only": self.script_only if self.script_only is not None else False,
            **bscript,
        }
