"""定义mprpc服务器基类.

+ File: core.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-01-23 version-0.5 by hsz
"""
import os
import pydoc
import platform
import inspect
from functools import partial
from concurrent import futures
from ssl import SSLContext
from signal import (
    SIGTERM, SIGINT
)
from typing import (
    Tuple,
    List,
    Optional,
    Any,
    Callable
)

from pymprpc.errors import (
    RpcException,
    NotFindError,
    ParamError,
    RPCRuntimeError
)

from .protocol import MPProtocolServer

from .utils import (
    list_public_methods,
    resolve_dotted_attribute
)

from .log import (
    logger
)

if platform.system() == "Windows":
    try:
        import aio_windows_patch as asyncio
    except:
        import warnings
        warnings.warn(
            "you should install aio_windows_patch to support windows",
            RuntimeWarning,
            stacklevel=3)
        import asyncio

else:
    import asyncio

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass


class BaseServer:
    """mprpc的服务器基类,负责启动服务器和管理连接.

    Attributes:
        addr (Tuple[str, int]): - 服务器的地址
        loop (asyncio.AbstractEventLoop): - 事件循环
        backlog (int): - 最大的连接数
        graceful_shutdown_timeout (int): - 优雅关闭的时间

    """

    version = "0.0.1"

    def __init__(self,
                 addr: Tuple[str, int], *,
                 loop: Optional[asyncio.AbstractEventLoop]=None,
                 func_executor: Optional[futures.Executor]=None,
                 auth: List[Tuple[str, str]]=[("admin", "admin")],
                 timeout: float = 180.0,
                 debug: bool=False,
                 compreser: Optional[str]=None,
                 ssl: Optional[SSLContext]=None,
                 backlog: int=100,
                 graceful_shutdown_timeout: int=10):
        """初始化服务器设置.

        Parameters:
            addr (Tuple[str, int]): - 服务器启动地址
            loop (Optional[asyncio.AbstractEventLoop]): - 启动服务的事件循环,默认为None
            func_executor (Optional[futures.Executor]): - 函数,方法等的执行器,
            默认为`ProcessPoolExecutor`

            auth (List[Tuple[str, str]]): - 验证信息,默认为`[("admin", "admin")]`
            timeout (float): - 连接的过期时间,默认180s
            debug (bool): - 是否使用debug模式,默认为False
            compreser: (Optional[str]): - 使用什么压缩函数,默认为None
            ssl (Optional[SSLContext]): - 是否使用ssl,默认为None
            backlog (int): - 设置默认的连接数缓冲大小,默认为100
            graceful_shutdown_timeout (int): - 优雅关闭延迟时间,默认10

        """
        # public
        self.addr = addr
        self.loop = loop or asyncio.get_event_loop()
        self.ssl = ssl
        self.backlog = backlog
        self.graceful_shutdown_timeout = graceful_shutdown_timeout
        self.pid = None
        self.funcs = {}
        self.instance = None

        self.rpc_server = None
        self.running = False
        # protected
        self._func_executor = func_executor or futures.ProcessPoolExecutor()
        self._protocol = partial(
            MPProtocolServer,
            method_wrapper=self,
            loop=loop,
            auth=auth,
            timeout=timeout,
            debug=debug,
            compreser=compreser)
        self.loop.set_default_executor(func_executor)
        if debug is True:
            self.loop.set_debug(True)

    def clean(self):
        """服务结束后清理服务器."""
        # 服务结束阶段
        if self.running is False:
            return False
        logger.info("Stopping worker [%s]", self.pid)
        # 关闭server
        self.rpc_server.close()
        self.loop.run_until_complete(self.rpc_server.wait_closed())
        # 关闭连接
        # 完成所有空转连接的关闭工作
        for connection in MPProtocolServer.CONNECTIONS:
            connection.shutdown()

        # 等待由graceful_shutdown_timeout设置的时间
        # 让还在运转的连接关闭,防止连接一直被挂起
        start_shutdown = 0
        while MPProtocolServer.CONNECTIONS and (
                start_shutdown < self.graceful_shutdown_timeout):
            self.loop.run_until_complete(asyncio.sleep(0.1))
            start_shutdown = start_shutdown + 0.1

        # 在等待graceful_shutdown_timeout设置的时间后
        # 强制关闭所有的连接
        # for conn in MPProtocolServer.CONNECTIONS:
        #     conn.close()
        # 收尾阶段关闭所有协程,
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        # 关闭loop
        self.loop.close()
        logger.info("Stopped worker [%s]", self.pid)
        return True

    def run_forever(self):
        """执行服务器."""
        server_coroutine = self.loop.create_server(
            self._protocol,
            self.addr[0],
            self.addr[1],
            ssl=self.ssl,
            backlog=self.backlog
        )
        try:
            self.rpc_server = self.loop.run_until_complete(server_coroutine)
        except BaseException:
            logger.exception("Unable to start server")
            return
        _singals = (SIGINT, SIGTERM)
        for _signal in _singals:
            try:
                self.loop.add_signal_handler(_signal, self.loop.stop)
            except NotImplementedError as ni:
                logger.warning('tried to use loop.add_signal_handler '
                               'but it is not implemented on this platform.')
        self.pid = os.getpid()
        logger.info(
            "Server @{host}:{port}".format(
                host=self.addr[0],
                port=self.addr[1]
            )
        )
        logger.info(
            """Starting worker [{pid}]
  _ __ ___  _ __  _ __ _ __   ___ 
 | '_ ` _ \| '_ \| '__| '_ \ / __|
 | | | | | | |_) | |  | |_) | (__ 
 |_| |_| |_| .__/|_|  | .__/ \___|
           |_|        |_|                 
""".format(pid=self.pid))
        self.running = True
        self.loop.run_forever()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.clean()

    # --------------------自省--------------------------------
    def register_introspection_functions(self)->None:
        """注册自省函数到函数字典."""
        self.funcs.update({
            'system.listMethods': self.system_listMethods,
            'system.methodSignature': self.system_methodSignature,
            'system.methodHelp': self.system_methodHelp,
            'system.lenConnections': self.system_lenConnections,
            'system.lenUndoneTasks': self.system_lenUndoneTasks
        })

    def system_lenConnections(self)->int:
        """获取所有的连接数目."""
        return len(MPProtocolServer.CONNECTIONS)

    def system_lenUndoneTasks(self)->int:
        """获取未完成的任务数目."""
        return len([i for i in MPProtocolServer.TASKS if not i.done()])

    def system_listMethods(self)->List[str]:
        """返回所有注册的函数的名字.

        system.listMethods() => ['add', 'subtract', 'multiple']

        Return:
            (list): - 被注册的可调用函数

        """
        methods = set(self.funcs.keys())
        if self.instance is not None:
            if hasattr(self.instance, '_listMethods'):
                methods |= set(self.instance._listMethods())
            elif not hasattr(self.instance, '_dispatch'):
                methods |= set(list_public_methods(self.instance))
        return sorted(methods)

    def system_methodSignature(self, method_name: str)->str:
        """获取函数的签名.

        system.methodSignature('add') => [double, int, int]

        Parameters:
            method_name (str): - 要查看的函数名

        Returns:
            (str): - 签名文本

        """
        method = None
        if method_name in self.funcs:
            method = self.funcs[method_name]
        elif self.instance is not None:
            try:
                method = resolve_dotted_attribute(
                    self.instance,
                    method_name,
                    self.allow_dotted_names
                )
            except AttributeError:
                pass
        if method is None:
            return ""
        else:
            return str(inspect.signature(method))

    def system_methodHelp(self, method_name: str)->str:
        """将docstring返回.

        system.methodHelp('add') => "Adds two integers together"

        Return:
            (str): - 函数的帮助文本

        """
        method = None
        if method_name in self.funcs:
            method = self.funcs[method_name]
        elif self.instance is not None:
            try:
                method = resolve_dotted_attribute(
                    self.instance,
                    method_name,
                    self.allow_dotted_names
                )
            except AttributeError:
                pass
        if method is None:
            return ""
        else:
            return pydoc.getdoc(method)

    # ---------------------注册函数------------------------

    def register_instance(self, instance: Any, allow_dotted_names: bool=False):
        """注册一个实例用于执行,注意只能注册一个.

        Parameters:
            instance (Any): - 将一个类的实例注册到rpc
            allow_dotted_names (bool): 是否允许带`.`号的名字

        """
        if self.instance:
            raise RuntimeError("can only register one instance")
        self.instance = instance
        self.allow_dotted_names = allow_dotted_names
        return True

    def register_function(self, name: Optional[str]=None):
        """注册函数.

        Parameters:
            name (Optional[str]): - 将函数注册到的名字,如果为None,name就用其原来的名字

        """
        def wrap(function: Callable)->Any:
            nonlocal name
            if name is None:
                name = function.__name__
            self.funcs[name] = function
            return function
        return wrap

    def set_executor(self, executor: futures.Executor):
        """设置计算密集型任务的执行器.

        Parameters:
            executor (futures.Executor): - 函数调用的执行器

        """
        self.loop.set_default_executor(executor)
        self._func_executor = executor
        return True

    async def apply(self, ID: str, method: str, *args: Any, **kwargs: Any):
        """执行注册的函数或者实例的方法.

        如果函数或者方法是协程则执行协程,如果是函数则使用执行器执行,默认使用的是多进程.

        Parameters:
            ID (str): 任务的ID
            method (str): 任务调用的函数名
            args (Any): 位置参数
            kwargs (Any): 关键字参数

        Raise:
            (RPCRuntimeError): - 当执行调用后抛出了异常,那就算做RPC运行时异常

        Return:
            (Any): - 被调用函数的返回

        """
        func = None
        try:
            # check to see if a matching function has been registered
            func = self.funcs[method]
        except KeyError:
            if self.instance is not None:
                # check for a _dispatch method
                try:
                    func = resolve_dotted_attribute(
                        self.instance,
                        method,
                        self.allow_dotted_names)
                except AttributeError:
                    pass
        if func is not None:
            sig = inspect.signature(func)
            try:
                sig.bind(*args, **kwargs)
            except:
                raise ParamError(
                    "args can not bind to method {}".format(method), ID)
            if method.startswith("system."):
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    raise RPCRuntimeError(
                        'Error:{} happend in method {}'.format(
                            e.__class__.__name__,
                            method
                        ),
                        ID
                    )
                else:
                    return result
            if inspect.iscoroutinefunction(func):
                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    raise RPCRuntimeError(
                        'Error:{} happend in method {}'.format(
                            e.__class__.__name__,
                            method
                        ),
                        ID
                    )
                else:
                    return result
            elif inspect.isasyncgenfunction(func):
                result = func(*args, **kwargs)
                return result
            elif inspect.isfunction(func) or inspect.ismethod(func):
                try:
                    f = partial(func, *args, **kwargs)
                    result = await self.loop.run_in_executor(None, f)
                except Exception as e:
                    raise RPCRuntimeError(
                        'Error:{} happend in method {}'.format(
                            e.__class__.__name__,
                            method
                        ),
                        ID
                    )
                else:
                    return result
            else:
                raise RpcException('method "%s" is not supported' % method)
        else:
            raise NotFindError('method "%s" is not supported' % method, ID)
