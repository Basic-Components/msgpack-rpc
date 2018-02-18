"""定义阻塞环境下使用的mprpc的客户端.

+ File: sync.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-02-08 version-0.5 by hsz

"""
import uuid
import zlib
import bz2
import lzma
import warnings
from telnetlib import Telnet
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


class RPC(EncoderDecoderMixin):
    """同步的RPC客户端.注意,是单线程实现,不支持心跳操作,也没有连接过期的检验.

    可以通过设置debug=True规定传输使用json且显示中间过程中的信息.

    Attributes:
        SEPARATOR (bytes): - 协议规定的请求响应终止符
        VERSION (str): - 协议版本,以`x.x`的形式表现版本
        COMPRESERS (Dict[str,model]): - 支持的压缩解压工具

        username (Optional[str]): - 登录远端的用户名
        password (Optional[str]): - 登录远端的密码
        hostname (str): - 远端的主机地址
        port (int): - 远端的主机端口

        debug (bool): - 是否使用debug模式
        compreser (Optional[str]): - 是否使用压缩工具压缩传输信息,以及压缩工具是什么

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
                 debug: bool=False,
                 compreser: Optional[str]=None):
        """初始化RPC客户端.

        Parameters:
            addr (str): - 形如`tcp://xxx:xxx@xxx:xxx`的字符串
            debug (bool): - 是否使用debug模式,默认为否
            compreser(Optional[str]): - 是否使用压缩工具压缩传输信息,以及压缩工具是什么,默认为不使用.

        """
        pas = urlparse(addr)
        if pas.scheme != "tcp":
            raise abort(505, "unsupported scheme for this protocol")
        # public
        self.username = pas.username
        self.password = pas.password
        self.hostname = pas.hostname
        self.port = pas.port
        self.debug = debug
        if compreser is not None:
            _compreser = self.COMPRESERS.get(compreser)
            if _compreser is not None:
                self.compreser = _compreser
            else:
                raise RuntimeError("compreser unsupport")
        else:
            self.compreser = None

        self.closed = True
        self.reader = None
        self.writer = None
        self.tasks = {}
        self.remote_info = None
        # protected
        self._client = None

    def __enter__(self):
        if self.debug is True:
            print('entering context')
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.debug is True:
            print('exit context')
        self.close()

    def connect(self):
        """与远端建立连接,并进行验证身份."""
        self._client = Telnet(self.hostname, self.port)
        self.closed = False
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
        self._client.write(queryb)
        self.remote_info = self._responsehandler()

    def reconnect(self):
        """断线重连."""
        self.closed = True
        self.connect()
        if self.debug:
            print("reconnect to {}".format((self.hostname, self.port)))

    def close(self):
        """关闭与远端的连接.

        判断标志位closed是否为False,如果是则关闭,否则不进行操作

        """
        if self.closed is False:
            self._client.close()
            self.closed = True
            if self.debug is True:
                print('close')
        if self.debug is True:
            print("closed")

    def _responsehandler(self):
        if self.debug is True:
            if self.debug is True:
                print("listenning response!")
        try:
            data = self._client.read_until(self.SEPARATOR)
        except Exception as e:
            print(e)
            raise
        else:
            response = self.decoder(data)
            return self._status_code_check(response)

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
            return self._server_error_handler(code)

        elif 500 > code >= 400:
            if self.debug:
                print("call method error")
            return self._method_error_handler(response)

        elif 400 > code >= 200:
            if code >= 300:
                self._warning_handler(code)
            if code in (200, 201, 202, 206, 300, 301):
                if self.debug is True:
                    print("resv resp {}".format(response))
                return self._method_response_handler(response)

        elif 200 > code >= 100:
            return self._server_response_handler(response)
        else:
            raise MprpcException("unknow status code {}".format(code))

    def _server_error_handler(self, code: int):
        """处理500~599段状态码,抛出对应警告.

        Parameters:
            (code): - 响应的状态码

        Return:
            (bool): - 已知的警告类型则返回True,否则返回False

        Raise:
            (ServerException): - 当返回为服务异常时则抛出对应异常

        """
        raise abort(code)

    def _method_error_handler(self, response: Dict[str, Any]):
        """处理400~499段状态码,为对应的任务设置异常.

        Parameters:
            (response): - 响应的python字典形式数据

        Return:
            (bool): - 准确地说没有错误就会返回True

        """
        exp = response.get('MESSAGE')
        code = response.get("CODE")
        ID = exp.get("ID")
        raise abort(code, ID=ID, message=exp.get('MESSAGE'))

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
            return self._result_handler(response)
        elif code in (201, 301):
            return self._gen_result_handler()

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
            return response
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
        result = res.get("RESULT")
        return result

    # -----------------------流式结果响应处理-------------------

    def _gen_result_handler(self):
        """流式结果响应处理.

        收到状态码标识201或301的响应后,创建一个生成器用于反映流.

        Yield:
            (Any): - 流中的运算结果

        """
        while True:
            try:
                data = self._client.read_until(self.SEPARATOR)
            except:
                raise
            else:
                response = self.decoder(data)
                code = response.get("CODE")
                res = response.get("MESSAGE")
                if code == 202:
                    result = res.get('RESULT')
                    yield result
                if code == 206:
                    break

    # --------------------------发送请求--------------------------------------

    def _make_query(self, ID: str, methodname: str, *args: Any, **kwargs: Any):
        """将调用请求的ID,方法名,参数包装为请求数据.

        Parameters:
            ID (str): - 任务ID
            methodname (str): - 要调用的方法名
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:
            (Dict[str, Any]) : - 请求的python字典形式

        """
        query = {
            "MPRPC": self.VERSION,
            "ID": ID,
            "METHOD": methodname,
            "RETURN": True,
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
        self._client.write(queryb)
        if self.debug is True:
            print("send query {}".format(queryb))

        return True

    def send_query(self, ID, methodname, *args, **kwargs):
        """将调用请求的ID,方法名,参数包装为请求数据后编码为字节串发送出去.

        Parameters:
            ID (str): - 任务ID
            methodname (str): - 要调用的方法名
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:

            (bool): - 准确地说没有错误就会返回True

        """
        query = self._make_query(ID, methodname, *args, **kwargs)
        self._send_query(query)
        return True

    # def delay(self, methodname, *args, **kwargs):
    #     """调用但不要求返回结果,而是通过系统方法getresult来获取.

    #     Parameters:
    #         methodname (str): - 要调用的方法名
    #         args (Any): - 要调用的方法的位置参数
    #         kwargs (Any): - 要调用的方法的关键字参数

    #     """
    #     ID = str(uuid.uuid4())
    #     self.send_query(ID, methodname, False, *args, **kwargs)
    #     return ID

    def _query(self, ID, methodname, *args, **kwargs):
        """将调用请求的ID,方法名,参数包装为请求数据后编码为字节串发送出去.并创建一个Future对象占位.

        Parameters:
            ID (str): - 任务ID
            methodname (str): - 要调用的方法名
            args (Any): - 要调用的方法的位置参数
            kwargs (Any): - 要调用的方法的关键字参数

        Return:

            (asyncio.Future): - 返回对应ID的Future对象

        """
        self.send_query(ID, methodname, *args, **kwargs)
        result = self._responsehandler()
        return result

    def query(self, methodname, *args, **kwargs):
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
        result = self._query(ID=ID, methodname=methodname, *args, **kwargs)
        return result

    def __getattr__(self, name):
        """运算符`.`重载,让远程函数调用可以使用`.`符号设置要调用的函数."""
        ID = str(uuid.uuid4())
        print(name)
        return Method(self._query, name, ID)
