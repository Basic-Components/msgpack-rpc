import asyncio
from pymprpc.mixins.encoder_decoder_mixin import EncoderDecoderMixin
from pymprpc.errors import abort

from .aio import AsyncRPC


class AsyncBrokerRPC(EncoderDecoderMixin):
    """异步的RPC客户端.

    可以通过设置debug=True规定传输使用json且显示中间过程中的信息.

    Attributes:
        SEPARATOR (bytes): - 协议规定的请求响应终止符
        VERSION (str): - 协议版本,以`x.x`的形式表现版本

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
    VERSION = "0.1"

    def __init__(self,
                 addr: str,
                 loop: Optional[asyncio.AbstractEventLoop]=None,
                 debug: bool=False,
                 compreser: Optional[str]=None,
                 heart_beat: Optional[int]=None):
        """初始化RPC客户端.

        Parameters:
            addr (str): - 形如`tcp://xxx:xxx@xxx:xxx`的字符串,指向中介
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
        self.compreser = compreser
        self.heart_beat = heart_beat
        # protected
        self._client = None

    async def __aenter__(self):
        if self.debug is True:
            print('entering context')
        await self.connect()
        return self._client

    async def __aexit__(self, exc_type, exc, tb):
        if self.debug is True:
            print('exit context')
        self.close()

    async def connect(self):
        """与远端建立连接.

        主要执行的操作有:
        + 将监听响应的协程_response_handler放入事件循环
        + 如果有验证信息则发送验证信息
        + 获取连接建立的返回

        """
        reader, writer = await asyncio.open_connection(
            host=self.hostname,
            port=self.port,
            loop=self.loop)
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
        writer.write(queryb)
        res = await reader.readuntil(self.SEPARATOR)
        response = self.decoder(res)
        code = response.get("CODE")
        if code == 50:
            url = response.get("URL")
            self._client = AsyncRPC(url,
                                    loop=self.loop,
                                    self.debug
                                    self.compreser,
                                    self.heart_beat)
            await self._client.connect()
        elif code == 51:
            raise abort(51)
        else:
            raise RuntimeError("unknown code {}".format(code))
        try:
            writer.write_eof()
            print("close broker with eof")
        except:
            writer.close()
            print("close broker")
        finally:
            reader = None
            writer = None

    def close(self):
        """关闭与远端的连接.

        判断标志位closed是否为False,如果是则关闭,否则不进行操作

        """
        self._client.close()
