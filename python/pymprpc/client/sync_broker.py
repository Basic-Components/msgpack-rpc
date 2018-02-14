from telnetlib import Telnet
from .sync import RPC


class BrokerRPC(EncoderDecoderMixin):
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
        self.compreser = compreser

        self._client = None

    def __enter__(self):
        self.connect()
        return self._client

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def connect(self):
        """与远端建立连接,并进行验证身份."""
        client = Telnet(self.hostname, self.port)
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
        client.write(queryb)
        data = client.read_until(self.SEPARATOR)
        response = self.decoder(data)
        code = response.get("CODE")
        if code == 50:
            url = response.get("URL")
            self._client = RPC(url, self.debug, self.compreser)
            self._client.connect()
        elif code == 51:
            raise abort(51)
        else:
            raise RuntimeError("unknown code {}".format(code))
        client.close()

    def close(self):
        """关闭与远端的连接.

        判断标志位closed是否为False,如果是则关闭,否则不进行操作

        """
        self._client.close()
