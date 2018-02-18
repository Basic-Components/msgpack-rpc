import traceback
import inspect
import platform
from time import time
import zlib
import bz2
import lzma
import warnings
from typing import (
    Optional,
    List,
    Tuple,
    Dict,
    Any,
    AsyncIterator
)
from pymprpc.errors import (
    ProtocolSyntaxException,
    LoginError,
    RequestError,
    MethodError,
    ServerException
)
from pymprpc.mixins.encoder_decoder_mixin import EncoderDecoderMixin
from .log import logger, access_logger
if platform.system() == "Windows":
    try:
        import aio_windows_patch as asyncio
    except:
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


class MPProtocolServer(asyncio.StreamReaderProtocol, EncoderDecoderMixin):
    """message-pack Protocol 的服务器协议实现.

    Attributes:
        CONNECTIONS (Set[MPProtocolServer]): - 当前的所有连接的池
        TASKS (List[asyncio.Future]): - 当前的所有连接下的所有任务
        SEPARATOR (bytes): - 读请求时的终止符,默认为`b"##PRO-END##"`
        VERSION (str): - 协议版本,以`x.x`的形式表现版本
        COMPRESERS (Dict[str,model]): - 支持的压缩解压工具

        version (int): - 协议版本
        auth  (List[Tuple[str, str]]): - 允许的登录用户名密码对
        method_wrapper (SimpleMPRPServer): - 远程调用包装
        tasks (Dict[str,asyncio.Future]): - 当前连接执行的任务
        timeout (float): - 连接的过期时间,一旦超时没有一条消息写入那么就强行关闭连接.默认为60.0s
        debug (bool): - 是否使用debug模式,默认不使用
        compreser (Optional[str]): - 是否压缩传输的信息,默认不压缩

    Property:
        connections  (Set): - 当前的连接池.

    """

    CONNECTIONS = set()
    TASKS = []
    SEPARATOR = b"##PRO-END##"
    VERSION = "0.1"
    COMPRESERS = {
        "zlib": zlib,
        "bz2": bz2,
        "lzma": lzma
    }

    @property
    def connections(self):
        """当前的连接数."""
        return self.__class__.CONNECTIONS

    def __init__(self,
                 method_wrapper: "SimpleMPRPServer",
                 loop: Optional[asyncio.AbstractEventLoop]=None,
                 auth: List[Tuple[str, str]]=None,
                 timeout: Optional[float] = 180.0,
                 debug: bool=False,
                 compreser: Optional[str]=None
                 ):
        """实例化一个协议对象,用于管理一个连接.

        初始化主要是设置成员的值,包括一些用于管理状态的变量和容器

        Parameters:
            method_wrapper (SimpleMPRPServer): - pmprpc服务的实例

            loop (Optional[asyncio.AbstractEventLoop]): - 事件循环

            auth (Optional[List[Tuple[str, str]]]): - 合法的认证信息,保存在一个列表中,
            以username,password的成对形式保存

            timeout (Optional[float]): - 过期时间,如果timeout为None则不会因过期而关闭

            debug (bool): - 是否使用debug模式,默认为否

            compreser(Optional[str]): - 是否使用压缩工具压缩传输信息,以及压缩工具是什么,默认为不使用.

        """
        # public
        self.auth = auth
        self.timeout = timeout
        self.debug = debug
        self.method_wrapper = method_wrapper
        self.tasks = {}

        if compreser is not None:
            _compreser = self.COMPRESERS.get(compreser)
            if _compreser is not None:
                self.compreser = _compreser
            else:
                raise RuntimeError("compreser unsupport")
        else:
            self.compreser = None
        # protected
        self._handlertask = None  # 执行的任务循环
        self._loop = loop or asyncio.get_event_loop()
        self._last_response_time = time()  # 上一次响应的过期时间
        self._timeout_handler = None
        self._transport = None
        self._remote_host = None
        self._extra = None
        self._stream_writer = None
        self._stream_reader = None
        self._client_connected_cb = None
        self._over_ssl = False

        self._paused = False
        self._drain_waiter = None
        self._connection_lost = False

    # ------------------------连接处理------------------------------------

    def connection_made(self, transport: asyncio.transports.Transport):
        """连接建立起来触发的回调函数.

        用于设定一些参数,并将监听任务放入事件循环,如果设置了timeout,也会将timeout_callback放入事件循环

        Parameters:
            transport (asyncio.Transports): - 连接的传输对象

        """
        self._transport = transport
        self._remote_host = self._transport.get_extra_info('peername')
        self._extra = {"client": str(self._remote_host)}
        self.connections.add(self)

        self._stream_reader = asyncio.StreamReader(loop=self._loop)
        self._stream_writer = asyncio.StreamWriter(transport, self,
                                                   self._stream_reader,
                                                   self._loop)
        super().connection_made(transport)
        if self.timeout:
            self._timeout_handler = self._loop.call_soon(
                self.timeout_callback)
        self._handlertask = asyncio.ensure_future(self.query_handler())
        if self.debug:
            access_logger.info("connected", extra=self._extra)

    def connection_lost(self, exc: Exception=None):
        """连接丢失时触发的回调函数.

        用于清理一些任务和关闭连接,包括:
        + 取消监听任务
        + 取消过期监控任务
        + 取消其他还没执行完的任务
        + 将流读写器都重置
        + 将本连接从当前的连接池中去除

        Parameters:
            exc (Exception): - 异常,如果是None的话说明不是因为异常而关闭的连接

        """
        self._handlertask.cancel()

        super().connection_lost(exc)
        if self._timeout_handler:
            self._timeout_handler.cancel()
        self._transport = None
        for i, task in self.tasks.items():
            task.cancel()
        self.connections.discard(self)
        if self.debug:
            access_logger.info("lost connection", extra=self._extra)

    def shutdown(self):
        """关停当前连接.

        用于主动关停连接,并清理一些任务,包括:
        + 取消监听任务
        + 取消过期监控任务
        + 取消其他还没执行完的任务
        + 将流读写器都重置

        """
        self._handlertask.cancel()

        if self._timeout_handler:
            self._timeout_handler.cancel()
        self._transport = None
        self._stream_reader = None
        self._stream_writer.close()
        for i, task in self.tasks.items():
            task.cancel()
        self._stream_writer = None
        logger.info("close connection with {}".format(
            self._remote_host
        ))

    def close(self):
        """强制关闭当前连接.

        用于主动关闭连接,并清理一些任务,包括:
        + 取消监听任务
        + 取消过期监控任务
        + 取消其他还没执行完的任务
        + 将流读写器都重置
        + 将本连接从当前的连接池中去除
        """
        self.shutdown()
        self.connections.discard(self)

    # --------------------------------过期处理-----------------------------

    def timeout_callback(self):
        """过期回调函数.

        如果设置了timeout则会启动一个协程按当前时间和最近的响应时间只差递归的执行这个回调

        """
        # Check if elapsed time since last response exceeds our configured
        # maximum keep alive timeout value
        now = time()
        time_elapsed = now - self._last_response_time
        if time_elapsed < self.timeout:
            time_left = self.timeout - time_elapsed
            self._timeout_handler = (
                self._loop.call_later(
                    time_left,
                    self.timeout_callback
                )
            )
        else:
            logger.info('KeepAlive Timeout. Closing connection.')
            responseb = self.encoder({
                "MPRPC": self.VERSION,
                "CODE": 504
            })
            self._stream_writer.write(responseb)
            self.close()
    # ------------------------流读写包装---------------------------------

    def writer(self, response: Dict[str, Any]):
        """将响应的python结构转化为字节,并写入到流中,同时刷新最后一次响应时间为当前时间

        Parameters:
            response (Dict[str,Any]): - 要写入给客户端的响应的python结构

        """
        responseb = self.encoder(response)
        self._stream_writer.write(responseb)
        if self.debug:
            access_logger.info("write {}".format(responseb), extra=self._extra)
        self._last_response_time = time()

    async def read(self):
        """读取请求,并转化为python的字典结构.如果读入了EOF,那么触发回调函数connection_lost."""
        try:
            data = await self._stream_reader.readuntil(self.SEPARATOR)
        except asyncio.IncompleteReadError:
            self.connection_lost()
        else:
            query = self.decoder(data)
            if self.debug:
                access_logger.info("get query: {}".format(
                    query
                ), extra=self._extra)
            return query

    # -------------------------------请求处理--------------------------------

    async def query_handler(self):
        """根据获取到的不同请求执行不同的动作.会在建立连接后被放入事件循环.

        主要为3种请求:
        + 验证请求
        + 心跳请求
        + 任务调用请求
        如果中途有步骤报错也负责将对应的错误转化为错误信息发送给客户端.

        """
        while True:
            request = await self.read()
            if request is None:
                break
            ID = request.get('ID')
            try:
                if request.get("AUTH"):
                    self._check_auth_handler(request)
                elif request.get("HEARTBEAT"):
                    response = {
                        "MPRPC": self.VERSION,
                        "CODE": 101,
                        "HEARTBEAT": "pong"
                    }
                    self.writer(response)
                elif ID:
                    fut = asyncio.ensure_future(
                        self._RPC_handler(request),
                        loop=self._loop)
                    if asyncio.isfuture(fut):
                        self.tasks[ID] = fut
                        self.__class__.TASKS.append(fut)
                else:
                    raise ProtocolSyntaxException("Protocol Syntax Error")
            except MethodError as se:
                exinfo = traceback.TracebackException.from_exception(
                    se).format(chain=True)
                frames = "".join([i + "/n" for i in exinfo])
                response = {
                    "MPRPC": self.VERSION,
                    "CODE": se.status_code,
                    "MESSAGE": {
                        "ID": ID,
                        'EXCEPTION': str(type(se)),
                        'MESSAGE': str(se),
                        "DATA": {
                            'METHOD': request.get("METHOD"),
                            "ARGS": request.get("ARGS"),
                            "KWARGS": request.get("KWARGS"),
                            'FRAME': frames}
                    }
                }
                self.writer(response)
            except ServerException as me:
                response = {
                    "MPRPC": self.VERSION,
                    "CODE": me.status_code,

                }
                self.writer(response)
            except Exception as e:
                if self.debug:
                    logger.info("Unknow Error: {}[{}]".format(
                        type(e).__name__, str(e)
                    ))

    # -------------------------------用户验证---------------------------------
    def _check_auth_handler(self, request: Dict[str, Any]):
        """用于验证客户端是否有权限调服务.

        如果服务端有验证信息,则会根据验证信息判断是否合法
        + 如果合法,那么返回一条信息用于响应验证请求
        + 如果不合法,那么返回验证错误

        如果服务端没有验证信息
        + 如果验证信息都为空,直接返回响应
        + 如果信息不为空,那么返回验证错误

        Parameters:
            request (Dict[str, Any]): - python字典形式的请求

        Return:
            (bool): - 请求是否被验证通过,通过了返回True

        Raise:
            (LoginError): - 当验证不通过时抛出

        """
        a_username = request.get("AUTH").get("USERNAME")
        a_password = request.get("AUTH").get("PASSWORD")
        auth_len = len(self.auth)
        if auth_len == 0:
            if any([a_username, a_password]):
                if self.debug:
                    access_logger.info("login failed", extra=self._extra)
                raise LoginError("login error ,unknown username/password")
            else:
                return True
        else:
            for username, password in self.auth:
                if all([a_username == username, a_password == password]):
                    response = {
                        "MPRPC": self.VERSION,
                        "CODE": 100,
                        "VERSION": self.method_wrapper.version,
                        "DESC": self.method_wrapper.__doc__,
                        "DEBUG": self.debug,
                        "COMPRESER": self.compreser.__name__ if (
                            self.compreser) else None,
                        "TIMEOUT": self.timeout,
                    }
                    self.writer(response)
                    if self.debug:
                        access_logger.info("login succeed", extra=self._extra)
                    break
            else:
                if self.debug:
                    access_logger.info("login failed", extra=self._extra)
                raise LoginError("login error ,unknown username/password")
            return True

    # ----------------------------------RPC调用处理---------------------------------
    async def _RPC_handler(self, request: Dict[str, Any]):
        """用于调用函数并执行.同时如果执行出错也负责将错误转化为对应的调用错误返回给客户端.

        执行成功后根据结果进行不同的处理,如果注册的是函数,实例中的方法,或者协程,则获取计算得的结果,并返回给客户端.
        如果是异步生成器函数,那么返回的就是一个对应的异步生成器,我们通过对其包装后循环调用实现流传输.

        Parameters:
            request (Dict[str, Any]): - python字典形式的请求

        Raise:
            (Exception): - 当执行调用后抛出了异常,且异常不在定义范围内,则抛出

        Return:
            (bool): - 当正常调用则返回True,如果抛出了规定范围内的异常则返回False

        """
        ID = request.get("ID")
        method = request.get("METHOD")
        with_return = request.get("RETURN")
        args = request.get("ARGS") or []
        kwargs = request.get("KWARGS") or {}
        try:
            if method is None:
                raise RequestError(
                    "request do not have method", request.get("ID"))
            if method == "system.getresult":
                await self._get_result(ID, *args, **kwargs)
            else:
                result = await self.method_wrapper.apply(ID, method,
                                                         *args, **kwargs)
        except MethodError as se:
            exinfo = traceback.TracebackException.from_exception(
                se).format(chain=True)
            frames = "".join([i + "/n" for i in exinfo])
            response = {
                "MPRPC": self.VERSION,
                "CODE": se.status_code,
                "MESSAGE": {
                    "ID": ID,
                    'EXCEPTION': str(type(se)),
                    'MESSAGE': str(se),
                    "DATA": {
                        'METHOD': request.get("METHOD"),
                        "ARGS": request.get("ARGS"),
                        "KWARGS": request.get("KWARGS"),
                        'FRAME': frames}
                }
            }
            self.writer(response)
            return False
        except ServerException as me:
            response = {
                "MPRPC": self.VERSION,
                "CODE": me.status_code,
            }
            self.writer(response)
            return False
        except Exception as e:
            if self.debug is True:
                raise e
            else:
                logger.info(
                    "Task[{}]: Unknown Error {}:\nmessage:{}".format(
                        ID, e.__class__.__name__, str(e))
                )
        else:
            if with_return:
                if inspect.isasyncgen(result):
                    await self._asyncgen_wrap(result, ID)
                else:
                    response = {
                        "MPRPC": self.VERSION,
                        "CODE": 200,
                        "MESSAGE": {
                            "ID": ID,
                            'RESULT': result
                        }
                    }
                    self.writer(response)
                    if self.debug:
                        access_logger.info(
                            "Task[{}]: response answered".format(ID),
                            extra=self._extra
                        )
            return result

    async def _asyncgen_wrap(self, cor: AsyncIterator, ID: str):
        """流包装器.

        通过调用异步生成器传输流数据.

        Parameters:
            cor (AsyncIterator): - 异步迭代器
            ID (str): - 任务的ID

        Return:
            (bool): - 当正常调用则返回True

        """
        response = {
            "MPRPC": self.VERSION,
            "CODE": 201,
            "MESSAGE": {
                "ID": ID
            }
        }
        self.writer(response)
        if self.debug:
            access_logger.info(
                "Task[{}]: response stream start".format(ID),
                extra=self._extra
            )
        async for i in cor:
            response = {
                "MPRPC": self.VERSION,
                "CODE": 202,
                "MESSAGE": {
                    "ID": ID,
                    'RESULT': i
                }
            }
            self.writer(response)
            if self.debug:
                access_logger.info(
                    "Task[{}]: response stream yield".format(ID),
                    extra=self._extra
                )
        response = {
            "MPRPC": self.VERSION,
            "CODE": 206,
            "MESSAGE": {
                "ID": ID
            }
        }
        self.writer(response)
        if self.debug:
            access_logger.info(
                "Task[{}]: response stream end".format(ID),
                extra=self._extra
            )
        return True

    # ---------------------------------getresult----------------------------------
    async def _get_result(self, ID, _ID):
        try:
            result = await self.tasks[_ID]
            if inspect.isasyncgen(result):
                await self._asyncgen_wrap(result, _ID)
            else:
                response = {
                    "MPRPC": self.VERSION,
                    "CODE": 200,
                    "MESSAGE": {
                        "ID": ID,
                        'RESULT': result
                    }
                }
                self.writer(response)
                if self.debug:
                    access_logger.info(
                        "Task[{}]: response answered".format(ID),
                        extra=self._extra
                    )
        except Exception as e:
            print(e)
