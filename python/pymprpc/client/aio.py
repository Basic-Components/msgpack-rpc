"""定义asyncio环境下使用的mprpc的客户端.

+ File: aio.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-02-08 version-0.5 by hsz

"""
import asyncio
import uuid
import zlib
import bz2
import lzma
import warnings
from typing import (
    Optional,
    Dict,
    Any
)
from urllib.parse import urlparse
from pymprpc.errors import (
    MprpcException,
    abort
)
from pymprpc.mixins.encoder_decoder_mixin import EncoderDecoderMixin
from .utils import Method


class AsyncRPC(EncoderDecoderMixin):
    """异步的RPC客户端.

    可以通过设置debug=True规定传输使用json且显示中间过程中的信息.

    Attributes:
        SEPARATOR (bytes): - 协议规定的请求响应终止符
        VERSION (str): - 协议版本,以`x.x`的形式表现版本
        COMPRESERS (Dict[str,model]): - 支持的压缩解压工具

        username (Optional[str]): - 登录远端的用户名
        password (Optional[str]): - 登录远端的密码
        hostname (str): - 远端的主机地址
        port (int): - 远端的主机端口

        loop (asyncio.AbstractEventLoop): - 使用的事件循环
        debug (bool): - 是否使用debug模式
        compreser (Optional[str]): - 是否使用压缩工具压缩传输信息,以及压缩工具是什么
        heart_beat (Optional[int]): - 是否使用心跳机制确保连接不会因过期而断开

        closed (bool): - 客户端是否已经关闭或者还未开始运转
        reader (asyncio.StreamReader): - 流读取对象
        writer (asyncio.StreamWriter): - 流写入对象
        tasks (Dict[str,asyncio.Future]): - 远端执行的任务,保存以ID为键
        gens (Dict[str,Any]): - 远端执行的流返回任务,保存以ID为键
        gens_res (Dict[str,List[Any]]): - 远端执行的流返回任务的结果,保存以ID为键
        remote_info (Dict[str,Any]): - 通过验证后返回的远端服务信息

    """

    SEPARATOR = b"##PRO-END##"
    COMPRESERS = {
        "zlib": zlib,
        "bz2": bz2,
        "lzma": lzma
    }
    VERSION = "0.1"

    def __init__(self,
                 addr: str,
                 loop: Optional[asyncio.AbstractEventLoop]=None,
                 debug: bool=False,
                 compreser: Optional[str]=None,
                 heart_beat: Optional[int]=None):
        """初始化RPC客户端.

        Parameters:
            addr (str): - 形如`tcp://xxx:xxx@xxx:xxx`的字符串
            loop (Optional[asyncio.AbstractEventLoop]): - 事件循环
            debug (bool): - 是否使用debug模式,默认为否
            compreser(Optional[str]): - 是否使用压缩工具压缩传输信息,以及压缩工具是什么,默认为不使用.
            heart_beat (Optional[int]):- 是否使用心跳机制确保连接不会因过期而断开,默认为不使用.

        """
        pas = urlparse(addr)
        if pas.scheme != "tcp":
            raise abort(505, "unsupported scheme for this protocol")
        # public
        self.username = pas.username
        self.password = pas.password
        self.hostname = pas.hostname
        self.port = pas.port
        self.loop = loop or asyncio.get_event_loop()
        self.debug = debug
        if compreser is not None:
            _compreser = self.COMPRESERS.get(compreser)
            if _compreser is not None:
                self.compreser = _compreser
            else:
                raise RuntimeError("compreser unsupport")
        else:
            self.compreser = None
        self.heart_beat = heart_beat

        self.closed = True
        self.reader = None
        self.writer = None
        self.tasks = {}
        self.remote_info = None
        # protected
        self._gens_queue = {}
        self._login_fut = None
        self._response_task = None
        self._heartbeat_task = None
        if self.debug is True:
            self.loop.set_debug(True)

    async def __aenter__(self):
        if self.debug is True:
            print('entering context')
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.debug is True:
            print('exit context')
        self.close()

    async def reconnect(self):
        """断线重连."""
        self.clean()
        try:
            self.writer.close()
        except:
            pass
        self.closed = True
        await self.connect()
        if self.debug:
            print("reconnect to {}".format((self.hostname, self.port)))

    async def connect(self):
        """与远端建立连接.

        主要执行的操作有:
        + 将监听响应的协程_response_handler放入事件循环
        + 如果有验证信息则发送验证信息
        + 获取连接建立的返回

        """
        self.reader, self.writer = await asyncio.open_connection(
            host=self.hostname,
            port=self.port,
            loop=self.loop)
        self.closed = False
        self._response_task = asyncio.ensure_future(self._response_handler())
        query = {
            "MPRPC": self.VERSION,
            "AUTH": {
                "USERNAME": self.username,
                "PASSWORD": self.password
            }
        }
        queryb = self.encoder(query)
        if self.debug is True:
            print("send auth {}".format(queryb))
        self.writer.write(queryb)
        self._login_fut = self.loop.create_future()
        self.remote_info = await self._login_fut
        if self.remote_info is False:
            raise abort(501)
        if self.heart_beat:
            self._heartbeat_task = asyncio.ensure_future(
                self._heartbeat_callback())

    def clean(self):
        """清理还在执行或者等待执行的协程."""
        for _, i in self.tasks.items():
            i.cancel()
        self._heartbeat_task.cancel()
        self._response_task.cancel()

    def close(self):
        """关闭与远端的连接.

        判断标志位closed是否为False,如果是则关闭,否则不进行操作

        """
        if self.closed is False:
            self.clean()
            try:
                self.writer.write_eof()
            except:
                pass
            self.writer.close()
            self.closed = True
            if self.debug is True:
                print('close')
        if self.debug is True:
            print("closed")

    # ------------------------心跳操作-------------------------------

    async def _heartbeat_callback(self):
        """如果设置了心跳,则调用这个协程."""
        query = {
            "MPRPC": self.VERSION,
            "HEARTBEAT": "ping"
        }
        queryb = self.encoder(query)
        while True:
            await asyncio.sleep(self.heart_beat)
            self.writer.write(queryb)
            if self.debug is True:
                print("ping")

    # ------------------------读取response操作-----------------------
    async def _response_handler(self):
        """监听响应数据的协程函数.`connect`被调用后会被创建为一个协程并放入事件循环."""
        if self.debug is True:
            if self.debug is True:
                print("listenning response!")
        while True:
            try:
                res = await self.reader.readuntil(self.SEPARATOR)
            except:
                raise
            else:
                response = self.decoder(res)
                self._status_code_check(response)

    def _status_code_check(self, response: Dict[str, Any]):
        """检查响应码并进行对不同的响应进行处理.

        主要包括:
        + 编码在500~599段为服务异常,直接抛出对应异常
        + 编码在400~499段为调用异常,为对应ID的future设置异常
        + 编码在300~399段为警告,会抛出对应警告
        + 编码在200~399段为执行成功响应,将结果设置给对应ID的future.
        + 编码在100~199段为服务器响应,主要是处理验证响应和心跳响应

        Parameters:
            response (Dict[str, Any]): - 响应的python字典形式数据

        Return:
            (bool): - 如果是非服务异常类的响应,那么返回True

        """
        code = response.get("CODE")
        if self.debug:
            print("resv:{}".format(response))
            print(code)

        if code >= 500:
            if self.debug:
                print("server error")
            self._server_error_handler(code)

        elif 500 > code >= 400:
            if self.debug:
                print("call method error")
            self._method_error_handler(response)

        elif 400 > code >= 200:
            if code >= 300:
                self._warning_handler(code)
            if code in (200, 201, 202, 206, 300, 301):
                if self.debug is True:
                    print("resv resp {}".format(response))
                self._method_response_handler(response)

        elif 200 > code >= 100:
            self._server_response_handler(response)
        else:
            raise MprpcException("unknow status code {}".format(code))
        return True

    def _server_error_handler(self, code: int):
        """处理500~599段状态码,抛出对应警告.

        Parameters:
            (code): - 响应的状态码

        Return:
            (bool): - 已知的警告类型则返回True,否则返回False

        Raise:
            (ServerException): - 当返回为服务异常时则抛出对应异常

        """
        if code == 501:
            self._login_fut.set_result(False)
        else:
            self.clean()
            raise abort(code)
        return True

    def _method_error_handler(self, response: Dict[str, Any]):
        """处理400~499段状态码,为对应的任务设置异常.

        Parameters:s
            (response): - 响应的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        exp = response.get('MESSAGE')
        code = response.get("CODE")
        ID = exp.get("ID")
        e = abort(code, ID=ID, message=exp.get('MESSAGE'))
        self.tasks[ID].set_exception(e)
        return True

    def _warning_handler(self, code: int):
        """处理300~399段状态码,抛出对应警告.

        Parameters:
            (code): - 响应的状态码

        Return:
            (bool): - 已知的警告类型则返回True,否则返回False

        """
        if code == 300:
            warnings.warn(
                "ExpireWarning",
                RuntimeWarning,
                stacklevel=3
            )
        elif code == 301:
            warnings.warn(
                "ExpireStreamWarning",
                RuntimeWarning,
                stacklevel=3
            )
        else:
            if self.debug:
                print("unknow code {}".format(code))
            return False
        return True

    def _method_response_handler(self, response: Dict[str, Any]):
        """处理200~399段状态码,为对应的响应设置结果.

        Parameters:
            (response): - 响应的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        code = response.get("CODE")
        if code in (200, 300):
            self._result_handler(response)
        else:
            asyncio.ensure_future(self._gen_result_handler(response))
            # self.gen_result_handler(response)

    def _server_response_handler(self, response: Dict[str, Any]):
        """处理100~199段状态码,针对不同的服务响应进行操作.

        Parameters:
            (response): - 响应的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        code = response.get("CODE")
        if code == 100:
            if self.debug:
                print("auth succeed")
            self._login_fut.set_result(response)
        if code == 101:
            if self.debug:
                print('pong')
        return True

    # ---------------------应答结果响应处理-------------------
    def _result_handler(self, response: Dict[str, Any]):
        """应答结果响应处理.

        将结果解析出来设置给任务对应的Future对象上

        Parameters:
            (response): - 响应的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        res = response.get("MESSAGE")
        ID = res.get("ID")
        result = res.get("RESULT")
        fut = self.tasks.get(ID)
        fut.set_result(result)
        return True

    # -----------------------流式结果响应处理-------------------

    async def _gen_result_handler(self, response: Dict[str, Any]):
        """流式结果响应处理.

        + 收到状态码标识201或301的响应后,将tasks中ID对应的Future对象的结果设置为一个用于包装的异步生成器.
        并为这个ID创建一个异步队列保存在`_gens_queue[ID]`中用于存取结果

        + 收到状态码标识为202的响应后向对应ID的存取队列中存入一条结果.

        + 收到终止状态码206后向对应ID的异步生成器结果获取队列中存入一个`StopAsyncIteration`对象用于终止异步迭代器

        Parameters:
            (response): - 响应的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        code = response.get("CODE")
        res = response.get("MESSAGE")
        ID = res.get("ID")
        if code in (201, 301):
            ait = self._wrap_gen(ID)
            self.tasks.get(ID).set_result(ait)
            self._gens_queue[ID] = asyncio.Queue()
        if code == 202:
            result = res.get('RESULT')
            await self._gens_queue[ID].put(result)

        if code == 206:
            await self._gens_queue[ID].put(StopAsyncIteration())
        return True

    async def _wrap_gen(self, ID: str):
        """异步迭代器包装.

        Parameters:
            ID (str): - 任务ID

        Yield:
            (Any): - 从异步迭代器结果队列中获取的结果

        Raise:
            (StopAsyncIteration): - 异步迭代器终止时抛出该异常

        """
        while True:
            result = await self._gens_queue[ID].get()
            if isinstance(result, StopAsyncIteration):
                del self._gens_queue[ID]
                break
            else:
                yield result

    # --------------------------发送请求--------------------------------------

    def _make_query(self, ID: str, methodname: str, returnable: bool, *args: Any, **kwargs: Any):
        """将调用请求的ID,方法名,参数包装为请求数据.

        Parameters:
            ID (str): - 任务ID
            methodname (str): - 要调用的方法名
            returnable (bool): - 是否要求返回结果
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:
            (Dict[str, Any]) : - 请求的python字典形式

        """
        query = {
            "MPRPC": self.VERSION,
            "ID": ID,
            "METHOD": methodname,
            "RETURN": returnable,
            "ARGS": args,
            "KWARGS": kwargs
        }
        print(query)
        return query

    def _send_query(self, query: Dict[str, Any]):
        """将请求编码为字节串发送出去给服务端.

        Parameters:
            (query): - 请求的的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        queryb = self.encoder(query)
        self.writer.write(queryb)
        if self.debug is True:
            print("send query {}".format(queryb))

        return True

    def send_query(self, ID, methodname, returnable, *args, **kwargs):
        """将调用请求的ID,方法名,参数包装为请求数据后编码为字节串发送出去.

        Parameters:
            ID (str): - 任务ID
            methodname (str): - 要调用的方法名
            returnable (bool): - 是否要求返回结果
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:

            (bool): - 准确地说没有错误就会返回True

        """
        query = self._make_query(ID, methodname, returnable, *args, **kwargs)
        self._send_query(query)
        self.tasks[ID] = self.loop.create_future()
        return True

    def delay(self, methodname, *args, **kwargs):
        """调用但不要求返回结果,而是通过系统方法getresult来获取.

        Parameters:
            methodname (str): - 要调用的方法名
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        """
        ID = str(uuid.uuid4())
        self.send_query(ID, methodname, False, *args, **kwargs)
        return ID

    def _async_query(self, ID, methodname, *args, **kwargs):
        """将调用请求的ID,方法名,参数包装为请求数据后编码为字节串发送出去.并创建一个Future对象占位.

        Parameters:
            ID (str): - 任务ID
            methodname (str): - 要调用的方法名
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:
            (asyncio.Future): - 返回对应ID的Future对象

        """
        self.send_query(ID, methodname, True, *args, **kwargs)
        task = self.tasks[ID]
        return task

    def async_query(self, methodname, *args, **kwargs):
        """异步调用一个远端的函数.

        为调用创建一个ID,并将调用请求的方法名,参数包装为请求数据后编码为字节串发送出去.并创建一个Future对象占位.

        Parameters:
            methodname (str): - 要调用的方法名
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:
            (asyncio.Future): - 返回对应ID的Future对象

        """
        ID = str(uuid.uuid4())
        task = self._async_query(ID=ID, methodname=methodname, *args, **kwargs)
        return task

    def __getattr__(self, name):
        """运算符`.`重载,让远程函数调用可以使用`.`符号设置要调用的函数."""
        ID = str(uuid.uuid4())
        print(name)
        return Method(self._async_query, name, ID)
